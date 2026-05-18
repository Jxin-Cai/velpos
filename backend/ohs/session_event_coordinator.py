"""Coordinates cross-cutting session events: WS broadcast, IM sync, audit, timeline, usage."""

from __future__ import annotations

import asyncio
import logging

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.session.acl.connection_manager import ConnectionManager
from domain.session.model.session_audit_event import SessionAuditEvent
from domain.shared.async_utils import safe_create_task

from application.im_binding.im_channel_application_service import ImChannelApplicationService
from application.session.session_timeline_event_service import SessionTimelineEventService
from application.usage.usage_governance_application_service import UsageGovernanceApplicationService

from infr.config.database import async_session_factory
from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl
from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
from infr.repository.session_audit_event_repository_impl import SessionAuditEventRepositoryImpl
from infr.repository.session_repository_impl import SessionRepositoryImpl
from infr.repository.session_timeline_event_repository_impl import SessionTimelineEventRepositoryImpl
from infr.repository.usage_governance_repository_impl import UsageGovernanceRepositoryImpl

logger = logging.getLogger(__name__)


class SessionEventCoordinator:
    """Coordinates cross-cutting session events: WS broadcast, IM sync, audit, timeline."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        im_channel_registry: ImChannelRegistry,
    ) -> None:
        self._connection_manager = connection_manager
        self._im_channel_registry = im_channel_registry

    # ── WS + IM broadcast ─────────────────────────────────────────

    async def broadcast_with_im(self, session_id: str, data: dict) -> None:
        """Broadcast to WS clients and forward user_choice_request to IM."""
        await self._connection_manager.broadcast(session_id, data)
        event = data.get("event")
        if event in {"permission_request", "user_choice_request"}:
            interaction_type = "user_choice" if event == "user_choice_request" else "permission"
            await self._connection_manager.broadcast_global({
                "event": "session_waiting_for_input",
                "session_id": session_id,
                "interaction_type": interaction_type,
                "tool_name": data.get("tool_name", ""),
                "questions": data.get("questions", []),
                "tool_input": data.get("tool_input", ""),
                "agent_state": "waiting_permission",
            })
            audit_type = "ask_user_question_requested" if event == "user_choice_request" else "permission_requested"
            try:
                await self.record_audit_event(
                    SessionAuditEvent.create(
                        session_id=session_id,
                        event_type=audit_type,
                        payload={"tool_name": data.get("tool_name", "")},
                    )
                )
            except Exception:
                logger.warning("Failed to record pending request audit for session %s", session_id, exc_info=True)
        if event == "user_choice_request":
            questions = data.get("questions", [])
            lines = ["[User Input Required]"]
            for i, q in enumerate(questions):
                lines.append(f"\n{q.get('question', '')}")
                for j, opt in enumerate(q.get("options", [])):
                    label = opt.get("label", "")
                    desc = opt.get("description", "")
                    lines.append(f"  {j + 1}. {label}" + (f" - {desc}" if desc else ""))
            text = "\n".join(lines)
            safe_create_task(self.on_assistant_response(session_id, text))

    # ── IM sync ───────────────────────────────────────────────────

    async def _sync_to_im(self, session_id: str, content: str, log_label: str = "Outbound") -> None:
        """Forward a message to the bound IM channel with 3-attempt retry."""
        last_err = None
        for attempt in range(3):
            try:
                async with async_session_factory() as db_session:
                    svc = ImChannelApplicationService(
                        registry=self._im_channel_registry,
                        binding_repo=ImBindingRepositoryImpl(db_session),
                        init_repo=ChannelInitRepositoryImpl(db_session),
                    )
                    await svc.sync_outbound(session_id, content)
                    await db_session.commit()
                return
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))

        logger.warning(
            "%s IM sync failed for session %s after 3 attempts",
            log_label, session_id, exc_info=last_err,
        )
        await self._connection_manager.broadcast(session_id, {
            "event": "error",
            "message": "IM message sync failed, the message may not have been delivered to the IM channel.",
        })

    async def on_assistant_response(self, session_id: str, content: str) -> None:
        await self._sync_to_im(session_id, content, "Outbound")

    async def on_user_message(self, session_id: str, content: str) -> None:
        await self._sync_to_im(session_id, f"[Web User]\n{content}", "User message")

    # ── IM binding check ──────────────────────────────────────────

    async def is_session_im_bound(self, session_id: str) -> bool:
        """Check if a session has an active IM binding (for idle disconnect protection)."""
        try:
            async with async_session_factory() as db_session:
                repo = ImBindingRepositoryImpl(db_session)
                binding = await repo.find_by_session_id(session_id)
                return binding is not None and binding.binding_status == BindingStatus.BOUND
        except Exception:
            logger.warning("Failed to check IM binding for session %s", session_id, exc_info=True)
            return False

    # ── Pending request context ───────────────────────────────────

    async def persist_pending_request_context(
        self,
        session_id: str,
        context: dict | None,
    ) -> None:
        async with async_session_factory() as db_session:
            repo = SessionRepositoryImpl(db_session)
            session = await repo.find_by_id(session_id)
            if session is None:
                return
            if context:
                session.update_pending_request_context(context)
            else:
                session.clear_pending_request_context()
            await repo.save(session)
            await db_session.commit()

    # ── Audit events ──────────────────────────────────────────────

    async def record_audit_event(self, event) -> None:
        async with async_session_factory() as db_session:
            repo = SessionAuditEventRepositoryImpl(db_session)
            await repo.save(event)
            await db_session.commit()

    # ── Timeline events ───────────────────────────────────────────

    async def record_timeline_event(
        self,
        session_id: str,
        event_type: str,
        title: str,
        payload: dict | None = None,
        status: str = "completed",
    ) -> None:
        async with async_session_factory() as db_session:
            svc = SessionTimelineEventService(
                repository=SessionTimelineEventRepositoryImpl(db_session),
                connection_manager=None,
            )
            await svc.record_event(
                session_id=session_id,
                run_id="external",
                event_type=event_type,
                title=title,
                payload=payload or {},
                status=status,
                commit=True,
                emit=False,
            )

    async def timeline_broadcast_hook(self, session_id: str, data: dict) -> None:
        event = data.get("event")
        if event == "permission_request":
            await self.record_timeline_event(
                session_id,
                "permission_request",
                f"权限请求：{data.get('tool_name', '')}",
                {"tool_name": data.get("tool_name", ""), "tool_input": data.get("tool_input", "")},
                status="running",
            )
        elif event == "user_choice_request":
            await self.record_timeline_event(
                session_id,
                "permission_request",
                "用户选择请求",
                {"tool_name": data.get("tool_name", ""), "questions": data.get("questions", [])},
                status="running",
            )

    # ── Usage ledger ──────────────────────────────────────────────

    async def record_usage_ledger(
        self,
        session_id: str,
        project_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> None:
        async with async_session_factory() as db_session:
            svc = UsageGovernanceApplicationService(
                repository=UsageGovernanceRepositoryImpl(db_session),
            )
            await svc.record_usage(
                session_id=session_id,
                project_id=project_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
            )
            await db_session.commit()
