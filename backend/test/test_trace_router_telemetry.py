from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest

from domain.session.model.execution_ledger_event import (
    ExecutionLedgerEvent,
    ExecutionLedgerEventType,
    RunEventCounts,
)
from ohs.http.trace_router import get_telemetry_summary

_SESSION_ID = "sess0001"
_RUN_ID = "run-1"
_NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class _SpanRepositoryStub:
    async def find_by_run(self, _session_id: str, _run_id: str) -> list:
        return []


class _EventRepositoryStub:
    def __init__(
        self,
        counts: RunEventCounts | None = None,
        events_by_name: dict[str, list[ExecutionLedgerEvent]] | None = None,
        recent: list[ExecutionLedgerEvent] | None = None,
    ) -> None:
        self._counts = counts or RunEventCounts()
        self._events_by_name = events_by_name or {}
        self._recent = recent or []

    async def count_by_run(self, _session_id: str, _run_id: str) -> RunEventCounts:
        return self._counts

    async def find_by_event_names(
        self,
        _session_id: str,
        _run_id: str,
        _event_type: ExecutionLedgerEventType,
        event_names: Sequence[str],
        limit: int = 500,
    ) -> list[ExecutionLedgerEvent]:
        return [
            event
            for name in event_names
            for event in self._events_by_name.get(name, [])
        ]

    async def find_recent_by_type(
        self,
        _session_id: str,
        _run_id: str,
        _event_type: ExecutionLedgerEventType,
        limit: int = 100,
    ) -> list[ExecutionLedgerEvent]:
        return self._recent


def _log_event(event_name: str, payload: dict) -> ExecutionLedgerEvent:
    return ExecutionLedgerEvent.from_otel_record(
        event_id=f"event-{event_name}",
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        signal="log",
        event_name=event_name,
        event_time=_NOW,
        payload=payload,
    )


async def _summary(event_repo: _EventRepositoryStub) -> dict:
    response = await get_telemetry_summary(
        _SESSION_ID,
        _RUN_ID,
        _SpanRepositoryStub(),  # type: ignore[arg-type]
        event_repo,  # type: ignore[arg-type]
    )
    assert response.data is not None
    return response.data


@pytest.mark.asyncio
async def test_reports_log_and_metric_totals_from_store_tallies() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        counts=RunEventCounts(
            log_event_count=4200,
            metric_sample_count=17,
            log_counts_by_name={"api_request": 4200},
        )
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert (summary["log_event_count"], summary["metric_sample_count"]) == (4200, 17)


@pytest.mark.asyncio
async def test_sums_every_failure_event_name_into_api_error_count() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        counts=RunEventCounts(
            log_counts_by_name={
                "api_error": 2,
                "api_refusal": 1,
                "api_retries_exhausted": 3,
                "internal_error": 1,
                "api_request": 9,
            }
        )
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert summary["api_error_count"] == 7


@pytest.mark.asyncio
async def test_counts_both_raw_body_event_names_when_bodies_are_exported() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        counts=RunEventCounts(
            log_counts_by_name={"api_request_body": 5, "api_response_body": 4}
        )
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert summary["raw_api_body_count"] == 9


@pytest.mark.asyncio
async def test_sums_request_cost_when_api_request_events_carry_cost() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        events_by_name={
            "api_request": [
                _log_event("api_request", {"attributes": {"cost_usd": 0.02}}),
                _log_event("api_request", {"attributes": {"cost_usd": 0.03}}),
            ]
        }
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert summary["cost_usd"] == 0.05


@pytest.mark.asyncio
async def test_falls_back_to_cost_metric_when_requests_report_no_cost() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        events_by_name={
            "api_request": [_log_event("api_request", {"attributes": {}})],
            "claude_code.cost.usage": [
                _log_event("claude_code.cost.usage", {"value": 0.25}),
            ],
        }
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert summary["cost_usd"] == 0.25


@pytest.mark.asyncio
async def test_clips_oversized_field_when_recent_event_is_listed() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        recent=[_log_event("api_response_body", {"body": "x" * 50000})]
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert len(summary["recent_events"][0]["payload"]["body"]) < 50000


@pytest.mark.asyncio
async def test_flags_clipped_event_so_reader_can_request_it_verbatim() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        recent=[_log_event("api_response_body", {"body": "x" * 50000})]
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert summary["recent_events"][0]["payload_truncated"] is True


@pytest.mark.asyncio
async def test_leaves_small_event_unflagged_when_nothing_is_clipped() -> None:
    # Arrange
    event_repo = _EventRepositoryStub(
        recent=[_log_event("api_request", {"attributes": {"cost_usd": 0.01}})]
    )

    # Act
    summary = await _summary(event_repo)

    # Assert
    assert summary["recent_events"][0]["payload_truncated"] is False
