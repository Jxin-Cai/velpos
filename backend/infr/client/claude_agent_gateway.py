from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk._errors import ProcessError
from claude_agent_sdk.types import (
    SystemMessage as _SystemMessage,
    TaskStartedMessage,
    TaskProgressMessage,
    TaskNotificationMessage,
    ResultMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from domain.session.acl.claude_agent_gateway import (
    ClaudeAgentGateway as ClaudeAgentGatewayPort,
)

logger = logging.getLogger(__name__)


class ClaudeAgentGateway(ClaudeAgentGatewayPort):

    def __init__(
        self,
        cli_path: str | None = None,
        permission_mode: str | None = None,
        max_buffer_size: int | None = None,
    ) -> None:
        import os

        self._cli_path = cli_path or os.getenv("CLAUDE_CLI_PATH")
        if not self._cli_path:
            raise RuntimeError("CLAUDE_CLI_PATH environment variable is not set")
        self._permission_mode = permission_mode or os.getenv("CLAUDE_PERMISSION_MODE", "bypassPermissions")
        self._max_buffer_size = max_buffer_size or int(os.getenv("CLAUDE_MAX_BUFFER_SIZE", str(10 * 1024 * 1024)))
        self._idle_timeout = float(os.getenv("CLAUDE_IDLE_TIMEOUT", "300"))
        # session_id -> ClaudeSDKClient (long-lived connections)
        self._clients: dict[str, ClaudeSDKClient] = {}
        # session_id -> SDK session_id (UUID) for JSONL cleanup
        self._sdk_session_ids: dict[str, str] = {}
        # session_id -> project_dir (cwd) for JSONL cleanup
        self._session_cwds: dict[str, str] = {}
        # session_id -> model used when connecting (for reconnect-on-change)
        self._connected_models: dict[str, str] = {}
        # session_id -> permission_mode set by user
        self._session_permission_modes: dict[str, str] = {}
        # session_id -> asyncio.Future for pending user responses (choices/permissions)
        self._pending_user_responses: dict[str, asyncio.Future] = {}
        # session_id -> pending request context (questions list for AskUserQuestion)
        self._pending_request_context: dict[str, dict[str, Any]] = {}
        # callback for persisting pending request context
        self._persist_pending_request_context_fn: Any = None
        # session_id -> last activity timestamp
        self._last_activity: dict[str, float] = {}
        # session_id -> asyncio.TimerHandle for scheduled idle disconnect
        self._idle_timers: dict[str, asyncio.TimerHandle] = {}
        # sessions actively running a query (protected from idle disconnect)
        self._active_sessions: set[str] = set()
        # broadcast callback: set externally to push events to WS clients
        self._broadcast_fn: Any = None
        # IM binding check callback: set externally to protect bound sessions
        self._is_im_bound_fn: Any = None
        # Lock for protecting _pending_user_responses and _clients mutations
        self._lock = asyncio.Lock()

    def set_broadcast_fn(self, fn: Any) -> None:
        """Set the broadcast function for pushing events to WebSocket clients."""
        self._broadcast_fn = fn

    def set_is_im_bound_fn(self, fn: Any) -> None:
        """Set the callback to check if a session has an active IM binding."""
        self._is_im_bound_fn = fn

    def set_persist_pending_request_context_fn(self, fn: Any) -> None:
        """Set the callback for persisting pending request context."""
        self._persist_pending_request_context_fn = fn

    async def _persist_pending_request_context(
        self,
        session_id: str,
        context: dict[str, Any] | None,
    ) -> None:
        if not self._persist_pending_request_context_fn:
            return
        try:
            await self._persist_pending_request_context_fn(session_id, context)
        except Exception:
            logger.warning(
                "persist pending request context failed: session=%s",
                session_id,
                exc_info=True,
            )

    @staticmethod
    def _normalize_tool_result_content(content: Any) -> Any:
        if content is None or isinstance(content, (str, list, dict, int, float, bool)):
            return content
        return str(content)[:500]

    @staticmethod
    def _create_stderr_collector() -> tuple[list[str], "Callable[[str], None]"]:
        """Create a stderr line collector and its callback."""
        lines: list[str] = []

        def _on_stderr(line: str) -> None:
            lines.append(line)
            logger.warning("CLI stderr: %s", line)

        return lines, _on_stderr

    async def _try_connect(
        self,
        session_id: str,
        model: str,
        perm_mode: str,
        cwd: str,
        prev_sdk_sid: str | None,
    ) -> ClaudeSDKClient:
        """Build options, connect CLI; if resume fails, fallback to fresh session."""
        stderr_lines, stderr_cb = self._create_stderr_collector()
        options = ClaudeAgentOptions(
            model=model,
            permission_mode=perm_mode,
            max_buffer_size=self._max_buffer_size,
            cli_path=self._cli_path,
            setting_sources=["user", "project"],
            cwd=cwd if cwd else None,
            resume=prev_sdk_sid,
            continue_conversation=bool(prev_sdk_sid),
            can_use_tool=self._create_can_use_tool_callback(session_id),
            stderr=stderr_cb,
        )

        client = ClaudeSDKClient(options=options)
        try:
            await client.connect()
            return client
        except ProcessError:
            if not prev_sdk_sid:
                raise

            # Resume failed — fallback to fresh session
            logger.warning("resume 失败, 降级为新会话: session=%s", session_id)
            self._sdk_session_ids.pop(session_id, None)

            options_fresh = ClaudeAgentOptions(
                model=model,
                permission_mode=perm_mode,
                max_buffer_size=self._max_buffer_size,
                cli_path=self._cli_path,
                setting_sources=["user", "project"],
                cwd=cwd if cwd else None,
                can_use_tool=self._create_can_use_tool_callback(session_id),
                stderr=stderr_cb,
            )
            client_fresh = ClaudeSDKClient(options=options_fresh)
            await client_fresh.connect()
            return client_fresh

    def mark_active(self, session_id: str) -> None:
        """Mark a session as actively running a query."""
        self._active_sessions.add(session_id)

    def mark_idle(self, session_id: str) -> None:
        """Mark a session as no longer actively running a query."""
        self._active_sessions.discard(session_id)

    def is_active(self, session_id: str) -> bool:
        """Check if a session is actively running a query."""
        return session_id in self._active_sessions

    def _touch(self, session_id: str) -> None:
        """Update last activity time and cancel any pending idle disconnect."""
        self._last_activity[session_id] = time.monotonic()
        timer = self._idle_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()
            logger.debug("取消空闲清理定时器: session=%s", session_id)

    def schedule_idle_disconnect(self, session_id: str, delay: float | None = None) -> None:
        """Schedule a delayed disconnect for an idle session."""
        if session_id not in self._clients:
            return
        # Cancel existing timer if any
        old = self._idle_timers.pop(session_id, None)
        if old is not None:
            old.cancel()
        delay = delay if delay is not None else self._idle_timeout
        loop = asyncio.get_running_loop()
        self._idle_timers[session_id] = loop.call_later(
            delay,
            lambda sid=session_id: asyncio.create_task(self._idle_disconnect(sid)),
        )
        logger.info("已调度空闲断开: session=%s", session_id)

    async def _idle_disconnect(self, session_id: str) -> None:
        """Disconnect an idle session. Skips if running a query or pending user response."""
        self._idle_timers.pop(session_id, None)
        if session_id not in self._clients:
            return
        # Don't disconnect while a query is actively running
        if session_id in self._active_sessions:
            logger.info("空闲断开跳过(查询运行中): session=%s, 重新调度", session_id)
            self.schedule_idle_disconnect(session_id)
            return
        # Don't disconnect while waiting for user permission/choice
        if session_id in self._pending_user_responses:
            logger.info("空闲断开跳过(等待用户响应): session=%s, 重新调度", session_id)
            self.schedule_idle_disconnect(session_id)
            return
        # Don't disconnect sessions with active IM bindings
        if self._is_im_bound_fn:
            try:
                if await self._is_im_bound_fn(session_id):
                    logger.info("空闲断开跳过(IM绑定): session=%s, 重新调度", session_id)
                    self.schedule_idle_disconnect(session_id)
                    return
            except Exception:
                logger.warning("检查IM绑定状态失败: session=%s", session_id, exc_info=True)
        logger.info("空闲断开: session=%s", session_id)
        await self.disconnect(session_id)

    async def disconnect_all(self) -> None:
        """Disconnect all active SDK clients (server shutdown)."""
        # Cancel all idle timers
        for timer in self._idle_timers.values():
            timer.cancel()
        self._idle_timers.clear()
        # Disconnect all clients
        session_ids = list(self._clients.keys())
        for sid in session_ids:
            try:
                await self.disconnect(sid)
            except Exception:
                logger.warning("disconnect_all 异常: session=%s", sid, exc_info=True)
        logger.info("disconnect_all 完成, 清理了 %d 个连接", len(session_ids))

    async def connect(
        self,
        session_id: str,
        model: str,
        prompt: str,
        cwd: str = "",
        sdk_session_id: str = "",
    ) -> AsyncIterator[dict[str, Any]]:

        # Use externally persisted sdk_session_id for resume, fall back to in-memory cache
        prev_sdk_sid = sdk_session_id or self._sdk_session_ids.get(session_id)

        # Disconnect existing client if any
        await self.disconnect(session_id)

        # Use per-session permission mode if set, otherwise fall back to default
        perm_mode = self._session_permission_modes.get(session_id, self._permission_mode)

        client = await self._try_connect(
            session_id=session_id,
            model=model,
            perm_mode=perm_mode,
            cwd=cwd,
            prev_sdk_sid=prev_sdk_sid,
        )
        self._clients[session_id] = client
        self._connected_models[session_id] = model
        self._touch(session_id)
        if cwd:
            self._session_cwds[session_id] = cwd

        # Force permission mode after connect — resume can restore a stale mode
        try:
            await client.set_permission_mode(perm_mode)
        except Exception:
            logger.debug("set_permission_mode after connect failed (non-critical): session=%s", session_id)

        # Send query and receive response until ResultMessage
        await client.query(prompt=prompt)

        async for msg in client.receive_response():
            # Capture SDK session_id from messages that carry it
            sdk_sid = getattr(msg, "session_id", None)
            if sdk_sid:
                old_sid = self._sdk_session_ids.get(session_id)
                if old_sid != sdk_sid:
                    self._sdk_session_ids[session_id] = sdk_sid
            info = self._extract_message_info(msg)
            if info is not None:
                # Attach captured SDK session_id so caller can persist it
                if sdk_sid:
                    info["sdk_session_id"] = sdk_sid
                yield info

    async def send_query(
        self,
        session_id: str,
        prompt: str,
    ) -> AsyncIterator[dict[str, Any]]:
        client = self._clients.get(session_id)
        if client is None:
            raise RuntimeError(f"No active connection for session {session_id}")

        self._touch(session_id)
        await client.query(prompt=prompt)

        async for msg in client.receive_response():
            sdk_sid = getattr(msg, "session_id", None)
            if sdk_sid:
                old_sid = self._sdk_session_ids.get(session_id)
                if old_sid != sdk_sid:
                    self._sdk_session_ids[session_id] = sdk_sid
            info = self._extract_message_info(msg)
            if info is not None:
                if sdk_sid:
                    info["sdk_session_id"] = sdk_sid
                yield info

    async def compact(
        self,
        session_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        client = self._clients.get(session_id)
        if client is None:
            raise RuntimeError(f"No active connection for session {session_id}")

        await client.query(prompt="/compact")

        async for msg in client.receive_response():
            sdk_sid = getattr(msg, "session_id", None)
            if sdk_sid:
                old_sid = self._sdk_session_ids.get(session_id)
                if old_sid != sdk_sid:
                    self._sdk_session_ids[session_id] = sdk_sid
            info = self._extract_message_info(msg)
            if info is not None:
                yield info

    async def interrupt(self, session_id: str) -> None:
        client = self._clients.get(session_id)
        if client is None:
            raise RuntimeError(f"No active connection for session {session_id}")
        await client.interrupt()

    async def disconnect(self, session_id: str) -> None:
        client = self._clients.pop(session_id, None)
        if client is not None:
            try:
                await client.disconnect()
            except RuntimeError as e:
                # anyio cross-task cancel scope error — kill subprocess directly
                logger.warning("disconnect RuntimeError (cross-task): session=%s, %s", session_id, e)
                self._force_kill_client(client)
            except Exception:
                logger.warning("disconnect 异常: session=%s", session_id, exc_info=True)
                self._force_kill_client(client)
        self._connected_models.pop(session_id, None)
        # Note: _sdk_session_ids, _session_cwds, _session_permission_modes persist
        # across reconnects to support resume and cleanup

    @staticmethod
    def _force_kill_client(client: ClaudeSDKClient) -> None:
        """Force kill the underlying subprocess when graceful disconnect fails."""
        try:
            transport = getattr(client, "_transport", None)
            if transport is None:
                return
            process = getattr(transport, "_process", None)
            if process is None:
                return
            if process.returncode is None:
                process.kill()
                logger.info("force killed subprocess pid=%s", getattr(process, "pid", "?"))
        except Exception:
            logger.warning("force kill failed", exc_info=True)

    def cleanup_session(self, session_id: str) -> None:
        """Remove all tracked state for a session (call after full deletion)."""
        self._sdk_session_ids.pop(session_id, None)
        self._session_cwds.pop(session_id, None)
        self._session_permission_modes.pop(session_id, None)
        self._last_activity.pop(session_id, None)
        self._active_sessions.discard(session_id)
        timer = self._idle_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()
        fut = self._pending_user_responses.pop(session_id, None)
        self._pending_request_context.pop(session_id, None)
        if fut and not fut.done():
            fut.cancel()

    def _create_can_use_tool_callback(self, session_id: str):
        """Create a can_use_tool callback that broadcasts to WS and waits for user response."""

        async def can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            ctx: ToolPermissionContext,
        ):
            if not self._broadcast_fn:
                logger.warning("No broadcast_fn set, auto-allowing tool: %s", tool_name)
                return PermissionResultAllow()

            # In bypass mode, auto-allow all tools except AskUserQuestion
            # (AskUserQuestion is user interaction, not a permission check)
            perm_mode = self._session_permission_modes.get(session_id, self._permission_mode)
            if perm_mode == "bypassPermissions" and tool_name != "AskUserQuestion":
                logger.debug("bypassPermissions: auto-allowing tool %s", tool_name)
                return PermissionResultAllow()

            # Determine event type based on tool name
            if tool_name == "AskUserQuestion":
                event_type = "user_choice_request"
                event_data = {
                    "event": event_type,
                    "tool_name": tool_name,
                    "questions": tool_input.get("questions", []),
                }
            else:
                event_type = "permission_request"
                # Summarize tool input for display
                input_summary = str(tool_input)
                if len(input_summary) > 500:
                    input_summary = input_summary[:500] + "..."
                event_data = {
                    "event": event_type,
                    "tool_name": tool_name,
                    "tool_input": input_summary,
                }

            # Create a Future to wait for user response
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            async with self._lock:
                self._pending_user_responses[session_id] = fut
                self._pending_request_context[session_id] = {
                    "tool_name": tool_name,
                    "questions": tool_input.get("questions", []) if tool_name == "AskUserQuestion" else [],
                    "tool_input": str(tool_input)[:500] if tool_name != "AskUserQuestion" else "",
                }
                pending_context = dict(self._pending_request_context[session_id])

            await self._persist_pending_request_context(session_id, pending_context)

            # Broadcast to WS clients
            await self._broadcast_fn(session_id, event_data)

            try:
                # Wait for user response with timeout (5 minutes)
                response = await asyncio.wait_for(fut, timeout=300)
            except asyncio.TimeoutError:
                logger.warning("can_use_tool timeout: session=%s, tool=%s", session_id, tool_name)
                return PermissionResultDeny(message="User response timeout")
            except asyncio.CancelledError:
                logger.info("can_use_tool cancelled: session=%s, tool=%s", session_id, tool_name)
                return PermissionResultDeny(message="Cancelled by user")
            finally:
                async with self._lock:
                    self._pending_user_responses.pop(session_id, None)
                    self._pending_request_context.pop(session_id, None)
                await self._persist_pending_request_context(session_id, None)

            if tool_name == "AskUserQuestion":
                # For AskUserQuestion, pass answers via updated_input
                answers = response.get("answers", {})
                updated = {**tool_input, "answers": answers}
                return PermissionResultAllow(updated_input=updated)
            else:
                # For permission requests, allow or deny
                if response.get("decision") == "allow":
                    return PermissionResultAllow()
                else:
                    return PermissionResultDeny(
                        message=response.get("message", "User denied"),
                    )

        return can_use_tool

    async def resolve_user_response(self, session_id: str, response_data: dict[str, Any]) -> bool:
        """Resolve a pending user response (choice answer or permission decision).

        Returns True if a pending response was resolved, False if none was pending.
        """
        async with self._lock:
            fut = self._pending_user_responses.get(session_id)
            if fut and not fut.done():
                fut.set_result(response_data)
                logger.info("resolve_user_response: session=%s", session_id)
                return True
        logger.warning("resolve_user_response: no pending response for session=%s", session_id)
        return False

    async def get_pending_request_context(self, session_id: str) -> dict[str, Any] | None:
        """Return the pending request context if a user response is awaited, else None."""
        async with self._lock:
            if session_id in self._pending_user_responses:
                fut = self._pending_user_responses[session_id]
                if not fut.done():
                    return self._pending_request_context.get(session_id)
        return None

    async def cancel_pending_response(self, session_id: str) -> bool:
        """Cancel a pending user response future so the query can terminate.

        Returns True if a pending response was cancelled, False if none was pending.
        """
        cancelled = False
        async with self._lock:
            fut = self._pending_user_responses.pop(session_id, None)
            self._pending_request_context.pop(session_id, None)
            if fut and not fut.done():
                fut.cancel()
                cancelled = True
        await self._persist_pending_request_context(session_id, None)
        if cancelled:
            logger.info("cancel_pending_response: session=%s", session_id)
        return cancelled

    async def set_model(self, session_id: str, model: str) -> None:
        client = self._clients.get(session_id)
        if client is None:
            raise RuntimeError(f"No active connection for session {session_id}")
        await client.set_model(model)

    async def set_permission_mode(self, session_id: str, mode: str) -> None:
        # Always persist the choice so it's used on next connect
        self._session_permission_modes[session_id] = mode
        client = self._clients.get(session_id)
        if client is None:
            return
        await client.set_permission_mode(mode)

    def is_connected(self, session_id: str) -> bool:
        """Check if a session has an active SDK client."""
        return session_id in self._clients

    def is_process_alive(self, session_id: str) -> bool:
        """Check if the underlying CLI subprocess is still running.

        Returns False if no client exists or the subprocess has exited.
        """
        client = self._clients.get(session_id)
        if client is None:
            return False
        transport = getattr(client, "_transport", None)
        if transport is None:
            return False
        process = getattr(transport, "_process", None)
        if process is None:
            return False
        return process.returncode is None

    async def open_connection(
        self,
        session_id: str,
        model: str,
        cwd: str = "",
        sdk_session_id: str = "",
    ) -> None:
        """Open a persistent SDK connection without sending a query."""
        prev_sdk_sid = sdk_session_id or self._sdk_session_ids.get(session_id)

        if not prev_sdk_sid:
            raise RuntimeError(
                f"Cannot open persistent connection for session {session_id}: "
                "no SDK session to resume (run a query first)"
            )

        await self.disconnect(session_id)

        perm_mode = self._session_permission_modes.get(session_id, self._permission_mode)

        client = await self._try_connect(
            session_id=session_id,
            model=model,
            perm_mode=perm_mode,
            cwd=cwd,
            prev_sdk_sid=prev_sdk_sid,
        )
        self._clients[session_id] = client
        self._connected_models[session_id] = model
        self._touch(session_id)
        if cwd:
            self._session_cwds[session_id] = cwd

        # Force permission mode after connect — resume can restore a stale mode
        try:
            await client.set_permission_mode(perm_mode)
        except Exception:
            logger.debug("set_permission_mode after open_connection failed (non-critical): session=%s", session_id)

    def get_connected_model(self, session_id: str) -> str | None:
        """Return the model used for the current connection, or None if not connected."""
        return self._connected_models.get(session_id)

    def get_cached_sdk_session_id(self, session_id: str) -> str | None:
        """Return the cached SDK session ID for a session, or None if not tracked."""
        return self._sdk_session_ids.get(session_id)

    def get_permission_mode(self, session_id: str) -> str:
        """Return the effective permission mode for a session."""
        return self._session_permission_modes.get(session_id, self._permission_mode)

    def delete_session_files(
        self, session_id: str, project_dir: str, sdk_session_id: str | None = None,
    ) -> None:
        """Delete Claude Code JSONL session files for the given session.

        Uses SDK's list_sessions to find matching sessions and removes the
        JSONL files from ~/.claude/projects/.

        *sdk_session_id* is an optional fallback taken from the DB when the
        gateway's in-memory ``_sdk_session_ids`` mapping has no entry (e.g.
        after a process restart).
        """
        import os
        from claude_agent_sdk import list_sessions as sdk_list_sessions
        from claude_agent_sdk._internal.sessions import (
            _canonicalize_path,
            _find_project_dir,
        )

        # Try to find and delete by tracked SDK session_id first
        # Fall back to DB-persisted sdk_session_id when in-memory mapping is empty
        sdk_sid = self._sdk_session_ids.get(session_id) or sdk_session_id
        cwd = self._session_cwds.get(session_id) or project_dir

        if sdk_sid and cwd:
            canonical = _canonicalize_path(cwd)
            proj_dir = _find_project_dir(canonical)
            if proj_dir is not None:
                jsonl_path = proj_dir / f"{sdk_sid}.jsonl"
                if jsonl_path.exists():
                    try:
                        jsonl_path.unlink()
                        logger.info("已删除 JSONL: %s", jsonl_path)
                    except OSError:
                        logger.warning("删除 JSONL 失败: %s", jsonl_path, exc_info=True)
                    return

        logger.info("未找到 SDK session_id 对应的 JSONL 文件: session=%s", session_id)

    async def get_models(self) -> list[dict[str, Any]]:
        """Get available models by connecting a temporary SDK client and reading server info."""
        raw_models: list[dict[str, Any]] = []

        # Reuse any existing client to avoid spawning a new process
        for client in self._clients.values():
            try:
                info = await client.get_server_info()
                if info and "models" in info:
                    raw_models = info["models"]
                    break
            except Exception:
                pass

        # No active client — create a temporary one
        if not raw_models:
            client = ClaudeSDKClient(options=ClaudeAgentOptions(
                cli_path=self._cli_path,
                permission_mode=self._permission_mode,
                max_buffer_size=self._max_buffer_size,
            ))
            try:
                await client.connect()
                info = await client.get_server_info()
                raw_models = (info or {}).get("models", [])
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        # Enrich with context_window: use known sizes first, then parse from text
        import re
        for model in raw_models:
            model_id = model.get("value", "")
            # Use known actual context size if available
            known = self._KNOWN_CONTEXT_WINDOWS.get(model_id)
            if known:
                model["context_window"] = known
                continue
            # Fallback: parse from displayName/description
            text = f"{model.get('displayName', '')} {model.get('description', '')}"
            match = re.search(r'(\d+(?:\.\d+)?)\s*[Mm]\s*context', text)
            if match:
                parsed = int(float(match.group(1)) * 1_000_000)
                model["context_window"] = parsed
            else:
                match_k = re.search(r'(\d+)\s*[Kk]\s*context', text)
                if match_k:
                    model["context_window"] = int(match_k.group(1)) * 1000
                else:
                    model["context_window"] = 200_000

        return raw_models

    async def get_models_for_channel(
        self,
        host: str = "",
        api_key: str = "",
    ) -> list[dict[str, Any]]:
        """Get available models using channel credentials via standard Anthropic API.

        Calls host + /v1/models (standard Anthropic endpoint) to list models.
        Falls back to empty list on error.
        """
        import httpx

        base_url = (host.rstrip("/") if host else "https://api.anthropic.com")
        url = f"{base_url}/v1/models"

        headers: dict[str, str] = {
            "anthropic-version": "2023-06-01",
        }
        if api_key:
            headers["x-api-key"] = api_key

        models: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "get_models_for_channel failed: status=%d, body=%s",
                        resp.status_code, resp.text[:200],
                    )
                    return []
                data = resp.json()
                # Standard Anthropic response: { "data": [ { "id": "...", "display_name": "...", ... } ] }
                raw_models = data.get("data", [])
                for m in raw_models:
                    model_id = m.get("id", "")
                    display_name = m.get("display_name", model_id)
                    # Use context_window from API if available, otherwise default
                    ctx_window = m.get("context_window") or self._KNOWN_CONTEXT_WINDOWS.get(model_id, 200_000)
                    models.append({
                        "value": model_id,
                        "displayName": display_name,
                        "description": m.get("description", ""),
                        "context_window": ctx_window,
                    })
        except Exception as e:
            logger.warning("get_models_for_channel error: %s", str(e))

        return models

    # System subtypes that carry no useful information for the user
    _IGNORED_SYSTEM_SUBTYPES: set[str] = {"init", "greeting"}

    # Known actual context window sizes for Claude models.
    # Values from Anthropic API model metadata.
    # Models not listed here will have context parsed from SDK description text.
    _KNOWN_CONTEXT_WINDOWS: dict[str, int] = {}

    @staticmethod
    def _extract_message_info(msg: Any) -> dict[str, Any] | None:
        """Extract a normalised dict from an SDK message.

        Returns a dict that **always** contains:
          - ``message_type``  (str matching a ``MessageType`` value)
          - ``content``       (dict with type-specific payload)

        For ``ResultMessage`` the dict additionally carries
        ``input_tokens`` / ``output_tokens`` so the caller can
        accumulate usage.

        Returns ``None`` for unrecognised message types.
        """
        if isinstance(msg, _SystemMessage):
            subtype = getattr(msg, "subtype", "")
            if subtype in ClaudeAgentGateway._IGNORED_SYSTEM_SUBTYPES:
                logger.debug("忽略无信息价值的 system 消息: subtype=%s", subtype)
                return None
            return ClaudeAgentGateway._extract_system_message(msg)

        msg_type = msg.__class__.__name__

        if msg_type == "AssistantMessage":
            blocks: list[dict[str, Any]] = []
            if hasattr(msg, "content") and msg.content:
                content_list = (
                    msg.content if isinstance(msg.content, list) else [msg.content]
                )
                for block in content_list:
                    block_type = block.__class__.__name__
                    if block_type == "TextBlock":
                        blocks.append({"type": "text", "text": getattr(block, "text", "")})
                    elif block_type == "ToolUseBlock":
                        input_data: dict[str, Any] = {}
                        if hasattr(block, "input"):
                            input_data = (
                                block.input
                                if isinstance(block.input, dict)
                                else {}
                            )
                        blocks.append(
                            {
                                "type": "tool_use",
                                "name": getattr(block, "name", ""),
                                "id": getattr(block, "id", ""),
                                "input": input_data,
                            }
                        )
                    elif block_type == "ToolResultBlock":
                        blocks.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": getattr(block, "tool_use_id", ""),
                                "content": ClaudeAgentGateway._normalize_tool_result_content(getattr(block, "content", None)),
                                "is_error": getattr(block, "is_error", False),
                            }
                        )
                    elif block_type == "ThinkingBlock":
                        blocks.append({"type": "thinking", "thinking": getattr(block, "thinking", "")})
            result: dict[str, Any] = {
                "message_type": "assistant",
                "content": {"blocks": blocks},
            }
            # Extract per-turn usage for accurate context window estimation.
            # AssistantMessage.usage is per API call (not cumulative), so it
            # reflects the actual context window size at this turn.
            usage = getattr(msg, "usage", None)
            if usage:
                if not isinstance(usage, dict):
                    usage = {
                        "input_tokens": getattr(usage, "input_tokens", 0),
                        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
                        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
                    }
                it = usage.get("input_tokens", 0)
                cc = usage.get("cache_creation_input_tokens", 0)
                cr = usage.get("cache_read_input_tokens", 0)
                per_turn = it + cc + cr
                if per_turn > 0:
                    result["context_input_tokens"] = per_turn
            return result


        if msg_type == "UserMessage":
            results: list[dict[str, Any]] = []
            if hasattr(msg, "content") and msg.content:
                content_list = (
                    msg.content if isinstance(msg.content, list) else [msg.content]
                )
                for item in content_list:
                    item_type = item.__class__.__name__
                    if item_type == "ToolResultBlock":
                        results.append(
                            {
                                "tool_use_id": getattr(item, "tool_use_id", ""),
                                "content": ClaudeAgentGateway._normalize_tool_result_content(getattr(item, "content", None)),
                                "is_error": getattr(item, "is_error", False),
                            }
                        )
                    elif isinstance(item, dict) and item.get("type") == "tool_result":
                        results.append(
                            {
                                "tool_use_id": item.get("tool_use_id", ""),
                                "content": ClaudeAgentGateway._normalize_tool_result_content(item.get("content")),
                                "is_error": item.get("is_error", False),
                            }
                        )
            return {
                "message_type": "tool_result",
                "content": {"results": results},
            }

        if msg_type == "ResultMessage":
            usage = getattr(msg, "usage", None) or {}
            if not isinstance(usage, dict):
                # Safety: handle case where usage is an object with attributes
                usage = {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
                }
            # Context window consumption = input + cache_creation + cache_read
            # (aligned with claude-hud's getTotalTokens logic — output is NOT context)
            input_tokens = usage.get("input_tokens", 0)
            cache_creation = usage.get("cache_creation_input_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            context_tokens = input_tokens + cache_creation + cache_read
            output_tokens = usage.get("output_tokens", 0)
            return {
                "message_type": "result",
                "content": {
                    "text": getattr(msg, "result", "") or "",
                    "duration_ms": getattr(msg, "duration_ms", 0),
                    "duration_api_ms": getattr(msg, "duration_api_ms", 0),
                    "num_turns": getattr(msg, "num_turns", 0),
                    "is_error": getattr(msg, "is_error", False),
                    "total_cost_usd": getattr(msg, "total_cost_usd", 0),
                    "stop_reason": getattr(msg, "stop_reason", None),
                    "usage": {
                        "input_tokens": context_tokens,
                        "output_tokens": output_tokens,
                    },
                },
                "input_tokens": context_tokens,
                "output_tokens": output_tokens,
            }

        return None

    @staticmethod
    def _extract_system_message(msg: _SystemMessage) -> dict[str, Any]:
        """Extract only key info from SystemMessage to convey execution rhythm.

        For task-related subtypes, extract structured fields.
        For other subtypes, only include subtype as a brief indicator.
        """
        subtype = getattr(msg, "subtype", "")

        if isinstance(msg, TaskStartedMessage):
            return {
                "message_type": "system",
                "content": {
                    "subtype": subtype,
                    "task_id": msg.task_id,
                    "description": msg.description,
                },
            }

        if isinstance(msg, TaskProgressMessage):
            return {
                "message_type": "system",
                "content": {
                    "subtype": subtype,
                    "task_id": msg.task_id,
                    "description": msg.description,
                    "last_tool_name": msg.last_tool_name or "",
                },
            }

        if isinstance(msg, TaskNotificationMessage):
            return {
                "message_type": "system",
                "content": {
                    "subtype": subtype,
                    "task_id": msg.task_id,
                    "status": msg.status,
                    "summary": msg.summary,
                },
            }

        # Other system messages: only subtype for rhythm awareness
        return {
            "message_type": "system",
            "content": {
                "subtype": subtype,
            },
        }
