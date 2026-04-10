from __future__ import annotations

import asyncio
import logging
import os

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
    ) -> None:
        self._session_repository = session_repository
        self._claude_agent_gateway = claude_agent_gateway
        self._connection_manager = connection_manager
        self._claude_session_manager = claude_session_manager
        self._on_assistant_response = on_assistant_response
        self._on_user_message = on_user_message
        self._project_repository = project_repository
        self._im_unbind_fn = im_unbind_fn

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

        await self._session_repository.save(session)

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
        await self._session_repository.save(session)
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
                # Restore sdk_session_id — connection stays alive after /clear
                if new_sdk_sid:
                    session.update_sdk_session_id(new_sdk_sid)
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

        await self._session_repository.save(session)
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

        logger.info(
            "[session=%s] 收到用户请求",
            command.session_id,
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
            await self._session_repository.save(session)
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

        except Exception as e:
            logger.error(
                "[session=%s] Claude查询失败: %s",
                command.session_id,
                str(e),
                exc_info=True,
            )
            session.fail_query(error_message=str(e))
            await self._connection_manager.broadcast(
                session.session_id,
                {"event": "error", "message": str(e)},
            )

        finally:
            self._claude_agent_gateway.mark_idle(command.session_id)
            # Use a fresh DB session to ensure final save succeeds even if
            # the original connection was lost during a long-running query
            try:
                await self._session_repository.save(session)
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

    async def _consume_message_stream(
        self, session: "Session", msg_stream: "AsyncIterator[dict]"
    ) -> None:
        """Iterate over the message stream, persist messages and broadcast to WS."""
        async for msg_dict in msg_stream:
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
        disconnected and not actively querying (e.g. after a server restart),
        transitions it to idle. Skips correction if a query is in progress
        (e.g., triggered from IM while SDK is reconnecting).
        """
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if session.is_running and not self._claude_agent_gateway.is_connected(session_id):
            if self._claude_agent_gateway.is_active(session_id):
                return
            session.complete_query()
            await self._session_repository.save(session)

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
        """Cancel an active Claude query via SDK interrupt.

        Sends an interrupt signal immediately, with a short timeout.
        If interrupt times out, falls back to disconnect to force-stop.
        The WS handler fires this as a background task so the UI is
        immediately unblocked.
        """
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
        await self._session_repository.save(session)

    async def set_permission_mode(self, session_id: str, mode: str) -> None:
        """Change the permission mode for an active session.

        The mode is always saved in the gateway so it takes effect on the
        next connect, even if no SDK client is currently connected.
        """
        await self._claude_agent_gateway.set_permission_mode(session_id, mode)

    async def get_models(self) -> list[dict]:
        """Get available models from Claude Code."""
        return await self._claude_agent_gateway.get_models()

    async def resolve_user_response(self, session_id: str, response_data: dict) -> bool:
        """Resolve a pending user response (choice answer or permission decision)."""
        return await self._claude_agent_gateway.resolve_user_response(session_id, response_data)

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
        await self._session_repository.save(session)

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
        await self._session_repository.save(session)

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
            await self._session_repository.save(session)
            all_messages = [{"type": msg.message_type.value, "content": msg.content} for msg in session.messages]
            await self._connection_manager.broadcast(
                session_id,
                {
                    "event": "connected",
                    "session": self._session_to_dict(session),
                    "messages": all_messages,
                },
            )
