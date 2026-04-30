from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import uuid

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
from domain.session.model.session_run_step import SessionRunStep
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
    _session_locks: dict[str, asyncio.Lock] = {}
    _session_locks_guard = asyncio.Lock()
    # Shared across all instances to coordinate between WS-service and bg-service
    _cancelled_sessions: set[str] = set()
    _queued_messages: dict[str, "RunQueryCommand"] = {}
    _waiting_for_slot: set[str] = set()
    _query_semaphore: asyncio.Semaphore | None = None
    _query_semaphore_guard = asyncio.Lock()

    @classmethod
    async def _lock_for_session(cls, session_id: str) -> asyncio.Lock:
        async with cls._session_locks_guard:
            lock = cls._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                cls._session_locks[session_id] = lock
            return lock

    @classmethod
    async def _get_query_semaphore(cls) -> asyncio.Semaphore:
        if cls._query_semaphore is None:
            async with cls._query_semaphore_guard:
                if cls._query_semaphore is None:
                    max_concurrent = int(os.getenv("SESSION_MAX_CONCURRENT_QUERIES", "2"))
                    cls._query_semaphore = asyncio.Semaphore(max(1, max_concurrent))
        return cls._query_semaphore

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
        self._audit_event_recorder = audit_event_recorder
        self._usage_recorder = usage_recorder
        self._timeline_service = timeline_service
        self._timeline_event_service = timeline_event_service
        self._session_service_factory = session_service_factory

    def is_waiting_for_slot(self, session_id: str) -> bool:
        return session_id in self._waiting_for_slot

    async def submit_query(self, command: RunQueryCommand) -> None:
        self._claude_agent_gateway.mark_active(command.session_id)
        session_lock = await self._lock_for_session(command.session_id)
        query_semaphore = await self._get_query_semaphore()
        try:
            if session_lock.locked():
                await self._connection_manager.broadcast(
                    command.session_id,
                    {"event": "resource_waiting", "status": "waiting_session_runner"},
                )
                await self._record_audit_event(
                    command.session_id,
                    "resource_waiting",
                    payload={"reason": "session_runner_busy"},
                )
            async with session_lock:
                if query_semaphore.locked():
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
                async with query_semaphore:
                    self._waiting_for_slot.discard(command.session_id)
                    await self.run_claude_query(command)
        except asyncio.CancelledError:
            self._waiting_for_slot.discard(command.session_id)
            self._claude_agent_gateway.mark_idle(command.session_id)
            raise
        except Exception:
            self._waiting_for_slot.discard(command.session_id)
            self._claude_agent_gateway.mark_idle(command.session_id)
            raise

    async def _save_session(self, session: Session, *, commit: bool = False) -> None:
        """Persist a session and optionally commit immediately.

        WebSocket handlers and background tasks reuse a long-lived DB session.
        In those paths we must commit after writes so row locks are released
        promptly instead of being held until the WebSocket disconnects.

        If the underlying connection is dead (OperationalError/InterfaceError),
        replaces the DB session with a fresh one from the pool and retries once.
        """
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
        """Replace the underlying DB session with a fresh one from the pool."""
        from infr.config.database import async_session_factory
        from infr.repository.session_repository_impl import SessionRepositoryImpl

        try:
            await self._session_repository.close()
        except Exception:
            pass
        new_db_session = async_session_factory()
        self._session_repository = SessionRepositoryImpl(new_db_session)

    @staticmethod
    def _is_fork_sdk_session_id(sdk_session_id: str) -> bool:
        return sdk_session_id.startswith("fork:")

    async def _resolve_resume_sdk_session_id(self, session: Session) -> str:
        sdk_session_id = session.sdk_session_id
        if not sdk_session_id:
            return ""
        if self._is_fork_sdk_session_id(sdk_session_id):
            return sdk_session_id

        owner = await self._session_repository.find_by_sdk_session_id(sdk_session_id)
        if owner is None or owner.session_id == session.session_id:
            return sdk_session_id

        session.update_sdk_session_id("")
        await self._record_audit_event(
            session.session_id,
            "sdk_session_binding_reset",
            payload={
                "sdk_session_id": sdk_session_id,
                "conflict_session_id": owner.session_id,
                "source": "resume",
            },
        )
        logger.error(
            "[session=%s] SDK session binding conflict on resume: sdk_session_id=%s owner=%s",
            session.session_id,
            sdk_session_id,
            owner.session_id,
            extra={"session_id": session.session_id, "sdk_session_id": sdk_session_id},
        )
        await self._save_session(session, commit=True)
        return ""

    async def _accept_or_reject_sdk_session_id(
        self,
        session: Session,
        new_sdk_session_id: str,
        source: str,
        run_id: str | None = None,
    ) -> bool:
        if not new_sdk_session_id or new_sdk_session_id == session.sdk_session_id:
            return False

        if not self._is_fork_sdk_session_id(new_sdk_session_id):
            try:
                owner = await self._session_repository.find_by_sdk_session_id(new_sdk_session_id)
            except Exception:
                await self._reconnect_db_session()
                owner = await self._session_repository.find_by_sdk_session_id(new_sdk_session_id)
            if owner is not None and owner.session_id != session.session_id:
                session.update_sdk_session_id("")
                await self._record_audit_event(
                    session.session_id,
                    "sdk_session_binding_conflict",
                    payload={
                        "sdk_session_id": new_sdk_session_id,
                        "conflict_session_id": owner.session_id,
                        "source": source,
                        "run_id": run_id,
                    },
                )
                logger.error(
                    "[session=%s] rejected SDK session_id from %s: sdk_session_id=%s owner=%s",
                    session.session_id,
                    source,
                    new_sdk_session_id,
                    owner.session_id,
                    extra={
                        "session_id": session.session_id,
                        "sdk_session_id": new_sdk_session_id,
                        "run_id": run_id or "-",
                    },
                )
                await self._claude_agent_gateway.disconnect(session.session_id)
                raise RuntimeError("SDK session is already bound to another Velpos session")

        session.update_sdk_session_id(new_sdk_session_id)
        event_type = {
            "clear": "sdk_session_id_updated_after_clear",
            "rewind": "sdk_session_id_updated_after_rewind",
            "compact": "sdk_session_id_updated_after_compact",
        }.get(source, "sdk_session_id_seen")
        await self._record_audit_event(
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

    async def _record_usage_ledger(self, session: Session) -> None:
        if self._usage_recorder is None:
            return
        if session.usage.input_tokens <= 0 and session.usage.output_tokens <= 0:
            return
        try:
            await self._usage_recorder(
                session.session_id,
                session.project_id,
                session.model,
                session.usage.input_tokens,
                session.usage.output_tokens,
                0,
                0,
            )
        except Exception:
            logger.warning("[session=%s] usage ledger write failed", session.session_id, exc_info=True)

    async def _start_run_step(
        self,
        session_id: str,
        run_id: str,
        step_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = True,
    ) -> SessionRunStep | None:
        if self._timeline_service is None:
            return None
        try:
            return await self._timeline_service.start_step(
                session_id, run_id, step_type, title, payload, commit=commit,
            )
        except Exception:
            logger.warning("[session=%s] run step start failed", session_id, exc_info=True)
            return None

    async def _progress_run_step(
        self,
        step: SessionRunStep | None,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = False,
    ) -> None:
        if self._timeline_service is None or step is None:
            return
        try:
            await self._timeline_service.progress_step(step, payload, commit=commit)
        except Exception:
            logger.warning("[session=%s] run step progress failed", step.session_id, exc_info=True)

    async def _complete_run_step(
        self,
        step: SessionRunStep | None,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = True,
    ) -> None:
        if self._timeline_service is None or step is None or step.status != "running":
            return
        try:
            await self._timeline_service.complete_step(step, payload, commit=commit)
        except Exception:
            logger.warning("[session=%s] run step complete failed", step.session_id, exc_info=True)

    async def _fail_run_step(
        self,
        step: SessionRunStep | None,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = True,
    ) -> None:
        if self._timeline_service is None or step is None or step.status != "running":
            return
        try:
            await self._timeline_service.fail_step(step, payload, commit=commit)
        except Exception:
            logger.warning("[session=%s] run step fail failed", step.session_id, exc_info=True)

    async def _record_timeline_event(
        self,
        session_id: str,
        run_id: str,
        event_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        status: str = "completed",
        *,
        commit: bool = True,
        emit: bool = True,
    ) -> None:
        if self._timeline_event_service is None:
            return
        try:
            await self._timeline_event_service.record_event(
                session_id=session_id,
                run_id=run_id,
                event_type=event_type,
                title=title,
                payload=payload,
                status=status,
                commit=commit,
                emit=emit,
            )
        except Exception:
            logger.warning(
                "[session=%s] timeline event write failed: %s",
                session_id,
                event_type,
                exc_info=True,
            )

    @staticmethod
    def _compact_payload_value(value: Any, limit: int = 1200) -> Any:
        if isinstance(value, str):
            return value if len(value) <= limit else value[:limit] + "..."
        if isinstance(value, list):
            return [SessionApplicationService._compact_payload_value(v, limit) for v in value[:20]]
        if isinstance(value, dict):
            return {
                str(k): SessionApplicationService._compact_payload_value(v, limit)
                for k, v in list(value.items())[:40]
            }
        return value

    def _timeline_events_for_message(
        self,
        msg_type_str: str,
        content: dict[str, Any],
        msg_dict: dict[str, Any],
    ) -> list[tuple[str, str, dict[str, Any]]]:
        events: list[tuple[str, str, dict[str, Any]]] = []
        if msg_type_str == "assistant":
            blocks = content.get("blocks", []) if isinstance(content, dict) else []
            text_parts = [
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
            ]
            if text_parts:
                text = "\n".join(text_parts)
                events.append((
                    "assistant_message",
                    "助手消息",
                    {"summary": text[:500], "text_length": len(text)},
                ))
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = str(block.get("name") or "tool")
                    events.append((
                        "tool_use",
                        f"工具调用：{name}",
                        {
                            "tool_name": name,
                            "tool_use_id": block.get("id", ""),
                            "input": self._compact_payload_value(block.get("input", {})),
                        },
                    ))
                elif block.get("type") == "tool_result":
                    events.append((
                        "tool_result",
                        "工具结果",
                        {
                            "tool_use_id": block.get("tool_use_id", ""),
                            "is_error": bool(block.get("is_error", False)),
                            "content": self._compact_payload_value(block.get("content")),
                        },
                    ))
                elif block.get("type") == "thinking":
                    thinking = str(block.get("thinking") or "")
                    events.append((
                        "assistant_thinking",
                        "思考中",
                        {"summary": thinking[:500], "text_length": len(thinking)},
                    ))
        elif msg_type_str == "tool_result":
            results = content.get("results", []) if isinstance(content, dict) else []
            for result in results:
                events.append((
                    "tool_result",
                    "工具结果",
                    {
                        "tool_use_id": result.get("tool_use_id", "") if isinstance(result, dict) else "",
                        "is_error": bool(result.get("is_error", False)) if isinstance(result, dict) else False,
                        "content": self._compact_payload_value(result.get("content") if isinstance(result, dict) else result),
                    },
                ))
        elif msg_type_str == "system":
            subtype = str(content.get("subtype") or "system") if isinstance(content, dict) else "system"
            events.append(("system_message", f"系统事件：{subtype}", self._compact_payload_value(content)))
        elif msg_type_str == "result":
            usage = content.get("usage", {}) if isinstance(content, dict) else {}
            events.append((
                "final_result",
                "最终结果",
                {
                    "is_error": bool(content.get("is_error", False)) if isinstance(content, dict) else False,
                    "duration_ms": content.get("duration_ms", 0) if isinstance(content, dict) else 0,
                    "num_turns": content.get("num_turns", 0) if isinstance(content, dict) else 0,
                    "stop_reason": content.get("stop_reason") if isinstance(content, dict) else None,
                    "total_cost_usd": content.get("total_cost_usd", 0) if isinstance(content, dict) else 0,
                },
            ))
            events.append((
                "token_usage",
                "Token 与成本",
                {
                    "input_tokens": msg_dict.get("input_tokens", usage.get("input_tokens", 0)),
                    "output_tokens": msg_dict.get("output_tokens", usage.get("output_tokens", 0)),
                    "total_cost_usd": content.get("total_cost_usd", 0) if isinstance(content, dict) else 0,
                },
            ))
        else:
            events.append((
                msg_type_str,
                MessageConversionService.summarise_content(content),
                self._compact_payload_value(content),
            ))
        return events

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

    async def list_timeline_events(
        self,
        session_id: str,
        limit: int = 500,
        event_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self._timeline_event_service is None:
            return []
        events = await self._timeline_event_service.list_events(
            session_id=session_id,
            limit=max(1, min(limit, 1000)),
            event_types=event_types,
        )
        return [self._timeline_event_service.event_to_dict(event) for event in events]

    async def list_run_timeline_events(
        self,
        session_id: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        if self._timeline_event_service is None:
            return []
        events = await self._timeline_event_service.list_run_events(session_id, run_id)
        return [self._timeline_event_service.event_to_dict(event) for event in events]

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
            session.update_queued_command(command.prompt, command.image_paths, command.attachments)
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
                "attachment_count": len(queued_command.get("attachments", [])),
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
    def _public_sdk_session_id(sdk_session_id: str) -> str:
        return "" if sdk_session_id.startswith("fork:") else sdk_session_id

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
            "sdk_session_id": SessionApplicationService._public_sdk_session_id(session.sdk_session_id),
            "updated_time": session.updated_time.isoformat() if session.updated_time else None,
            "git_branch": "",
            "recovery": SessionApplicationService._recovery_to_dict(session),
        }

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

        safe_create_task(self._bind_sdk_session(session.session_id, session.model, project_dir))

        return session

    async def _bind_sdk_session(self, session_id: str, model: str, cwd: str) -> None:
        """Connect a fresh CLI and capture sdk_session_id from the first query."""
        from infr.config.database import async_session_factory
        from infr.repository.session_repository_impl import SessionRepositoryImpl

        session_lock = await self._lock_for_session(session_id)
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

    async def get_session(self, session_id: str) -> Session:
        """Get session details by session_id."""
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("Session not found")
        return session

    async def list_sessions(self) -> list[Session]:
        """List all sessions."""
        return await self._session_repository.find_all()

    async def get_current_git_branch(self, project_dir: str) -> str:
        if not project_dir:
            return ""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", project_dir, "rev-parse", "--abbrev-ref", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    async def get_git_branch_for_session(self, session_id: str) -> str:
        session = await self.get_session(session_id)
        return await self.get_current_git_branch(session.project_dir)

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
                    await self._accept_or_reject_sdk_session_id(session, restored_sid, "clear")
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

        run_id = uuid.uuid4().hex[:8]
        run_step = await self._start_run_step(
            command.session_id,
            run_id,
            "run",
            "执行用户请求",
            {
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
                "prompt_length": len(command.prompt),
            },
        )

        logger.info(
            "[session=%s] 收到用户请求",
            command.session_id,
        )

        await self._record_audit_event(
            command.session_id,
            "query_started",
            actor="user",
            payload={
                "run_id": run_id,
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
                "prompt_length": len(command.prompt),
            },
        )
        await self._record_timeline_event(
            command.session_id,
            run_id,
            "user_input",
            "用户输入",
            {
                "prompt": command.prompt[:1200],
                "prompt_length": len(command.prompt),
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
            },
        )

        attachment_refs = []
        image_paths = set(command.image_paths)
        for attachment in command.attachments:
            path = attachment.get("path", "")
            filename = attachment.get("filename", "attachment")
            mime_type = attachment.get("mime_type", "")
            if not path:
                continue
            if mime_type.startswith("image/") or path in image_paths:
                attachment_refs.append(f"[Image: {path}]")
            else:
                attachment_refs.append(f"[Attachment: {filename} path={path}]")

        actual_prompt = command.prompt
        if attachment_refs:
            actual_prompt = f"{command.prompt}\n\n" + "\n".join(attachment_refs)
            logger.info(
                "[session=%s] 附加 %d 个附件到 prompt",
                command.session_id,
                len(attachment_refs),
            )

        session.start_query()
        self._claude_agent_gateway.mark_active(command.session_id)

        # Save user message and broadcast
        message_id = uuid.uuid4().hex[:12]
        user_message = Message.create(
            message_type=MessageType.USER,
            content={
                "message_id": message_id,
                "text": actual_prompt,
                "attachments": command.attachments,
            },
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
                resume_sdk_session_id = await self._resolve_resume_sdk_session_id(session)
                msg_stream = self._claude_agent_gateway.connect(
                    session_id=command.session_id,
                    model=session.model,
                    prompt=actual_prompt,
                    cwd=session.project_dir,
                    sdk_session_id=resume_sdk_session_id,
                )

            try:
                await self._consume_message_stream(session, msg_stream, run_id)
            except Exception as stream_err:
                # If cancelled, don't retry — let cancel_query handle cleanup
                if command.session_id in self._cancelled_sessions:
                    logger.info(
                        "[session=%s] 消息流因取消而中断, 跳过重试",
                        command.session_id,
                    )
                    await self._fail_run_step(run_step, {"cancelled": True, "stage": "stream"})
                    return
                # If send_query's stream fails mid-iteration (e.g. dead CLI process),
                # fall back to a fresh connect
                if is_connected:
                    await self._record_audit_event(
                        command.session_id,
                        "query_retrying",
                        payload={"run_id": run_id, "error": str(stream_err)[:500]},
                    )
                    await self._record_timeline_event(
                        command.session_id,
                        run_id,
                        "retry",
                        "消息流中断，重新连接",
                        {"error": str(stream_err)[:500]},
                    )
                    logger.warning(
                        "[session=%s] 消息流中断 (%s), 重新 connect",
                        command.session_id,
                        stream_err,
                    )
                    await self._claude_agent_gateway.disconnect(command.session_id)
                    resume_sdk_session_id = await self._resolve_resume_sdk_session_id(session)
                    msg_stream = self._claude_agent_gateway.connect(
                        session_id=command.session_id,
                        model=session.model,
                        prompt=actual_prompt,
                        cwd=session.project_dir,
                        sdk_session_id=resume_sdk_session_id,
                    )
                    await self._consume_message_stream(session, msg_stream, run_id)
                else:
                    raise

            await self._refresh_context_usage(session)

            # If cancelled during stream consumption, skip normal completion
            if command.session_id in self._cancelled_sessions:
                session.clear_cancel_requested()
                await self._fail_run_step(run_step, {"cancelled": True, "stage": "completion"})
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
            await self._record_usage_ledger(session)
            await self._complete_run_step(
                run_step,
                {
                    "input_tokens": session.usage.input_tokens,
                    "output_tokens": session.usage.output_tokens,
                    "message_count": session.message_count,
                },
            )
            await self._record_audit_event(
                command.session_id,
                "query_finished",
                payload={
                    "run_id": run_id,
                    "input_tokens": session.usage.input_tokens,
                    "output_tokens": session.usage.output_tokens,
                    "message_count": session.message_count,
                },
            )

        except Exception as e:
            # If cancelled, skip error handling — cancel_query handles everything
            if command.session_id in self._cancelled_sessions:
                session.clear_cancel_requested()
                await self._fail_run_step(run_step, {"cancelled": True, "stage": "error"})
                logger.info("[session=%s] 查询异常但已取消, 跳过错误处理", command.session_id)
                return
            logger.error(
                "[session=%s] Claude查询失败: %s",
                command.session_id,
                str(e),
                exc_info=True,
            )
            session.fail_query(error_message=str(e))
            await self._fail_run_step(run_step, {"error": str(e)[:500]})
            await self._record_audit_event(
                command.session_id,
                "query_failed",
                payload={"run_id": run_id, "error": str(e)[:500]},
            )
            await self._record_timeline_event(
                command.session_id,
                run_id,
                "error",
                "执行失败",
                {"error": str(e)[:1000]},
                status="failed",
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
                logger.error(
                    "[session=%s] final save failed, retrying with fresh DB session",
                    command.session_id,
                    exc_info=True,
                    extra={"session_id": command.session_id, "run_id": run_id},
                )
                try:
                    from infr.config.database import async_session_factory
                    from infr.repository.session_repository_impl import SessionRepositoryImpl

                    async with async_session_factory() as fresh_db:
                        fresh_repo = SessionRepositoryImpl(fresh_db)
                        await fresh_repo.save(session)
                        await fresh_db.commit()
                        logger.warning(
                            "[session=%s] final save recovered with fresh DB session",
                            command.session_id,
                            extra={"session_id": command.session_id, "run_id": run_id},
                        )
                except Exception:
                    logger.error(
                        "[session=%s] retry save also failed",
                        command.session_id,
                        exc_info=True,
                        extra={"session_id": command.session_id, "run_id": run_id},
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
                        "sdk_session_id": SessionApplicationService._public_sdk_session_id(session.sdk_session_id),
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
                    payload={"prompt_length": len(queued.prompt), "attachment_count": len(queued.attachments)},
                )
                logger.info("[session=%s] 执行排队的后续消息", command.session_id)
                if self._session_service_factory is not None:
                    async def _run_queued_message(command: RunQueryCommand) -> None:
                        queued_service = await self._session_service_factory()
                        try:
                            await queued_service.submit_query(command)
                        finally:
                            await queued_service.close()

                    safe_create_task(_run_queued_message(queued))
                else:
                    safe_create_task(self.submit_query(queued))

    # Maximum seconds to wait for the next message from the Claude stream.
    # If no message arrives within this window AND the CLI process has died,
    # we treat the stream as broken.  The generous timeout avoids false
    # positives during long tool executions (e.g. large file writes).
    _STREAM_MSG_TIMEOUT = 300  # 5 minutes

    @staticmethod
    def _tool_names_from_content(content: dict[str, Any]) -> list[str]:
        names: list[str] = []
        if isinstance(content, dict):
            for block in content.get("blocks", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = str(block.get("name") or "")
                    if name:
                        names.append(name)
        return names

    async def _consume_message_stream(
        self,
        session: "Session",
        msg_stream: "AsyncIterator[dict]",
        run_id: str,
    ) -> None:
        """Iterate over the message stream, persist messages and broadcast to WS.

        Includes a per-message timeout combined with a CLI process health
        check so the stream never hangs indefinitely when the subprocess
        crashes.
        """
        loop = asyncio.get_event_loop()
        last_save_time = loop.time()
        save_interval = 2.0  # save at most every 2s for cross-session visibility

        saw_context_input_usage = False
        stream_step = await self._start_run_step(
            session.session_id,
            run_id,
            "stream",
            "接收 Claude 消息流",
        )
        message_count = 0
        tool_count = 0
        waiting_count = 0
        aiter = msg_stream.__aiter__()
        next_msg_task: asyncio.Task | None = None
        try:
            while True:
                if next_msg_task is None:
                    next_msg_task = asyncio.create_task(aiter.__anext__())
                try:
                    msg_dict = await asyncio.wait_for(
                        asyncio.shield(next_msg_task), timeout=self._STREAM_MSG_TIMEOUT,
                    )
                    next_msg_task = None
                except StopAsyncIteration:
                    next_msg_task = None
                    break
                except asyncio.TimeoutError:
                    # Timeout waiting for next message — check if CLI is still alive.
                    # Keep the same __anext__ task alive; cancelling it can close the SDK stream.
                    if not self._claude_agent_gateway.is_process_alive(session.session_id):
                        logger.error(
                            "[session=%s] CLI 进程已退出且消息流超时, 终止消费",
                            session.session_id,
                        )
                        next_msg_task.cancel()
                        raise RuntimeError("Claude CLI process exited unexpectedly")
                    logger.info(
                        "[session=%s] 消息流等待超时但进程仍存活, 继续等待",
                        session.session_id,
                    )
                    waiting_count += 1
                    await self._record_audit_event(
                        session.session_id,
                        "stream_waiting",
                        payload={"run_id": run_id, "waiting_count": waiting_count},
                    )
                    await self._record_timeline_event(
                        session.session_id,
                        run_id,
                        "stream_waiting",
                        "等待 Claude 输出",
                        {"waiting_count": waiting_count},
                    )
                    await self._connection_manager.broadcast(
                        session.session_id,
                        {"event": "stream_waiting", "status": "waiting_output", "waiting_count": waiting_count},
                    )
                    continue
                msg_type_str = msg_dict["message_type"]

                # Handle internal meta events from gateway (not real messages)
                if msg_type_str == "_meta":
                    if msg_dict.get("resume_failed"):
                        session.update_sdk_session_id("")
                        await self._save_session(session, commit=True)
                        await self._record_audit_event(
                            session.session_id,
                            "sdk_resume_failed",
                            payload={"run_id": run_id},
                        )
                        await self._connection_manager.broadcast(
                            session.session_id,
                            {"event": "status_change", "data": self._session_to_dict(session)},
                        )
                    continue

                message = MessageConversionService.convert_stream_message(msg_dict)
                if message is None:
                    logger.warning(
                        "[session=%s] 未知消息类型: %s, 跳过",
                        session.session_id,
                        msg_type_str,
                    )
                    continue

                session.add_message(message)
                message_count += 1
                tool_names = self._tool_names_from_content(message.content)
                tool_count += len(tool_names)

                logger.info(
                    "[session=%s] Claude回复 [%s]",
                    session.session_id,
                    msg_type_str,
                )

                await self._connection_manager.broadcast(
                    session.session_id,
                    {"event": "message", "data": {"type": message.message_type.value, "content": message.content}},
                )
                for event_type, title, payload in self._timeline_events_for_message(
                    msg_type_str,
                    message.content,
                    msg_dict,
                ):
                    await self._record_timeline_event(
                        session.session_id,
                        run_id,
                        event_type,
                        title,
                        payload,
                        status="failed" if payload.get("is_error") else "completed",
                    )
                await self._progress_run_step(
                    stream_step,
                    {
                        "message_count": message_count,
                        "last_message_type": msg_type_str,
                        "last_tool_names": tool_names,
                        "tool_count": tool_count,
                    },
                    commit=False,
                )

                # Per-turn context from AssistantMessage — accurate context window size
                if "context_input_tokens" in msg_dict:
                    session.update_last_input_tokens(msg_dict["context_input_tokens"])
                    saw_context_input_usage = True

                if "input_tokens" in msg_dict and "output_tokens" in msg_dict:
                    # ResultMessage may carry cumulative tokens across all turns.
                    # Use it only when AssistantMessage did not provide live per-turn context.
                    if not saw_context_input_usage:
                        content = msg_dict.get("content", {})
                        num_turns = max(
                            msg_dict.get("num_turns")
                            or content.get("num_turns")
                            or 1,
                            1,
                        )
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
                    if new_sid:
                        await self._accept_or_reject_sdk_session_id(session, new_sid, "query", run_id)

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
            await self._complete_run_step(
                stream_step,
                {"message_count": message_count, "tool_count": tool_count},
            )
        except Exception as exc:
            await self._fail_run_step(stream_step, {"error": str(exc)[:500]})
            raise
        finally:
            if next_msg_task is not None and not next_msg_task.done():
                next_msg_task.cancel()

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

    def get_agent_state(self, session_id: str) -> str:
        return self._claude_agent_gateway.get_state(session_id)

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
        except Exception as e:
            logger.warning("[session=%s] SDK 连接预热失败: %s", session_id, e)

    async def refresh_context_usage(self, session_id: str) -> Session:
        session = await self.get_session(session_id)
        if not self._claude_agent_gateway.is_connected(session_id) and session.sdk_session_id:
            await self.prewarm_connection(session_id)
        if await self._refresh_context_usage(session):
            await self._save_session(session, commit=True)
        return session

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
        await self._record_timeline_event(
            session_id,
            "external",
            "cancel",
            "用户请求取消",
            {},
            status="cancelled",
        )
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
        rewind_sdk_sid = ""
        if self._claude_agent_gateway.is_connected(session_id):
            try:
                async for msg_dict in self._claude_agent_gateway.send_query(session_id, "/rewind"):
                    sdk_sid = msg_dict.get("sdk_session_id")
                    if sdk_sid:
                        rewind_sdk_sid = sdk_sid
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

            if rewind_sdk_sid:
                try:
                    await self._accept_or_reject_sdk_session_id(session, rewind_sdk_sid, "rewind")
                except Exception:
                    logger.error("[session=%s] /rewind SDK session_id rejected", session_id, exc_info=True)
                finally:
                    try:
                        await self._save_session(session, commit=True)
                    except Exception:
                        logger.warning(
                            "[session=%s] failed to persist /rewind sdk_session_id update",
                            session_id,
                            exc_info=True,
                        )

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

    async def rewind_to_message_id(self, session_id: str, message_id: str) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        for index, msg in enumerate(session.messages):
            if msg.message_type == MessageType.USER and msg.content.get("message_id") == message_id:
                await self.rewind_to_message(session_id, index)
                return

        raise ValueError(f"User message not found: {message_id}")

    async def rewind_to_message(self, session_id: str, message_index: int) -> None:
        """Rewind session to a specific user message index.

        1. Counts how many /rewind commands to send (number of user messages after target).
        2. Calls domain rewind_to.
        3. Sends N /rewind commands to Claude CLI.
        4. Persists and broadcasts updated state.
        """
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Count user messages after (and including) the target index
        rewind_count = sum(
            1 for msg in session.messages[message_index:]
            if msg.message_type == MessageType.USER
        )

        prompt = session.rewind_to(message_index)
        await self._save_session(session, commit=True)

        # Send /rewind to Claude CLI for each turn to undo
        if self._claude_agent_gateway.is_connected(session_id):
            rewind_sdk_sid = ""
            for _ in range(rewind_count):
                try:
                    async for msg_dict in self._claude_agent_gateway.send_query(session_id, "/rewind"):
                        sdk_sid = msg_dict.get("sdk_session_id")
                        if sdk_sid:
                            rewind_sdk_sid = sdk_sid
                except Exception as e:
                    logger.warning("[session=%s] /rewind failed: %s", session_id, e)
                    break

            if rewind_sdk_sid:
                try:
                    await self._accept_or_reject_sdk_session_id(session, rewind_sdk_sid, "rewind")
                    await self._save_session(session, commit=True)
                except Exception:
                    logger.error("[session=%s] rewind_to SDK session_id rejected", session_id, exc_info=True)

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
                "attachment_count": len(command.attachments),
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
            await self._record_timeline_event(
                session_id,
                "external",
                "permission_response",
                "用户响应权限请求",
                {"response_keys": sorted(response_data.keys())},
            )
        return resolved

    async def commit(self) -> None:
        """Commit the underlying DB session."""
        await self._session_repository.commit()

    async def rollback(self) -> None:
        """Rollback the underlying DB session."""
        await self._session_repository.rollback()

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
                    "session": self._session_to_dict(session),
                    "messages": all_messages,
                },
            )
