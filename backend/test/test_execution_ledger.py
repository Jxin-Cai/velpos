from __future__ import annotations

from typing import Any

import pytest

from application.session.trace_collector import TraceCollector
from domain.session.model.execution_ledger_event import ExecutionLedgerEventType
from domain.session.model.trace_span import TraceSpan


class _SpanRepositoryStub:
    def __init__(self, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.saved: list[TraceSpan] = []

    async def save_batch(self, spans: list[TraceSpan]) -> None:
        self.saved.extend(spans)

    async def update_batch(self, spans: list[TraceSpan]) -> None:
        self.saved.extend(spans)

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")


class _EventRepositoryStub:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    async def save_batch(self, events: list[Any]) -> None:
        for position, event in enumerate(events, start=1):
            event.position = position
        self.saved.extend(events)


@pytest.mark.asyncio
async def test_persists_ordered_lifecycle_events_when_run_completes() -> None:
    # Arrange
    span_repository = _SpanRepositoryStub()
    event_repository = _EventRepositoryStub()
    collector = TraceCollector(
        repository=span_repository,  # type: ignore[arg-type]
        event_repository=event_repository,  # type: ignore[arg-type]
    )

    # Act
    collector.ensure_run_span("session1", "run1")
    collector.finish_run("session1", "run1")
    await collector._flush()

    # Assert
    assert [event.event_type for event in event_repository.saved] == [
        ExecutionLedgerEventType.SPAN_CREATED,
        ExecutionLedgerEventType.SPAN_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_broadcasts_database_event_sequence_after_persistence() -> None:
    # Arrange
    messages: list[dict[str, Any]] = []

    async def broadcast(_session_id: str, message: dict[str, Any]) -> None:
        messages.append(message)

    collector = TraceCollector(
        repository=_SpanRepositoryStub(),  # type: ignore[arg-type]
        event_repository=_EventRepositoryStub(),  # type: ignore[arg-type]
        broadcast_fn=broadcast,
    )

    # Act
    collector.ensure_run_span("session1", "run1")
    await collector._flush()

    # Assert
    assert messages[0]["event_sequence"] == 1


@pytest.mark.asyncio
async def test_links_run_completion_to_run_creation_event() -> None:
    # Arrange
    event_repository = _EventRepositoryStub()
    collector = TraceCollector(
        repository=_SpanRepositoryStub(),  # type: ignore[arg-type]
        event_repository=event_repository,  # type: ignore[arg-type]
    )

    # Act
    collector.ensure_run_span("session1", "run1")
    collector.finish_run("session1", "run1")
    await collector._flush()

    # Assert
    assert event_repository.saved[1].causation_event_id == event_repository.saved[0].event_id


@pytest.mark.asyncio
async def test_retries_event_without_broadcast_when_transaction_fails() -> None:
    # Arrange
    messages: list[dict[str, Any]] = []

    async def broadcast(_session_id: str, message: dict[str, Any]) -> None:
        messages.append(message)

    collector = TraceCollector(
        repository=_SpanRepositoryStub(fail_commit=True),  # type: ignore[arg-type]
        event_repository=_EventRepositoryStub(),  # type: ignore[arg-type]
        broadcast_fn=broadcast,
    )

    # Act
    collector.ensure_run_span("session1", "run1")
    await collector._flush()

    # Assert
    assert messages == []
    assert len(collector._pending_events) == 1
