from __future__ import annotations

import logging
import os

from application.git_helpers import get_current_git_branch as _get_current_git_branch
from domain.shared.async_utils import safe_create_task
from collections.abc import Awaitable, Callable
from typing import Any

from application.session.command.clear_context_command import ClearContextCommand
from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.import_claude_session_command import ImportClaudeSessionCommand
from application.session.command.run_query_command import RunQueryCommand
from application.session.session_run_timeline_service import SessionRunTimelineService
from application.session.session_timeline_event_service import SessionTimelineEventService
from domain.session.acl.claude_agent_gateway import ClaudeAgentGateway
from domain.session.acl.connection_manager import ConnectionManager
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from domain.session.model.usage import Usage
from domain.session.service.message_conversion_service import MessageConversionService
from application.session.session_presenter import SessionPresenter
from application.session.session_observability_recorder import SessionObservabilityRecorder
from application.session.session_stream_consumer import SessionStreamConsumer
from application.session.session_query_engine import SessionQueryEngine
from domain.project.model.project import Project
from domain.session.service.sdk_session_binding_service import SdkSessionBindingService
from domain.project.repository.project_repository import ProjectRepository
from domain.session.repository.session_repository import SessionRepository
from domain.session.acl.claude_session_manager import ClaudeSessionManager
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
        claude_session_manager: ClaudeSessionManager | None = None,
        on_assistant_response: Callable[[str, str], Awaitable[None]] | None = None,
        on_user_message: Callable[[str, str], Awaitable[None]] | None = None,
        project_repository: ProjectRepository | None = None,
        im_unbind_fn: Callable[[str], Awaitable[None]] | None = None,
        audit_event_repository: SessionAuditEventRepository | None = None,
        audit_event_recorder: Callable[[SessionAuditEvent], Awaitable[None]] | None = None,
        usage_recorder: Callable[[str, str, str, int, int, int, int], Awaitable[None]] | None = None,
        timeline_service: SessionRunTimelineService | None = None,
        timeline_event_service: SessionTimelineEventService | None = None,
        session_service_factory: Callable[[], Awaitable["SessionApplicationService"]] | None = None,
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
        self._session_service_factory = session_service_factory
        self._recorder = SessionObservabilityRecorder(
            audit_event_repository=audit_event_repository,
            audit_event_recorder=audit_event_recorder,
            usage_recorder=usage_recorder,
            timeline_service=timeline_service,
            timeline_event_service=timeline_event_service,
        )
        self._binding_service = SdkSessionBindingService(session_repository)
        self._stream_consumer = SessionStreamConsumer(
            recorder=self._recorder,
            claude_agent_gateway=claude_agent_gateway,
            connection_manager=connection_manager,
            save_session_fn=self._save_session,
            accept_sdk_session_id_fn=self._accept_or_reject_sdk_session_id,
            cancelled_sessions=SessionQueryEngine._cancelled_sessions,
        )
        self._query_engine = SessionQueryEngine(
            session_repository=session_repository,
            claude_agent_gateway=claude_agent_gateway,
            connection_manager=connection_manager,
            recorder=self._recorder,
            stream_consumer=self._stream_consumer,
            save_session_fn=self._save_session,
            reconnect_db_session_fn=self._reconnect_db_session,
            accept_or_reject_sdk_session_id_fn=self._accept_or_reject_sdk_session_id,
            resolve_resume_sdk_session_id_fn=self._resolve_resume_sdk_session_id,
            refresh_context_usage_fn=self._refresh_context_usage,
            on_assistant_response=on_assistant_response,
            on_user_message=on_user_message,
            project_repository=project_repository,
            session_service_factory=session_service_factory,
        )

    # ── Query delegation ─────────────────────────────────────

    async def is_waiting_for_slot(self, session_id: str) -> bool:
        return await self._query_engine.is_waiting_for_slot(session_id)

    async def submit_query(self, command: RunQueryCommand) -> None:
        await self._query_engine.submit_query(command)

    async def run_claude_query(self, command: RunQueryCommand) -> None:
        await self._query_engine.run_claude_query(command)

    async def cancel_query(self, session_id: str) -> None:
        await self._query_engine.cancel_query(session_id)

    async def rewind_to_message_id(self, session_id: str, message_id: str) -> None:
        await self._query_engine.rewind_to_message_id(session_id, message_id)

    async def rewind_to_message(self, session_id: str, message_index: int) -> None:
        await self._query_engine.rewind_to_message(session_id, message_index)

    async def queue_message(self, session_id: str, command: RunQueryCommand) -> None:
        await self._query_engine.queue_message(session_id, command)

    async def clear_queued_message(self, session_id: str) -> None:
        await self._query_engine.clear_queued_message(session_id)

    # ── Persistence helpers ──────────────────────────────────

    async def _save_session(self, session: Session, *, commit: bool = False) -> None:
        from sqlalchemy.exc import InterfaceError, OperationalError

        try:
            await self._session_repository.save(session)
            if commit:
                await self._session_repository.commit()
        except (OperationalError, InterfaceError, OSError):
            logger.warning(
                "[session=%s] DB connection lost during save, reconnecting",
                session.session_id if hasattr(session, 'session_id') else '?',
                exc_info=True,
            )
            await self._reconnect_db_session()
            await self._session_repository.save(session)
            if commit:
                await self._session_repository.commit()

    async def _reconnect_db_session(self) -> None:
        from infr.config.database import async_session_factory
        from infr.repository.session_repository_impl import SessionRepositoryImpl

        try:
            await self._session_repository.close()
        except Exception:
            logger.debug("Failed to close old DB session during refresh", exc_info=True)
        new_db_session = async_session_factory()
        self._session_repository = SessionRepositoryImpl(new_db_session)

    # ── SDK session ID management ────────────────────────────

    async def _resolve_resume_sdk_session_id(self, session: Session) -> str:
        result = await self._binding_service.resolve_for_resume(session)
        if not result.accepted and result.conflict_session_id:
            await self._recorder.record_audit_event(
                session.session_id,
                "sdk_session_binding_reset",
                payload={
                    "sdk_session_id": session.sdk_session_id,
                    "conflict_session_id": result.conflict_session_id,
                    "source": "resume",
                },
            )
            logger.error(
                "[session=%s] SDK session binding conflict on resume: owner=%s",
                session.session_id,
                result.conflict_session_id,
                extra={"session_id": session.session_id},
            )
            await self._save_session(session, commit=True)
        return result.resolved_id

    async def _accept_or_reject_sdk_session_id(
        self,
        session: Session,
        new_sdk_session_id: str,
        source: str,
        run_id: str | None = None,
    ) -> bool:
        try:
            result = await self._binding_service.try_bind(session, new_sdk_session_id)
        except Exception:
            await self._reconnect_db_session()
            self._binding_service = SdkSessionBindingService(self._session_repository)
            result = await self._binding_service.try_bind(session, new_sdk_session_id)

        if not result.accepted:
            if result.conflict_session_id:
                await self._recorder.record_audit_event(
                    session.session_id,
                    "sdk_session_binding_conflict",
                    payload={
                        "sdk_session_id": new_sdk_session_id,
                        "conflict_session_id": result.conflict_session_id,
                        "source": source,
                        "run_id": run_id,
                    },
                )
                logger.error(
                    "[session=%s] rejected SDK session_id from %s: sdk_session_id=%s owner=%s",
                    session.session_id,
                    source,
                    new_sdk_session_id,
                    result.conflict_session_id,
                    extra={
                        "session_id": session.session_id,
                        "sdk_session_id": new_sdk_session_id,
                        "run_id": run_id or "-",
                    },
                )
                await self._claude_agent_gateway.disconnect(session.session_id)
                raise RuntimeError("SDK session is already bound to another Velpos session")
            return False

        event_type = {
            "clear": "sdk_session_id_updated_after_clear",
            "rewind": "sdk_session_id_updated_after_rewind",
            "compact": "sdk_session_id_updated_after_compact",
        }.get(source, "sdk_session_id_seen")
        await self._recorder.record_audit_event(
            session.session_id,
            event_type,
            payload={"run_id": run_id, "source": source},
        )
        logger.info(
            "[session=%s] 更新 SDK session_id: %s",
            session.session_id,
            new_sdk_session_id,
        )
        return True

    # ── Observability delegation ─────────────────────────────

    async def list_audit_events(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[SessionAuditEvent]:
        return await self._recorder.list_audit_events(session_id, limit)

    async def list_timeline_events(
        self,
        session_id: str,
        limit: int = 500,
        event_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._recorder.list_timeline_events(session_id, limit, event_types)

    async def list_run_timeline_events(
        self,
        session_id: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        return await self._recorder.list_run_timeline_events(session_id, run_id)

    # ── Artifacts ────────────────────────────────────────────

    async def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        session = await self.get_session(session_id)
        artifacts: list[dict[str, Any]] = []
        seen: set[str] = set()

        for index, message in enumerate(session.messages):
            content = message.content
            for path in SessionPresenter.artifact_candidates_from_value(content):
                if path in seen:
                    continue
                seen.add(path)
                artifacts.append({
                    "id": f"artifact-{len(artifacts) + 1}",
                    "path": path,
                    "label": SessionPresenter.artifact_label(path),
                    "source_message_index": index,
                    "message_type": message.message_type.value,
                })

        return artifacts

    # ── Context usage ────────────────────────────────────────

    async def _refresh_context_usage(self, session: Session) -> bool:
        context_usage = await self._claude_agent_gateway.get_context_usage(session.session_id)
        if not context_usage:
            return False
        total_tokens = context_usage.get("total_tokens", 0)
        if total_tokens <= 0:
            return False
        session.update_last_input_tokens(total_tokens)
        logger.info(
            "[session=%s] live context usage: %d tokens",
            session.session_id,
            total_tokens,
        )
        return True

    # ── Session CRUD ─────────────────────────────────────────

    async def create_session(self, command: CreateSessionCommand) -> Session:
        project_dir = command.project_dir

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

        await self._claude_agent_gateway.set_permission_mode(
            session.session_id, "bypassPermissions"
        )

        safe_create_task(self._bind_sdk_session(session.session_id, session.model, project_dir))

        return session

    async def _bind_sdk_session(self, session_id: str, model: str, cwd: str) -> None:
        from infr.config.database import async_session_factory
        from infr.repository.session_repository_impl import SessionRepositoryImpl

        session_lock = await SessionQueryEngine._session_lock_pool.acquire(session_id)
        try:
            async with session_lock:
                try:
                    await self._claude_agent_gateway.open_fresh_connection(session_id, model, cwd)
                    sdk_session_id = ""
                    async for msg_dict in self._claude_agent_gateway.send_query(session_id, "/status"):
                        sid = msg_dict.get("sdk_session_id")
                        if sid:
                            sdk_session_id = sid
                    if sdk_session_id:
                        async with async_session_factory() as db:
                            repo = SessionRepositoryImpl(db)
                            session = await repo.find_by_id(session_id)
                            if session:
                                session.update_sdk_session_id(sdk_session_id)
                                await repo.save(session)
                                await db.commit()
                        self._claude_agent_gateway.schedule_idle_disconnect(session_id)
                        logger.info("[session=%s] SDK session bound on create: %s", session_id, sdk_session_id)
                except Exception:
                    logger.warning("[session=%s] SDK session pre-bind failed", session_id, exc_info=True)
        finally:
            await SessionQueryEngine._session_lock_pool.unref(session_id)

    async def get_session(self, session_id: str) -> Session:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        return session

    async def list_sessions(self) -> list[Session]:
        return await self._session_repository.find_all()

    async def get_current_git_branch(self, project_dir: str) -> str:
        return await _get_current_git_branch(project_dir)

    async def force_cleanup(self, session_id: str) -> None:
        try:
            await self._claude_agent_gateway.disconnect(session_id)
        except Exception:
            logger.debug("Disconnect failed during force_cleanup for session=%s", session_id, exc_info=True)
        await self._claude_agent_gateway.cleanup_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")

        project_dir = session.project_dir

        if self._im_unbind_fn:
            try:
                await self._im_unbind_fn(session_id)
            except Exception:
                logger.warning("[session=%s] IM unbind failed during delete", session_id)

        await self._claude_agent_gateway.disconnect(session_id)

        if project_dir:
            self._claude_agent_gateway.delete_session_files(
                session_id, project_dir, sdk_session_id=session.sdk_session_id,
            )

        await self._claude_agent_gateway.cleanup_session(session_id)
        await self._query_engine.cleanup_session_state(session_id)

        removed = await self._session_repository.remove(session_id)
        if not removed:
            raise BusinessException("Session not found")
        await self._session_repository.commit()
        return True

    async def batch_delete_sessions(self, session_ids: list[str]) -> int:
        deleted = 0
        for sid in session_ids:
            try:
                await self.delete_session(sid)
                deleted += 1
            except Exception:
                logger.warning("batch delete: failed to delete session %s", sid, exc_info=True)
        return deleted

    async def rename_session(self, session_id: str, name: str) -> Session:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        session.rename(name)
        await self._save_session(session, commit=True)
        return session

    # ── Context management ───────────────────────────────────

    async def clear_context(self, command: ClearContextCommand) -> None:
        session = await self._session_repository.find_by_id(command.session_id)
        if session is None:
            raise BusinessException("Session not found")

        if self._claude_agent_gateway.is_connected(command.session_id):
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
                restored_sid = new_sdk_sid or self._claude_agent_gateway.get_cached_sdk_session_id(command.session_id)
                if restored_sid:
                    await self._accept_or_reject_sdk_session_id(session, restored_sid, "clear")
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
                await self._claude_agent_gateway.cleanup_session(command.session_id)
                session.clear_context()
        else:
            await self._claude_agent_gateway.cleanup_session(command.session_id)
            session.clear_context()

        await self._save_session(session, commit=True)
        await self._connection_manager.broadcast(
            session.session_id,
            {
                "event": "connected",
                "session": SessionPresenter.session_to_dict(session),
                "messages": [],
            },
        )

    # ── Agent state ──────────────────────────────────────────

    def is_agent_connected(self, session_id: str) -> bool:
        return self._claude_agent_gateway.is_connected(session_id)

    def get_agent_state(self, session_id: str) -> str:
        return self._claude_agent_gateway.get_state(session_id)

    def is_waiting_for_user_input(self, session_id: str) -> bool:
        return self._claude_agent_gateway.is_waiting_for_user_input(session_id)

    async def ensure_session_idle(self, session_id: str) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if not session.is_running:
            return
        if (
            self._claude_agent_gateway.is_connected(session_id)
            and self._claude_agent_gateway.is_process_alive(session_id)
        ):
            if self._claude_agent_gateway.is_active(session_id):
                return
        session.complete_query()
        await self._save_session(session, commit=True)

    # ── Connection management ────────────────────────────────

    async def prewarm_connection(self, session_id: str) -> None:
        if self._claude_agent_gateway.is_connected(session_id):
            return

        session = await self._session_repository.find_by_id(session_id)
        if session is None or not session.sdk_session_id:
            return

        try:
            resume_sdk_session_id = await self._resolve_resume_sdk_session_id(session)
            if not resume_sdk_session_id:
                return
            await self._claude_agent_gateway.open_connection(
                session_id=session_id,
                model=session.model,
                cwd=session.project_dir,
                sdk_session_id=resume_sdk_session_id,
            )
            logger.info("[session=%s] SDK 连接预热完成", session_id)
        except RuntimeError as e:
            if "resume failed" in str(e).lower() or "no longer exists" in str(e).lower():
                session.update_sdk_session_id("")
                await self._save_session(session, commit=True)
                logger.warning(
                    "[session=%s] SDK 连接预热 resume 失败, 已清除 stale sdk_session_id",
                    session_id,
                )
            else:
                logger.warning("[session=%s] SDK 连接预热失败: %s", session_id, e)
        except Exception as e:
            logger.warning("[session=%s] SDK 连接预热失败: %s", session_id, e)

    async def refresh_context_usage(self, session_id: str) -> Session:
        session = await self.get_session(session_id)
        if not self._claude_agent_gateway.is_connected(session_id) and session.sdk_session_id:
            await self.prewarm_connection(session_id)
        if await self._refresh_context_usage(session):
            await self._save_session(session, commit=True)
        return session

    # ── Settings ─────────────────────────────────────────────

    async def set_model(self, session_id: str, model: str) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        if self._claude_agent_gateway.is_connected(session_id):
            await self._claude_agent_gateway.set_model(session_id, model)
        session.change_model(model)
        await self._save_session(session, commit=True)

    async def set_permission_mode(self, session_id: str, mode: str) -> None:
        await self._claude_agent_gateway.set_permission_mode(session_id, mode)
        await self._recorder.record_audit_event(
            session_id,
            "permission_mode_changed",
            actor="user",
            payload={"mode": mode},
        )

    async def get_models(self) -> list[dict]:
        return await self._claude_agent_gateway.get_models()

    async def resolve_user_response(self, session_id: str, response_data: dict) -> bool:
        resolved = await self._claude_agent_gateway.resolve_user_response(session_id, response_data)
        if resolved:
            await self._recorder.record_audit_event(
                session_id,
                "user_response_resolved",
                actor="user",
                payload={"response_keys": sorted(response_data.keys())},
            )
            await self._recorder.record_timeline_event(
                session_id,
                "external",
                "permission_response",
                "用户响应权限请求",
                {"response_keys": sorted(response_data.keys())},
            )
            await self._connection_manager.broadcast_global({
                "event": "session_input_resolved",
                "session_id": session_id,
                "agent_state": self._claude_agent_gateway.get_state(session_id),
            })
        return resolved

    # ── DB lifecycle ─────────────────────────────────────────

    async def commit(self) -> None:
        await self._session_repository.commit()

    async def rollback(self) -> None:
        await self._session_repository.rollback()

    async def close(self) -> None:
        await self._session_repository.close()

    # ── Import ───────────────────────────────────────────────

    async def import_claude_session(self, command: ImportClaudeSessionCommand) -> Session:
        if self._claude_session_manager is None:
            raise BusinessException("Claude session manager not available")

        existing = await self._session_repository.find_by_sdk_session_id(
            command.claude_session_id
        )
        if existing is not None:
            return existing

        cc_messages = self._claude_session_manager.get_claude_session_messages(
            session_id=command.claude_session_id,
            directory=command.cwd,
        )

        if not cc_messages:
            raise BusinessException("No messages found in Claude Code session")

        pf_messages = MessageConversionService.convert_cc_messages(cc_messages)

        project_dir = command.cwd or ""
        project_id = ""
        if project_dir and self._project_repository:
            project_id = await self._ensure_project_for_dir(project_dir)

        session = Session.create(
            model=os.getenv("DEFAULT_MODEL", "claude-opus-4-6"),
            project_id=project_id,
            project_dir=project_dir,
        )

        if command.name:
            session.rename(command.name[:200])

        for msg in pf_messages:
            session.add_message(msg)

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

        await self._save_session(session, commit=True)

        logger.info(
            "[import] CC session %s -> VP session %s, %d messages",
            command.claude_session_id,
            session.session_id,
            len(pf_messages),
        )

        return session

    async def _ensure_project_for_dir(self, dir_path: str) -> str:
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

    # ── Compact ──────────────────────────────────────────────

    async def compact_session(self, session_id: str) -> None:
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
            compact_usage: dict = {"input_tokens": 0, "output_tokens": 0}
            compact_sdk_sid = ""

            async for msg_dict in self._claude_agent_gateway.compact(session_id):
                if "input_tokens" in msg_dict and "output_tokens" in msg_dict:
                    compact_usage = {
                        "input_tokens": msg_dict["input_tokens"],
                        "output_tokens": msg_dict["output_tokens"],
                    }
                sdk_sid = msg_dict.get("sdk_session_id")
                if sdk_sid:
                    compact_sdk_sid = sdk_sid

            usage = Usage(
                input_tokens=compact_usage["input_tokens"],
                output_tokens=compact_usage["output_tokens"],
            )

            if compact_sdk_sid:
                await self._accept_or_reject_sdk_session_id(session, compact_sdk_sid, "compact")

            session.complete_compact(usage)

            refreshed = await self._refresh_context_usage(session)
            if not refreshed and compact_usage["input_tokens"] > 0:
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
                    "session": SessionPresenter.session_to_dict(session),
                    "messages": all_messages,
                },
            )
