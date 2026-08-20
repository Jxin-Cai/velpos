from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.execution_ledger_event import (
    ExecutionLedgerEvent,
    ExecutionLedgerEventType,
    RunEventCounts,
)
from domain.session.repository.execution_ledger_event_repository import ExecutionLedgerEventRepository
from domain.shared.utils import safe_json_loads
from infr.repository.execution_ledger_event_model import ExecutionLedgerEventModel

# OTel derives a log event name from an attribute, falling back to the record
# body, which is unbounded. Clamp it to the column width on the way in.
_EVENT_NAME_MAX_LENGTH = 64
_UNNAMED_LOG_EVENT = "log"


class ExecutionLedgerEventRepositoryImpl(ExecutionLedgerEventRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_batch(self, events: list[ExecutionLedgerEvent]) -> None:
        if not events:
            return
        event_ids = [event.event_id for event in events]
        existing_result = await self._session.execute(
            select(ExecutionLedgerEventModel.event_id).where(
                ExecutionLedgerEventModel.event_id.in_(event_ids)
            )
        )
        existing_ids = set(existing_result.scalars().all())
        pending_by_id = {
            event.event_id: event
            for event in events
            if event.event_id not in existing_ids
        }
        pending_events = list(pending_by_id.values())
        if not pending_events:
            return
        models = [self._to_model(event) for event in pending_events]
        self._session.add_all(models)
        await self._session.flush()
        for event, model in zip(pending_events, models, strict=True):
            event.position = model.position

    async def find_by_run_after(
        self,
        session_id: str,
        run_id: str,
        after_position: int = 0,
        limit: int = 500,
    ) -> list[ExecutionLedgerEvent]:
        stmt = (
            select(ExecutionLedgerEventModel)
            .where(
                ExecutionLedgerEventModel.session_id == session_id,
                ExecutionLedgerEventModel.run_id == run_id,
                ExecutionLedgerEventModel.position > max(after_position, 0),
            )
            .order_by(ExecutionLedgerEventModel.position.asc())
            .limit(max(1, min(limit, 5001)))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def count_by_run(self, session_id: str, run_id: str) -> RunEventCounts:
        stmt = (
            select(
                ExecutionLedgerEventModel.event_type,
                ExecutionLedgerEventModel.event_name,
                func.count(ExecutionLedgerEventModel.position),
            )
            .where(
                ExecutionLedgerEventModel.session_id == session_id,
                ExecutionLedgerEventModel.run_id == run_id,
            )
            .group_by(
                ExecutionLedgerEventModel.event_type,
                ExecutionLedgerEventModel.event_name,
            )
        )
        result = await self._session.execute(stmt)
        log_counts: dict[str, int] = {}
        log_total = 0
        metric_total = 0
        for event_type, event_name, count in result.all():
            if event_type == ExecutionLedgerEventType.OTEL_LOG.value:
                name = event_name or _UNNAMED_LOG_EVENT
                log_counts[name] = log_counts.get(name, 0) + count
                log_total += count
            elif event_type == ExecutionLedgerEventType.OTEL_METRIC.value:
                metric_total += count
        return RunEventCounts(
            log_event_count=log_total,
            metric_sample_count=metric_total,
            log_counts_by_name=log_counts,
        )

    async def find_by_event_names(
        self,
        session_id: str,
        run_id: str,
        event_type: ExecutionLedgerEventType,
        event_names: Sequence[str],
        limit: int = 500,
    ) -> list[ExecutionLedgerEvent]:
        if not event_names:
            return []
        stmt = (
            select(ExecutionLedgerEventModel)
            .where(
                ExecutionLedgerEventModel.session_id == session_id,
                ExecutionLedgerEventModel.run_id == run_id,
                ExecutionLedgerEventModel.event_type == event_type.value,
                ExecutionLedgerEventModel.event_name.in_(list(event_names)),
            )
            .order_by(ExecutionLedgerEventModel.position.asc())
            .limit(max(1, min(limit, 5001)))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def find_recent_by_type(
        self,
        session_id: str,
        run_id: str,
        event_type: ExecutionLedgerEventType,
        limit: int = 100,
    ) -> list[ExecutionLedgerEvent]:
        stmt = (
            select(ExecutionLedgerEventModel)
            .where(
                ExecutionLedgerEventModel.session_id == session_id,
                ExecutionLedgerEventModel.run_id == run_id,
                ExecutionLedgerEventModel.event_type == event_type.value,
            )
            .order_by(ExecutionLedgerEventModel.position.desc())
            .limit(max(1, min(limit, 500)))
        )
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())
        models.reverse()
        return [self._to_domain(model) for model in models]

    async def find_by_event_id(
        self,
        session_id: str,
        event_id: str,
    ) -> ExecutionLedgerEvent | None:
        stmt = select(ExecutionLedgerEventModel).where(
            ExecutionLedgerEventModel.session_id == session_id,
            ExecutionLedgerEventModel.event_id == event_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    @staticmethod
    def _to_model(event: ExecutionLedgerEvent) -> ExecutionLedgerEventModel:
        return ExecutionLedgerEventModel(
            event_id=event.event_id,
            session_id=event.session_id,
            run_id=event.run_id,
            event_type=event.event_type.value,
            event_name=event.event_name[:_EVENT_NAME_MAX_LENGTH],
            span_id=event.span_id,
            parent_span_id=event.parent_span_id,
            span_type=event.span_type,
            status=event.status,
            agent_id=event.agent_id,
            tool_use_id=event.tool_use_id,
            causation_event_id=event.causation_event_id,
            event_time=event.event_time,
            ingested_time=event.ingested_time,
            payload_json=json.dumps(event.payload, ensure_ascii=False, default=str),
        )

    @staticmethod
    def _to_domain(model: ExecutionLedgerEventModel) -> ExecutionLedgerEvent:
        return ExecutionLedgerEvent(
            position=model.position,
            event_id=model.event_id,
            session_id=model.session_id,
            run_id=model.run_id,
            event_type=ExecutionLedgerEventType(model.event_type),
            event_name=model.event_name,
            span_id=model.span_id,
            parent_span_id=model.parent_span_id,
            span_type=model.span_type,
            status=model.status,
            agent_id=model.agent_id,
            tool_use_id=model.tool_use_id,
            causation_event_id=model.causation_event_id,
            event_time=model.event_time,
            ingested_time=model.ingested_time,
            payload=safe_json_loads(model.payload_json),
        )
