from __future__ import annotations

import asyncio
import logging
import os
import re

from domain.shared.async_utils import safe_create_task
from collections.abc import Awaitable, Callable
from typing import Any

from application.session.command.clear_context_command import ClearContextCommand
from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.import_claude_session_command import ImportClaudeSessionCommand
from application.session.command.run_query_command import RunQueryCommand
from domain.session.acl.claude_agent_gateway import ClaudeAgentGateway
from domain.session.acl.connection_manager import ConnectionManager
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from domain.session.model.usage import Usage
from domain.session.service.message_conversion_service import MessageConversionService
from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.session.repository.session_repository import SessionRepository
from domain.session.model.session_audit_event import SessionAuditEvent
from domain.session.repository.session_audit_event_repository import SessionAuditEventRepository
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


class SessionApplicationService:

    def __init__(
        self,
        session_repository: SessionRepository,
        claude_agent_gateway: ClaudeAgentGateway,
        connection_manager: ConnectionManager,
        claude_session_manager: Any = None,
        on_assistant_response: Callable[[str, str], Awaitable[None]] | None = None,
        on_user_message: Callable[[str, str], Awaitable[None]] | None = None,
        project_repository: ProjectRepository | None = None,
        im_unbind_fn: Callable[[str], Awaitable[None]] | None = None,
        audit_event_repository: SessionAuditEventRepository | None = None,
        audit_event_recorder: Callable[[SessionAuditEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._session_repository = session_repository
        self._claude_agent_gateway = claude_agent_gateway
        self._connection_manager = connection_manager
        self._claude_session_manager = claude_session_manager
        self._on_assistant_response = on_assistant_response
        self._on_user_message = on_user_message
        self._project_repository = project_repository
        self._im_unbind_fn = im_unbind_fn
        self._audit_event_repository = audit_event_repository
        self._audit_event_recorder = audit_event_recorder
        # Latest-wins queue: at most one pending message per session
        self._queued_messages: dict[str, RunQueryCommand] = {}
        # Tracks sessions that have been cancelled (to prevent retry in run_claude_query)
        self._cancelled_sessions: set[str] = set()
        max_concurrent = int(os.getenv("SESSION_MAX_CONCURRENT_QUERIES", "2"))
        self._query_semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self._waiting_for_slot: set[str] = set()

    def is_waiting_for_slot(self, session_id: str) -> bool:
        return session_id in self._waiting_for_slot

    async def submit_query(self, command: RunQueryCommand) -> None:
        if self._query_semaphore.locked():
            self._waiting_for_slot.add(command.session_id)
            await self._connection_manager.broadcast(
                command.session_id,
                {"event": "resource_waiting", "status": "waiting_slot"},
            )
            await self._record_audit_event(
                command.session_id,
                "resource_waiting",
                payload={"reason": "concurrency_limit"},
            )
        async with self._query_semaphore:
            self._waiting_for_slot.discard(command.session_id)
            await self.run_claude_query(command)

    async def _save_session(self, session: Session, *, commit: bool = False) -> None:
        """Persist a session and optionally commit immediately.

        WebSocket handlers and background tasks reuse a long-lived DB session.
        In those paths we must commit after writes so row locks are released
        promptly instead of being held until the WebSocket disconnects.
        """
        await self._session_repository.save(session)
        if commit:
            await self._session_repository.commit()

    async def _record_audit_event(
        self,
        session_id: str,
        event_type: str,
        actor: str = "system",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._audit_event_repository is None and self._audit_event_recorder is None:
            return
        try:
            event = SessionAuditEvent.create(
                session_id=session_id,
                event_type=event_type,
                actor=actor,
                payload=payload,
            )
            if self._audit_event_recorder is not None:
                await self._audit_event_recorder(event)
            elif self._audit_event_repository is not None:
                await self._audit_event_repository.save(event)
        except Exception:
            logger.warning(
                "[session=%s] audit event write failed: %s",
                session_id,
                event_type,
                exc_info=True,
            )

    async def list_audit_events(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[SessionAuditEvent]:
        if self._audit_event_repository is None:
            return []
        return await self._audit_event_repository.find_by_session_id(
            session_id=session_id,
            limit=max(1, min(limit, 500)),
        )

    async def _set_cancel_requested(self, session_id: str, requested: bool) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if requested:
            session.mark_cancel_requested()
        else:
            session.clear_cancel_requested()
        await self._save_session(session, commit=True)

    async def _set_queued_command(
        self,
        session_id: str,
        command: RunQueryCommand | None,
    ) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if command is None:
            session.clear_queued_command()
        else:
            session.update_queued_command(command.prompt, command.image_paths)
        await self._save_session(session, commit=True)

    @staticmethod
    def _recovery_to_dict(session: Session) -> dict[str, Any]:
        pending_request = session.pending_request_context
        queued_command = session.queued_command

        pending_summary = None
        if pending_request:
            tool_name = pending_request.get("tool_name", "")
            if tool_name == "AskUserQuestion":
                pending_summary = {
                    "interaction_type": "user_choice",
                    "tool_name": tool_name,
                    "questions": pending_request.get("questions", []),
                }
            else:
                pending_summary = {
                    "interaction_type": "permission",
                    "tool_name": tool_name,
                    "tool_input": pending_request.get("tool_input", ""),
                }

        queued_summary = None
        if queued_command:
            queued_summary = {
                "prompt": queued_command.get("prompt", ""),
                "image_count": len(queued_command.get("image_paths", [])),
            }

        return {
            "pending_request": pending_summary,
            "queued_command": queued_summary,
            "cancel_requested": session.cancel_requested,
        }

    @staticmethod
    def _artifact_candidates_from_value(value: Any) -> list[str]:
        candidates: list[str] = []
        if isinstance(value, str):
            candidates.extend(
                match.group(0).rstrip('.,:;)]}"\'')
                for match in re.finditer(r"(?:/|~/?|\./|\.\./)[^\s`'\"<>]+", value)
            )
        elif isinstance(value, dict):
            for key, nested in value.items():
                if key in {"file_path", "path", "paths", "filename", "output_file"}:
                    candidates.extend(SessionApplicationService._artifact_candidates_from_value(nested))
                elif isinstance(nested, (dict, list)):
                    candidates.extend(SessionApplicationService._artifact_candidates_from_value(nested))
        elif isinstance(value, list):
            for item in value:
                candidates.extend(SessionApplicationService._artifact_candidates_from_value(item))
        return candidates

    @staticmethod
    def _artifact_label(path: str) -> str:
        clean = path.rstrip("/")
        return clean.split("/")[-1] or clean

    async def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        session = await self.get_session(session_id)
        artifacts: list[dict[str, Any]] = []
        seen: set[str] = set()

        for index, message in enumerate(session.messages):
            content = message.content
            for path in self._artifact_candidates_from_value(content):
                if path in seen:
                    continue
                seen.add(path)
                artifacts.append({
                    "id": f"artifact-{len(artifacts) + 1}",
                    "path": path,
                    "label": self._artifact_label(path),
                    "source_message_index": index,
                    "message_type": message.message_type.value,
                })

        return artifacts

    @staticmethod
    def _session_to_dict(session: Session) -> dict[str, Any]:
        """Convert session to dict for WS broadcast (avoids ohs layer dependency)."""
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "model": session.model,
            "status": session.status.value,
            "message_count": session.message_count,
            "usage": {
                "input_tokens": session.usage.input_tokens,
                "output_tokens": session.usage.output_tokens,
            },
            "last_input_tokens": session.last_input_tokens,
            "project_dir": session.project_dir,
            "name": session.name,
            "sdk_session_id": session.sdk_session_id,
            "updated_time": session.updated_time.isoformat() if session.updated_time else None,
            "git_branch": "",
            "recovery": SessionApplicationService._recovery_to_dict(session),
        }

    async def create_session(self, command: CreateSessionCommand) -> Session:
        """Create a new Claude Code interaction session.

        If project_dir is provided, uses it directly.
        If project_id is provided (without project_dir), resolves dir from project.
        Otherwise falls back to PROJECTS_ROOT_DIR.
        """
        project_dir = command.project_dir

        # Resolve project_dir from project when not explicitly provided
        if not project_dir and command.project_id and self._project_repository:
            project = await self._project_repository.find_by_id(command.project_id)
            if project:
                project_dir = project.dir_path

        if not project_dir:
            projects_root = os.getenv(
                "PROJECTS_ROOT_DIR", os.path.expanduser("~/claude-projects")
            )
            dir_name = command.name.strip() if command.name else "default"
            project_dir = os.path.join(projects_root, dir_name)

        os.makedirs(project_dir, exist_ok=True)

        session = Session.create(model=command.model, project_id=command.project_id, project_dir=project_dir)

        if command.name:
            session.rename(command.name.strip())

        await self._save_session(session, commit=True)

        # Pre-set bypass permissions for new sessions so the first query
        # doesn't fall back to the env-level default (which may be acceptEdits)
        await self._claude_agent_gateway.set_permission_mode(
            session.session_id, "bypassPermissions"
        )

        return session

    async def get_session(self, session_id: str) -> Session:
        """Get session details by session_id."""
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        return session

    async def list_sessions(self) -> list[Session]:
        """List all sessions."""
        return await self._session_repository.find_all()

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by session_id.

        Also disconnects the SDK client, unbinds IM if bound,
        and removes Claude Code JSONL files.
        """
        # Get session info before deletion for project_dir
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")

        project_dir = session.project_dir

        # Unbind IM channel if bound (best-effort)
        if self._im_unbind_fn:
            try:
                await self._im_unbind_fn(session_id)
            except Exception:
                logger.warning("[session=%s] IM unbind failed during delete", session_id)

        # Disconnect SDK client if connected
        await self._claude_agent_gateway.disconnect(session_id)

        # Delete Claude Code JSONL session files
        if project_dir:
            self._claude_agent_gateway.delete_session_files(
                session_id, project_dir, sdk_session_id=session.sdk_session_id,
            )

        # Clean up all tracked gateway state for this session
        self._claude_agent_gateway.cleanup_session(session_id)

        removed = await self._session_repository.remove(session_id)
        if not removed:
            raise BusinessException("Session not found")
        await self._session_repository.commit()
        return True

    async def batch_delete_sessions(self, session_ids: list[str]) -> int:
        """Delete multiple sessions. Returns the number successfully deleted."""
        deleted = 0
        for sid in session_ids:
            try:
                await self.delete_session(sid)
                deleted += 1
            except Exception:
                logger.warning("batch delete: failed to delete session %s", sid, exc_info=True)
        return deleted

    async def rename_session(self, session_id: str, name: str) -> Session:
        """Rename a session."""
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        session.rename(name)
        await self._save_session(session, commit=True)
        return session

    async def clear_context(self, command: ClearContextCommand) -> None:
        """Clear session context via SDK /clear command or disconnect fallback.

        If SDK is connected, sends /clear slash command so Claude Code
        properly resets its internal context. Otherwise disconnects and
        cleans up locally.
        """
        session = await self._session_repository.find_by_id(command.session_id)
        if session is None:
            raise BusinessException("Session not found")

        if self._claude_agent_gateway.is_connected(command.session_id):
            # Send /clear to Claude Code — it resets context server-side
            try:
                clear_input_tokens = 0
                new_sdk_sid = None
                async for msg_dict in self._claude_agent_gateway.send_query(
                    command.session_id, prompt="/clear",
                ):
                    if "input_tokens" in msg_dict:
                        clear_input_tokens = msg_dict["input_tokens"]
                    sdk_sid = msg_dict.get("sdk_session_id")
                    if sdk_sid:
                        new_sdk_sid = sdk_sid

                session.clear_context()
                # Restore sdk_session_id — connection stays alive after /clear.
                # Prefer the sid from /clear response; fall back to gateway cache.
                restored_sid = new_sdk_sid or self._claude_agent_gateway.get_cached_sdk_session_id(command.session_id)
                if restored_sid:
                    session.update_sdk_session_id(restored_sid)
                # Write back last_input_tokens from the /clear response so
                # the frontend context bar reflects the post-clear state.
                if clear_input_tokens > 0:
                    session.update_last_input_tokens(clear_input_tokens)
                logger.info(
                    "[session=%s] /clear completed, last_input_tokens=%d",
                    command.session_id,
                    clear_input_tokens,
                )
            except Exception as e:
                logger.warning(
                    "[session=%s] /clear failed: %s, falling back to disconnect",
                    command.session_id, e,
                )
                await self._claude_agent_gateway.disconnect(command.session_id)
                self._claude_agent_gateway.cleanup_session(command.session_id)
                session.clear_context()
        else:
            # Not connected — just reset locally
            self._claude_agent_gateway.cleanup_session(command.session_id)
            session.clear_context()

        await self._save_session(session, commit=True)
        # Broadcast full session + empty messages so frontend resets context display
        await self._connection_manager.broadcast(
            session.session_id,
            {
                "event": "connected",
                "session": self._session_to_dict(session),
                "messages": [],
            },
        )

    async def run_claude_query(self, command: RunQueryCommand) -> None:
        """Execute a Claude query using persistent SDK connection.

        For the first query, connects to Claude via SDK. For subsequent queries,
        reuses the existing connection.
        """
        session = await self._session_repository.find_by_id(command.session_id)
        if session is None:
            raise BusinessException("Session not found")

        if session.cancel_requested:
            session.clear_cancel_requested()

        logger.info(
            "[session=%s] 收到用户请求",
            command.session_id,
        )

        await self._record_audit_event(
            command.session_id,
            "query_started",
            actor="user",
            payload={
                "image_count": len(command.image_paths),
                "prompt_length": len(command.prompt),
            },
        )

        # Append image file paths to prompt if present
        actual_prompt = command.prompt
        if command.image_paths:
            image_refs = "\n".join(
                f"[Image: {path}]" for path in command.image_paths
            )
            actual_prompt = f"{command.prompt}\n\n{image_refs}"
            logger.info(
                "[session=%s] 附加 %d 张图片到 prompt",
                command.session_id,
                len(command.image_paths),
            )

        session.start_query()
        self._claude_agent_gateway.mark_active(command.session_id)

        # Save user message and broadcast
        user_message = Message.create(
            message_type=MessageType.USER,
            content={"text": actual_prompt},
        )
        session.add_message(user_message)

        # Run DB save + WS broadcast in parallel with SDK connection check
        async def _save_and_broadcast():
            await self._save_session(session, commit=True)
            await self._connection_manager.broadcast(
                session.session_id,
                {
                    "event": "status_change",
                    "status": "running",
                    "prompt": actual_prompt,
                },
            )
            # Sync user message to bound IM channel
            if self._on_user_message:
                safe_create_task(
                    self._fire_user_outbound(session.session_id, actual_prompt),
                )

        async def _prepare_sdk_connection():
            """Check SDK connection state and disconnect if model changed.
            Returns is_connected (bool)."""
            is_connected = self._claude_agent_gateway.is_connected(command.session_id)
            connected_model = self._claude_agent_gateway.get_connected_model(command.session_id)
            if is_connected and connected_model != session.model:
                logger.info(
                    "[session=%s] 模型已变更 (%s -> %s), 断开重连",
                    command.session_id, connected_model, session.model,
                )
                await self._claude_agent_gateway.disconnect(command.session_id)
                return False
            return is_connected

        try:
            # Parallel: DB save + broadcast, SDK connection check
            _, is_connected = await asyncio.gather(
                _save_and_broadcast(),
                _prepare_sdk_connection(),
            )

            msg_stream = None
            if is_connected:
                try:
                    msg_stream = self._claude_agent_gateway.send_query(
                        session_id=command.session_id,
                        prompt=actual_prompt,
                    )
                except Exception as send_err:
                    logger.warning(
                        "[session=%s] send_query 失败 (%s), 回退到 connect",
                        command.session_id,
                        send_err,
                    )
                    await self._claude_agent_gateway.disconnect(command.session_id)
                    msg_stream = None

            if msg_stream is None:
                msg_stream = self._claude_agent_gateway.connect(
                    session_id=command.session_id,
                    model=session.model,
                    prompt=actual_prompt,
                    cwd=session.project_dir,
                    sdk_session_id=session.sdk_session_id,
                )

            try:
                await self._consume_message_stream(session, msg_stream)
            except Exception as stream_err:
                # If cancelled, don't retry — let cancel_query handle cleanup
                if command.session_id in self._cancelled_sessions:
                    logger.info(
                        "[session=%s] 消息流因取消而中断, 跳过重试",
                        command.session_id,
                    )
                    return
                # If send_query's stream fails mid-iteration (e.g. dead CLI process),
                # fall back to a fresh connect
                if is_connected:
                    logger.warning(
                        "[session=%s] 消息流中断 (%s), 重新 connect",
                        command.session_id,
                        stream_err,
                    )
                    await self._claude_agent_gateway.disconnect(command.session_id)
                    msg_stream = self._claude_agent_gateway.connect(
                        session_id=command.session_id,
                        model=session.model,
                        prompt=actual_prompt,
                        cwd=session.project_dir,
                        sdk_session_id=session.sdk_session_id,
                    )
                    await self._consume_message_stream(session, msg_stream)
                else:
                    raise

            # If cancelled during stream consumption, skip normal completion
            if command.session_id in self._cancelled_sessions:
                session.clear_cancel_requested()
                logger.info("[session=%s] 查询被取消, 跳过正常完成流程", command.session_id)
                return

            session.complete_query()

            # Fire outbound IM sync in background (only for web UI path)
            if self._on_assistant_response:
                text = MessageConversionService.extract_assistant_text(session.messages)
                if text:
                    safe_create_task(
                        self._fire_outbound(session.session_id, text),
                    )

            logger.info(
                "[session=%s] 查询完成, usage=%s",
                command.session_id,
                {"input_tokens": session.usage.input_tokens, "output_tokens": session.usage.output_tokens},
            )
            await self._record_audit_event(
                command.session_id,
                "query_finished",
                payload={
                    "input_tokens": session.usage.input_tokens,
                    "output_tokens": session.usage.output_tokens,
                    "message_count": session.message_count,
                },
            )

        except Exception as e:
            # If cancelled, skip error handling — cancel_query handles everything
            if command.session_id in self._cancelled_sessions:
                session.clear_cancel_requested()
                logger.info("[session=%s] 查询异常但已取消, 跳过错误处理", command.session_id)
                return
            logger.error(
                "[session=%s] Claude查询失败: %s",
                command.session_id,
                str(e),
                exc_info=True,
            )
            session.fail_query(error_message=str(e))
            await self._record_audit_event(
                command.session_id,
                "query_failed",
                payload={"error": str(e)[:500]},
            )
            await self._connection_manager.broadcast(
                session.session_id,
                {"event": "error", "message": str(e)},
            )

        finally:
            self._claude_agent_gateway.mark_idle(command.session_id)
            # If cancelled, cancel_query handles save and broadcast
            if command.session_id in self._cancelled_sessions:
                return
            # Use a fresh DB session to ensure final save succeeds even if
            # the original connection was lost during a long-running query
            try:
                await self._save_session(session, commit=True)
            except Exception:
                logger.warning(
                    "[session=%s] final save failed, retrying with fresh DB session",
                    command.session_id, exc_info=True,
                )
                try:
                    from infr.config.database import async_session_factory
                    from infr.repository.session_repository_impl import SessionRepositoryImpl

                    async with async_session_factory() as fresh_db:
                        fresh_repo = SessionRepositoryImpl(fresh_db)
                        await fresh_repo.save(session)
                        await fresh_db.commit()
                except Exception:
                    logger.error(
                        "[session=%s] retry save also failed",
                        command.session_id, exc_info=True,
                    )
            await self._connection_manager.broadcast(
                session.session_id,
                {
                    "event": "status",
                    "session": {
                        "session_id": session.session_id,
                        "project_id": session.project_id,
                        "model": session.model,
                        "status": session.status.value,
                        "message_count": session.message_count,
                        "usage": {
                            "input_tokens": session.usage.input_tokens,
                            "output_tokens": session.usage.output_tokens,
                        },
                        "last_input_tokens": session.last_input_tokens,
                        "project_dir": session.project_dir,
                        "name": session.name,
                        "sdk_session_id": session.sdk_session_id,
                        "updated_time": session.updated_time.isoformat() if session.updated_time else None,
                        "git_branch": "",
                    },
                },
            )

            # Execute queued follow-up message if present
            queued = self._queued_messages.pop(command.session_id, None)
            if queued:
                await self._set_queued_command(command.session_id, None)
                await self._record_audit_event(
                    command.session_id,
                    "queue_started",
                    payload={"prompt_length": len(queued.prompt)},
                )
                logger.info("[session=%s] 执行排队的后续消息", command.session_id)
                safe_create_task(self.submit_query(queued))

    # Maximum seconds to wait for the next message from the Claude stream.
    # If no message arrives within this window AND the CLI process has died,
    # we treat the stream as broken.  The generous timeout avoids false
    # positives during long tool executions (e.g. large file writes).
    _STREAM_MSG_TIMEOUT = 300  # 5 minutes

    async def _consume_message_stream(
        self, session: "Session", msg_stream: "AsyncIterator[dict]"
    ) -> None:
        """Iterate over the message stream, persist messages and broadcast to WS.

        Includes a per-message timeout combined with a CLI process health
        check so the stream never hangs indefinitely when the subprocess
        crashes.
        """
        loop = asyncio.get_event_loop()
        last_save_time = loop.time()
        save_interval = 2.0  # save at most every 2s for cross-session visibility

        aiter = msg_stream.__aiter__()
        while True:
            try:
                msg_dict = await asyncio.wait_for(
                    aiter.__anext__(), timeout=self._STREAM_MSG_TIMEOUT,
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                # Timeout waiting for next message — check if CLI is still alive
                if not self._claude_agent_gateway.is_process_alive(session.session_id):
                    logger.error(
                        "[session=%s] CLI 进程已退出且消息流超时, 终止消费",
                        session.session_id,
                    )
                    raise RuntimeError("Claude CLI process exited unexpectedly")
                # Process is alive but slow (e.g. long tool execution) — keep waiting
                logger.info(
                    "[session=%s] 消息流等待超时但进程仍存活, 继续等待",
                    session.session_id,
                )
                continue
            msg_type_str = msg_dict["message_type"]
            message = MessageConversionService.convert_stream_message(msg_dict)
            if message is None:
                logger.warning(
                    "[session=%s] 未知消息类型: %s, 跳过",
                    session.session_id,
                    msg_type_str,
                )
                continue

            session.add_message(message)

            logger.info(
                "[session=%s] Claude回复 [%s]",
                session.session_id,
                msg_type_str,
            )

            await self._connection_manager.broadcast(
                session.session_id,
                {"event": "message", "data": {"type": message.message_type.value, "content": message.content}},
            )

            # Per-turn context from AssistantMessage — accurate context window size
            if "context_input_tokens" in msg_dict:
                session.update_last_input_tokens(msg_dict["context_input_tokens"])

            if "input_tokens" in msg_dict and "output_tokens" in msg_dict:
                # ResultMessage carries cumulative tokens across all turns.
                # Only use as fallback for context estimation if no per-turn
                # data was provided by AssistantMessage.
                if session.last_input_tokens == 0:
                    num_turns = max(msg_dict.get("num_turns", 1) or 1, 1)
                    if num_turns == 1:
                        session.update_last_input_tokens(msg_dict["input_tokens"])
                    else:
                        estimated = int(msg_dict["input_tokens"] * 2 / (num_turns + 1))
                        session.update_last_input_tokens(estimated)

                # Cumulative usage tracking (for cost / billing display)
                if (
                    session.sdk_session_id
                    and session.usage.input_tokens == 0
                    and session.usage.output_tokens == 0
                ):
                    session.initialize_usage(
                        input_tokens=msg_dict["input_tokens"],
                        output_tokens=msg_dict["output_tokens"],
                    )
                    logger.info(
                        "[session=%s] resume 首次 usage 设定: in=%d, out=%d",
                        session.session_id,
                        msg_dict["input_tokens"],
                        msg_dict["output_tokens"],
                    )
                else:
                    session.update_usage(
                        input_tokens=msg_dict["input_tokens"],
                        output_tokens=msg_dict["output_tokens"],
                    )

            # Capture SDK session_id for resume support
            # Always update: resume may produce a new session_id
            if "sdk_session_id" in msg_dict:
                new_sid = msg_dict["sdk_session_id"]
                if new_sid and new_sid != session.sdk_session_id:
                    session.update_sdk_session_id(new_sid)
                    logger.info(
                        "[session=%s] 更新 SDK session_id: %s",
                        session.session_id,
                        new_sid,
                    )

            # Periodic save: ensure reconnecting clients see recent messages.
            # Uses the same DB session with explicit commit for visibility.
            now = loop.time()
            is_result = msg_type_str == "result"
            if is_result or (now - last_save_time >= save_interval):
                try:
                    await self._save_session(session, commit=True)
                    last_save_time = now
                except Exception:
                    logger.warning(
                        "[session=%s] periodic save failed",
                        session.session_id, exc_info=True,
                    )

    async def _fire_outbound(self, session_id: str, text: str) -> None:
        """Best-effort outbound IM sync — errors are logged, never raised."""
        try:
            await self._on_assistant_response(session_id, text)
        except Exception:
            logger.warning(
                "[session=%s] outbound IM sync failed", session_id, exc_info=True,
            )

    async def _fire_user_outbound(self, session_id: str, text: str) -> None:
        """Best-effort sync of user message to IM channel."""
        try:
            await self._on_user_message(session_id, text)
        except Exception:
            logger.warning(
                "[session=%s] user message IM sync failed", session_id, exc_info=True,
            )

    def is_agent_connected(self, session_id: str) -> bool:
        """Check if the SDK agent client is connected for a session."""
        return self._claude_agent_gateway.is_connected(session_id)

    async def ensure_session_idle(self, session_id: str) -> None:
        """Correct stale 'running' status when the agent is no longer connected.

        Loads the session, and if it is marked as running but the agent is
        disconnected (or the CLI process is dead) and not actively querying
        (e.g. after a server restart or CLI crash), transitions it to idle.
        Skips correction if a query is in progress
        (e.g., triggered from IM while SDK is reconnecting).
        """
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if not session.is_running:
            return
        # Agent is connected AND its process is alive — don't touch
        if (
            self._claude_agent_gateway.is_connected(session_id)
            and self._claude_agent_gateway.is_process_alive(session_id)
        ):
            if self._claude_agent_gateway.is_active(session_id):
                return
        session.complete_query()
        await self._save_session(session, commit=True)

    async def prewarm_connection(self, session_id: str) -> None:
        """Pre-establish SDK connection for a session so first query is faster.

        Only works for sessions with an sdk_session_id (previously used).
        Skips silently if session not found, already connected, or no sdk_session_id.
        """
        if self._claude_agent_gateway.is_connected(session_id):
            return

        session = await self._session_repository.find_by_id(session_id)
        if session is None or not session.sdk_session_id:
            return

        try:
            await self._claude_agent_gateway.open_connection(
                session_id=session_id,
                model=session.model,
                cwd=session.project_dir,
                sdk_session_id=session.sdk_session_id,
            )
            logger.info("[session=%s] SDK 连接预热完成", session_id)
        except Exception as e:
            logger.warning("[session=%s] SDK 连接预热失败: %s", session_id, e)

    async def cancel_query(self, session_id: str) -> None:
        """Cancel an active Claude query via SDK interrupt, then rewind.

        1. Marks session as cancelled (prevents retry in run_claude_query).
        2. Clears queued messages.
        3. Sends interrupt to SDK with 3s timeout, disconnect fallback.
        4. Waits briefly for run_claude_query to finish.
        5. Sends /rewind to Claude Code to undo the last turn.
        6. Rewinds domain session (removes last user msg + responses).
        7. Broadcasts rewind event with the original prompt.
        """
        self._cancelled_sessions.add(session_id)
        self._waiting_for_slot.discard(session_id)
        await self._record_audit_event(session_id, "cancel_requested", actor="user")
        await self._set_cancel_requested(session_id, True)
        await self.clear_queued_message(session_id)

        # Step 0: Cancel any pending user response (permission/choice) so the
        # query's can_use_tool callback stops blocking and the stream can finish.
        await self._claude_agent_gateway.cancel_pending_response(session_id)

        # Step 1: Interrupt the running query
        try:
            await asyncio.wait_for(
                self._claude_agent_gateway.interrupt(session_id),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[session=%s] interrupt timed out after 3s, falling back to disconnect",
                session_id,
            )
            await self._claude_agent_gateway.disconnect(session_id)
        except RuntimeError:
            logger.info("[session=%s] cancel_query: no active connection", session_id)

        # Step 2: Wait for run_claude_query to finish its finally block
        for _ in range(20):
            if not self._claude_agent_gateway.is_active(session_id):
                break
            await asyncio.sleep(0.1)

        # Step 3: Send /rewind to Claude Code to undo the last turn
        if self._claude_agent_gateway.is_connected(session_id):
            try:
                async for _ in self._claude_agent_gateway.send_query(session_id, "/rewind"):
                    pass
                logger.info("[session=%s] /rewind sent successfully", session_id)
            except Exception as e:
                logger.warning("[session=%s] /rewind failed: %s", session_id, e)

        # Step 4: Rewind domain session
        session = await self._session_repository.find_by_id(session_id)
        prompt = ""
        if session is not None:
            try:
                prompt = session.cancel_query()
                await self._save_session(session, commit=True)
            except ValueError:
                # Session not in RUNNING state — already transitioned
                # Still try to find last user message for prompt restoration
                for msg in reversed(session.messages):
                    if msg.message_type.value == "user":
                        prompt = msg.content.get("text", "")
                        break

            # Broadcast rewind: full session state + messages + original prompt
            all_messages = [
                {"type": msg.message_type.value, "content": msg.content}
                for msg in session.messages
            ]
            await self._connection_manager.broadcast(
                session_id,
                {
                    "event": "cancel_rewind",
                    "prompt": prompt,
                    "session": self._session_to_dict(session),
                    "messages": all_messages,
                },
            )
        else:
            # Session not found, just broadcast idle
            await self._connection_manager.broadcast(
                session_id,
                {"event": "status_change", "status": "idle"},
            )

        self._cancelled_sessions.discard(session_id)
        await self._set_cancel_requested(session_id, False)
        await self._record_audit_event(
            session_id,
            "cancel_completed",
            payload={"restored_prompt_length": len(prompt)},
        )

    # ── Message queue (latest-wins) ───────────────────────────

    async def queue_message(self, session_id: str, command: RunQueryCommand) -> None:
        """Queue a follow-up message to run after the current query finishes.

        Latest-wins: only the most recent queued message per session is kept.
        """
        previous = self._queued_messages.get(session_id)
        self._queued_messages[session_id] = command
        await self._set_queued_command(session_id, command)
        if previous is not None:
            await self._record_audit_event(
                session_id,
                "queue_dropped",
                payload={"prompt_length": len(previous.prompt)},
            )
        await self._record_audit_event(
            session_id,
            "queue_enqueued",
            actor="user",
            payload={
                "prompt_length": len(command.prompt),
                "image_count": len(command.image_paths),
            },
        )
        logger.info("[session=%s] 消息已排队 (latest-wins)", session_id)

    async def clear_queued_message(self, session_id: str) -> None:
        """Clear any queued message for a session (e.g. on cancel)."""
        removed = self._queued_messages.pop(session_id, None)
        await self._set_queued_command(session_id, None)
        if removed:
            logger.info("[session=%s] 已清除排队消息", session_id)

    def has_queued_message(self, session_id: str) -> bool:
        return session_id in self._queued_messages

    async def disconnect_session(self, session_id: str) -> None:
        """Disconnect the SDK client for a session."""
        await self._claude_agent_gateway.disconnect(session_id)

    async def set_model(self, session_id: str, model: str) -> None:
        """Change the model for an active session.

        Updates both the SDK client and the persisted session model.
        """
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        # Update SDK client if connected
        if self._claude_agent_gateway.is_connected(session_id):
            await self._claude_agent_gateway.set_model(session_id, model)
        # Update domain model and persist
        session.change_model(model)
        await self._save_session(session, commit=True)

    async def set_permission_mode(self, session_id: str, mode: str) -> None:
        """Change the permission mode for an active session.

        The mode is always saved in the gateway so it takes effect on the
        next connect, even if no SDK client is currently connected.
        """
        await self._claude_agent_gateway.set_permission_mode(session_id, mode)
        await self._record_audit_event(
            session_id,
            "permission_mode_changed",
            actor="user",
            payload={"mode": mode},
        )

    async def get_models(self) -> list[dict]:
        """Get available models from Claude Code."""
        return await self._claude_agent_gateway.get_models()

    async def resolve_user_response(self, session_id: str, response_data: dict) -> bool:
        """Resolve a pending user response (choice answer or permission decision)."""
        resolved = await self._claude_agent_gateway.resolve_user_response(session_id, response_data)
        if resolved:
            await self._record_audit_event(
                session_id,
                "user_response_resolved",
                actor="user",
                payload={"response_keys": sorted(response_data.keys())},
            )
        return resolved

    async def commit(self) -> None:
        """Commit the underlying DB session."""
        await self._session_repository.commit()

    async def close(self) -> None:
        """Close the underlying DB session."""
        await self._session_repository.close()

    async def import_claude_session(self, command: ImportClaudeSessionCommand) -> Session:
        """Import a Claude Code session into MySQL.

        Reads CC session messages via SDK, converts to VP Message format,
        creates a new VP Session, and saves to MySQL.
        """
        if self._claude_session_manager is None:
            raise BusinessException("Claude session manager not available")

        # Idempotency check: return existing VP session if already imported
        existing = await self._session_repository.find_by_sdk_session_id(
            command.claude_session_id
        )
        if existing is not None:
            return existing

        # 1. Read CC session messages
        cc_messages = self._claude_session_manager.get_claude_session_messages(
            session_id=command.claude_session_id,
            directory=command.cwd,
        )

        if not cc_messages:
            raise BusinessException("No messages found in Claude Code session")

        # 2. Convert message format
        pf_messages = MessageConversionService.convert_cc_messages(cc_messages)

        # 3. Resolve project for cwd (find existing or create new, transactional)
        project_dir = command.cwd or ""
        project_id = ""
        if project_dir and self._project_repository:
            project_id = await self._ensure_project_for_dir(project_dir)

        # 4. Create VP Session
        session = Session.create(
            model=os.getenv("DEFAULT_MODEL", "claude-opus-4-6"),
            project_id=project_id,
            project_dir=project_dir,
        )

        if command.name:
            session.rename(command.name[:200])

        for msg in pf_messages:
            session.add_message(msg)

        # Mark as continued conversation so next query uses connect() with cwd
        session = Session.reconstitute(
            session_id=session.session_id,
            model=session.model,
            status=session.status,
            messages=session.messages,
            usage=session.usage,
            continue_conversation=True,
            project_id=session.project_id,
            project_dir=session.project_dir,
            name=session.name,
            sdk_session_id=command.claude_session_id,
            updated_time=session.updated_time,
        )

        # Add a synthetic result message so that queryHistory is populated on load
        session.add_message(Message.create(
            message_type=MessageType.RESULT,
            content={
                "text": "(imported from Claude Code)",
                "duration_ms": 0,
                "duration_api_ms": 0,
                "num_turns": len([m for m in pf_messages if m.message_type == MessageType.USER]),
                "is_error": False,
                "total_cost_usd": 0,
                "stop_reason": "import",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        ))

        # 4. Save to MySQL
        await self._save_session(session, commit=True)

        logger.info(
            "[import] CC session %s -> VP session %s, %d messages",
            command.claude_session_id,
            session.session_id,
            len(pf_messages),
        )

        return session

    async def _ensure_project_for_dir(self, dir_path: str) -> str:
        """Find or create a project for the given directory path.

        Runs within the current transaction — if the project already exists,
        returns its id; otherwise creates a new one and returns the new id.
        """
        existing = await self._project_repository.find_by_dir_path(dir_path)
        if existing:
            return existing.id
        name = os.path.basename(dir_path.rstrip("/")) or dir_path
        project = Project.create(name=name, dir_path=dir_path)
        await self._project_repository.save(project)
        logger.info(
            "[import] Auto-created project: id=%s, name=%s, dir=%s",
            project.id, project.name, dir_path,
        )
        return project.id

    async def compact_session(self, session_id: str) -> None:
        """Compact session context to reduce token usage.

        Calls Claude Agent SDK compact functionality, replaces messages
        and usage with the compacted result.
        """
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")

        if not self._claude_agent_gateway.is_connected(session_id):
            raise BusinessException("Session is not connected, cannot compact")

        session.start_compact()
        self._claude_agent_gateway.mark_active(session_id)
        await self._save_session(session, commit=True)

        await self._connection_manager.broadcast(
            session_id,
            {"event": "status_change", "status": "compacting"},
        )

        try:
            # Gateway compact() sends /compact as a query — collect all response messages
            compact_messages: list[dict] = []
            compact_usage: dict = {"input_tokens": 0, "output_tokens": 0}

            async for msg_dict in self._claude_agent_gateway.compact(session_id):
                msg_type_str = msg_dict.get("message_type", "")
                if msg_type_str:
                    compact_messages.append(msg_dict)
                if "input_tokens" in msg_dict and "output_tokens" in msg_dict:
                    compact_usage = {
                        "input_tokens": msg_dict["input_tokens"],
                        "output_tokens": msg_dict["output_tokens"],
                    }

            messages = [
                Message.create(
                    message_type=MessageType(m["message_type"]),
                    content=m["content"],
                )
                for m in compact_messages
            ]

            usage = Usage(
                input_tokens=compact_usage["input_tokens"],
                output_tokens=compact_usage["output_tokens"],
            )

            session.complete_compact(messages, usage)

            # /compact's input_tokens reflects the OLD context size before
            # compaction.  We cannot accurately measure the new context size
            # without sending a real query (which would consume tokens and
            # pollute history).  Instead, estimate: compacted context is
            # roughly 10-20% of the original.  Use 15% as a reasonable middle
            # ground so the progress bar gives useful feedback.
            if compact_usage["input_tokens"] > 0:
                estimated_post = int(compact_usage["input_tokens"] * 0.15)
                session.update_last_input_tokens(estimated_post)
                logger.info(
                    "[session=%s] post-compact context estimated: %d tokens (15%% of %d)",
                    session_id, estimated_post, compact_usage["input_tokens"],
                )

        except Exception as e:
            logger.error(
                "[session=%s] compact failed: %s",
                session_id,
                str(e),
                exc_info=True,
            )
            session.fail_compact()
            await self._connection_manager.broadcast(
                session_id,
                {"event": "error", "message": str(e)},
            )

        finally:
            self._claude_agent_gateway.mark_idle(session_id)
            await self._save_session(session, commit=True)
            all_messages = [{"type": msg.message_type.value, "content": msg.content} for msg in session.messages]
            await self._connection_manager.broadcast(
                session_id,
                {
                    "event": "connected",
                    "session": self._session_to_dict(session),
                    "messages": all_messages,
                },
            )
