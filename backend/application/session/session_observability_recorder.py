from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from application.session.session_run_timeline_service import SessionRunTimelineService
from application.session.session_timeline_event_service import SessionTimelineEventService
from domain.session.model.session import Session
from domain.session.model.session_audit_event import SessionAuditEvent
from domain.session.model.session_run_step import SessionRunStep
from domain.session.repository.session_audit_event_repository import SessionAuditEventRepository
from domain.session.service.message_conversion_service import MessageConversionService

logger = logging.getLogger(__name__)


class SessionObservabilityRecorder:

    def __init__(
        self,
        audit_event_repository: SessionAuditEventRepository | None = None,
        audit_event_recorder: Callable[[SessionAuditEvent], Awaitable[None]] | None = None,
        usage_recorder: Callable[[str, str, str, int, int, int, int], Awaitable[None]] | None = None,
        timeline_service: SessionRunTimelineService | None = None,
        timeline_event_service: SessionTimelineEventService | None = None,
    ) -> None:
        self._audit_event_repository = audit_event_repository
        self._audit_event_recorder = audit_event_recorder
        self._usage_recorder = usage_recorder
        self._timeline_service = timeline_service
        self._timeline_event_service = timeline_event_service

    async def record_audit_event(
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

    async def record_usage_ledger(self, session: Session) -> None:
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

    async def start_run_step(
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

    async def progress_run_step(
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

    async def complete_run_step(
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

    async def fail_run_step(
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

    async def record_timeline_event(
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
    def compact_payload_value(value: Any, limit: int = 1200) -> Any:
        if isinstance(value, str):
            return value if len(value) <= limit else value[:limit] + "..."
        if isinstance(value, list):
            return [SessionObservabilityRecorder.compact_payload_value(v, limit) for v in value[:20]]
        if isinstance(value, dict):
            return {
                str(k): SessionObservabilityRecorder.compact_payload_value(v, limit)
                for k, v in list(value.items())[:40]
            }
        return value

    def timeline_events_for_message(
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
                            "input": self.compact_payload_value(block.get("input", {})),
                        },
                    ))
                elif block.get("type") == "tool_result":
                    events.append((
                        "tool_result",
                        "工具结果",
                        {
                            "tool_use_id": block.get("tool_use_id", ""),
                            "is_error": bool(block.get("is_error", False)),
                            "content": self.compact_payload_value(block.get("content")),
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
                        "content": self.compact_payload_value(result.get("content") if isinstance(result, dict) else result),
                    },
                ))
        elif msg_type_str == "system":
            subtype = str(content.get("subtype") or "system") if isinstance(content, dict) else "system"
            events.append(("system_message", f"系统事件：{subtype}", self.compact_payload_value(content)))
        elif msg_type_str == "result":
            c = content if isinstance(content, dict) else {}
            usage = c.get("usage", {})
            events.append((
                "final_result",
                "最终结果",
                {
                    "is_error": bool(c.get("is_error", False)),
                    "duration_ms": c.get("duration_ms", 0),
                    "num_turns": c.get("num_turns", 0),
                    "stop_reason": c.get("stop_reason"),
                    "total_cost_usd": c.get("total_cost_usd", 0),
                },
            ))
            events.append((
                "token_usage",
                "Token 与成本",
                {
                    "input_tokens": msg_dict.get("input_tokens", usage.get("input_tokens", 0)),
                    "output_tokens": msg_dict.get("output_tokens", usage.get("output_tokens", 0)),
                    "total_cost_usd": c.get("total_cost_usd", 0),
                },
            ))
        else:
            events.append((
                msg_type_str,
                MessageConversionService.summarise_content(content),
                self.compact_payload_value(content),
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
