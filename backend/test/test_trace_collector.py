from __future__ import annotations

import pytest

from application.session.trace_collector import TraceCollector
from domain.session.model.trace_span import TraceSpan


class _RepositoryStub:
    def __init__(self) -> None:
        self.saved: list[TraceSpan] = []
        self.updated: list[TraceSpan] = []

    async def save_batch(self, spans: list[TraceSpan]) -> None:
        self.saved.extend(spans)

    async def update_batch(self, spans: list[TraceSpan]) -> None:
        self.updated.extend(spans)

    async def commit(self) -> None:
        return None


def test_only_run_envelope_created_when_run_starts() -> None:
    # Arrange
    collector = TraceCollector(repository=_RepositoryStub())  # type: ignore[arg-type]

    # Act
    span_id = collector.ensure_run_span("session1", "run1", "message1")

    # Assert
    assert span_id is not None
    assert len(collector._buffer) == 1
    span = collector.find_run_span("session1", "run1")
    assert span is not None
    assert span.span_type == TraceSpan.SPAN_TYPE_RUN
    assert span.metadata["telemetry.source"] == "velpos_run_envelope"


def test_same_run_envelope_returned_when_run_started_twice() -> None:
    # Arrange
    collector = TraceCollector(repository=_RepositoryStub())  # type: ignore[arg-type]

    # Act
    first_id = collector.ensure_run_span("session1", "run1")
    second_id = collector.ensure_run_span("session1", "run1")

    # Assert
    assert second_id == first_id
    assert len(collector._buffer) == 1


def test_run_envelope_failed_when_run_finishes_with_error() -> None:
    # Arrange
    collector = TraceCollector(repository=_RepositoryStub())  # type: ignore[arg-type]
    collector.ensure_run_span("session1", "run1")

    # Act
    collector.finish_run("session1", "run1", error="SDK failed")

    # Assert
    span = collector.find_run_span("session1", "run1")
    assert span is not None
    assert span.status == TraceSpan.STATUS_FAILED
    assert span.metadata["error"] == "SDK failed"


def test_all_run_envelopes_abandoned_when_session_process_is_lost() -> None:
    # Arrange
    collector = TraceCollector(repository=_RepositoryStub())  # type: ignore[arg-type]
    collector.ensure_run_span("session1", "run1")
    collector.ensure_run_span("session1", "run2")

    # Act
    collector.abandon_all_running("session1", reason="Process lost")

    # Assert
    assert all(
        span.status == TraceSpan.STATUS_ABANDONED
        for span in collector._buffer.values()
    )


@pytest.mark.asyncio
async def test_abandoned_run_envelope_persisted_when_collector_stops() -> None:
    # Arrange
    repository = _RepositoryStub()
    collector = TraceCollector(repository=repository)  # type: ignore[arg-type]
    collector.ensure_run_span("session1", "run1")

    # Act
    await collector.stop()

    # Assert
    assert repository.saved
    assert repository.saved[0].status == TraceSpan.STATUS_ABANDONED
