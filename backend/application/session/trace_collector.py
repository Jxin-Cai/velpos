from __future__ import annotations

import asyncio
import copy
import logging
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from domain.session.model.execution_ledger_event import ExecutionLedgerEvent
from domain.session.model.trace_span import TraceSpan
from domain.session.repository.execution_ledger_event_repository import (
    ExecutionLedgerEventRepository,
)
from domain.session.repository.trace_span_repository import TraceSpanRepository

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL = float(os.getenv("VELPOS_TRACE_FLUSH_INTERVAL", "1.0"))
_TRACE_ENABLED = os.getenv("VELPOS_TRACE_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}


class TraceCollector:
    """Buffers only Velpos run envelopes around Claude Code's native OTLP data.

    Claude Code owns the detailed interaction, model, tool, permission, hook and
    subagent spans. Velpos keeps one application-level envelope so those native
    spans can be attached to the user request that launched them.
    """

    def __init__(
        self,
        repository: TraceSpanRepository | None = None,
        repository_factory: Callable[
            [], AbstractAsyncContextManager[TraceSpanRepository]
        ] | None = None,
        event_repository: ExecutionLedgerEventRepository | None = None,
        persistence_factory: Callable[
            [],
            AbstractAsyncContextManager[
                tuple[TraceSpanRepository, ExecutionLedgerEventRepository]
            ],
        ] | None = None,
        broadcast_fn: Any = None,
        flush_interval: float = _FLUSH_INTERVAL,
    ) -> None:
        if repository is None and repository_factory is None and persistence_factory is None:
            raise ValueError("repository, repository_factory, or persistence_factory is required")
        self._repository = repository
        self._repository_factory = repository_factory
        self._event_repository = event_repository
        self._persistence_factory = persistence_factory
        self._broadcast_fn = broadcast_fn
        self._flush_interval = flush_interval
        self._enabled = _TRACE_ENABLED
        self._buffer: dict[str, TraceSpan] = {}
        self._dirty_new: set[str] = set()
        self._dirty_update: set[str] = set()
        self._pending_events: list[ExecutionLedgerEvent] = []
        self._last_event_id_by_span: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._sequence_counter = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = loop.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        for session_id in {
            span.session_id
            for span in self._buffer.values()
            if span.status == TraceSpan.STATUS_RUNNING
        }:
            self.abandon_all_running(
                session_id,
                reason="Backend process stopped before the run completed",
            )
        await self._flush()

    async def flush(self) -> None:
        await self._flush()

    def ensure_run_span(
        self,
        session_id: str,
        run_id: str,
        source_message_id: str | None = None,
    ) -> str | None:
        if not self._enabled:
            return None
        existing = self.find_run_span(session_id, run_id)
        if existing is not None:
            return existing.id
        self.start()
        self._sequence_counter += 1
        span = TraceSpan.create(
            session_id=session_id,
            run_id=run_id,
            span_type=TraceSpan.SPAN_TYPE_RUN,
            name="Agent run",
            metadata={
                "source_message_id": source_message_id,
                "telemetry.source": "velpos_run_envelope",
            },
        )
        span.sequence = self._sequence_counter
        span.revision = 1
        self._buffer[span.id] = span
        self._dirty_new.add(span.id)
        self._queue_change(span, "created")
        return span.id

    def find_run_span(self, session_id: str, run_id: str) -> TraceSpan | None:
        return next(
            (
                span
                for span in self._buffer.values()
                if span.session_id == session_id
                and span.run_id == run_id
                and span.span_type == TraceSpan.SPAN_TYPE_RUN
            ),
            None,
        )

    def finish_run(
        self,
        session_id: str,
        run_id: str,
        error: str | None = None,
        cancelled: bool = False,
        abandoned: bool = False,
    ) -> None:
        span = self.find_run_span(session_id, run_id)
        if span is None or span.status != TraceSpan.STATUS_RUNNING:
            return
        if abandoned:
            span.abandon(reason="Process lost")
            action = "abandoned"
        elif cancelled:
            span.cancel(reason="Query cancelled")
            action = "cancelled"
        elif error:
            span.fail(error=error[:500])
            action = "failed"
        else:
            span.complete()
            action = "completed"
        self._mark_updated(span, action)

    def abandon_all_running(self, session_id: str, reason: str | None = None) -> None:
        for span in list(self._buffer.values()):
            if span.session_id != session_id or span.status != TraceSpan.STATUS_RUNNING:
                continue
            span.abandon(reason=reason)
            self._mark_updated(span, "abandoned")

    def _mark_updated(self, span: TraceSpan, action: str) -> None:
        span.revision += 1
        self._sequence_counter += 1
        span.sequence = self._sequence_counter
        self._dirty_update.add(span.id)
        self._queue_change(span, action)

    def _queue_change(self, span: TraceSpan, action: str) -> None:
        event = ExecutionLedgerEvent.from_span(span, action)
        event.causation_event_id = self._last_event_id_by_span.get(span.id)
        self._last_event_id_by_span[span.id] = event.event_id
        self._pending_events.append(event)

    async def discard_session(self, session_id: str) -> None:
        async with self._lock:
            span_ids = {
                span_id
                for span_id, span in self._buffer.items()
                if span.session_id == session_id
            }
            for span_id in span_ids:
                self._buffer.pop(span_id, None)
                self._last_event_id_by_span.pop(span_id, None)
            self._dirty_new.difference_update(span_ids)
            self._dirty_update.difference_update(span_ids)
            self._pending_events = [
                event
                for event in self._pending_events
                if event.session_id != session_id
            ]

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("TraceCollector flush error", exc_info=True)

    async def _flush(self) -> None:
        if not self._dirty_new and not self._dirty_update and not self._pending_events:
            return
        async with self._lock:
            new_ids = list(self._dirty_new)
            update_ids = list(self._dirty_update - self._dirty_new)
            events = copy.deepcopy(self._pending_events)
            self._dirty_new.clear()
            self._dirty_update.clear()
            self._pending_events.clear()
            new_spans = [copy.copy(self._buffer[item]) for item in new_ids]
            update_spans = [copy.copy(self._buffer[item]) for item in update_ids]
            for span in new_spans + update_spans:
                span.metadata = dict(span.metadata)

        try:
            if self._persistence_factory is not None:
                async with self._persistence_factory() as repositories:
                    await self._persist(*repositories, new_spans, update_spans, events)
            elif self._repository_factory is not None:
                async with self._repository_factory() as repository:
                    await self._persist(
                        repository,
                        None,
                        new_spans,
                        update_spans,
                        events,
                    )
            elif self._repository is not None:
                await self._persist(
                    self._repository,
                    self._event_repository,
                    new_spans,
                    update_spans,
                    events,
                )
        except Exception:
            async with self._lock:
                self._dirty_new.update(new_ids)
                self._dirty_update.update(update_ids)
                self._pending_events = events + self._pending_events
            logger.warning(
                "TraceCollector failed to persist run envelopes",
                exc_info=True,
            )
            return

        if events and self._broadcast_fn:
            for event in events:
                try:
                    await self._broadcast_fn(
                        event.session_id,
                        {
                            "event": "trace_span",
                            "action": event.payload.get("action", "updated"),
                            "span": event.payload.get("span", {}),
                            "event_id": event.event_id,
                            "event_sequence": event.position,
                        },
                    )
                except Exception:
                    logger.debug(
                        "TraceCollector broadcast failed for event %s",
                        event.event_id,
                        exc_info=True,
                    )

    @staticmethod
    async def _persist(
        repository: TraceSpanRepository,
        event_repository: ExecutionLedgerEventRepository | None,
        new_spans: list[TraceSpan],
        update_spans: list[TraceSpan],
        events: list[ExecutionLedgerEvent],
    ) -> None:
        if new_spans:
            await repository.save_batch(new_spans)
        if update_spans:
            await repository.update_batch(update_spans)
        if event_repository is not None and events:
            await event_repository.save_batch(events)
        if new_spans or update_spans or events:
            await repository.commit()
