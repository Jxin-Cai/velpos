from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest

from application.session.llm_request_query_service import LlmRequestQueryService
from domain.session.model.execution_ledger_event import (
    ExecutionLedgerEvent,
    ExecutionLedgerEventType,
)
from domain.session.service.llm_request_decomposer import API_REQUEST_BODY_EVENT_NAME

_SESSION_ID = "sess0001"
_RUN_ID = "run-1"
_NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def _body_event(event_id: str, system: str, offset_seconds: int = 0) -> ExecutionLedgerEvent:
    return ExecutionLedgerEvent.from_otel_record(
        event_id=event_id,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        signal="log",
        event_name=API_REQUEST_BODY_EVENT_NAME,
        event_time=_NOW + timedelta(seconds=offset_seconds),
        payload={
            "attributes": {
                "request_body": json.dumps({"system": system, "messages": [], "tools": []}),
            },
        },
    )


class _EventRepositoryStub:
    def __init__(self, events: list[ExecutionLedgerEvent]) -> None:
        self._events = events

    async def find_by_event_names(
        self,
        _session_id: str,
        _run_id: str,
        _event_type: ExecutionLedgerEventType,
        _event_names: Sequence[str],
        limit: int = 500,
    ) -> list[ExecutionLedgerEvent]:
        return self._events[:limit]

    async def find_by_event_id(
        self,
        session_id: str,
        event_id: str,
    ) -> ExecutionLedgerEvent | None:
        return next(
            (
                event
                for event in self._events
                if event.event_id == event_id and event.session_id == session_id
            ),
            None,
        )


@pytest.mark.asyncio
async def test_returns_decomposed_requests_when_bodies_are_recorded() -> None:
    # Arrange
    service = LlmRequestQueryService(_EventRepositoryStub([_body_event("e1", "S")]))

    # Act
    page = await service.list_requests(_SESSION_ID, _RUN_ID)

    # Assert
    assert [record.system for record in page.records] == ["S"]


@pytest.mark.asyncio
async def test_flags_more_results_when_scan_limit_is_reached() -> None:
    # Arrange
    events = [_body_event(f"e{index}", "S", index) for index in range(4)]
    service = LlmRequestQueryService(_EventRepositoryStub(events))

    # Act
    page = await service.list_requests(_SESSION_ID, _RUN_ID, limit=2)

    # Assert
    assert page.has_more is True


@pytest.mark.asyncio
async def test_returns_only_the_requested_page_when_scan_limit_is_reached() -> None:
    # Arrange
    events = [_body_event(f"e{index}", "S", index) for index in range(4)]
    service = LlmRequestQueryService(_EventRepositoryStub(events))

    # Act
    page = await service.list_requests(_SESSION_ID, _RUN_ID, limit=2)

    # Assert
    assert len(page.records) == 2


@pytest.mark.asyncio
async def test_returns_request_detail_when_event_id_matches_a_request_body() -> None:
    # Arrange
    service = LlmRequestQueryService(_EventRepositoryStub([_body_event("e1", "S")]))

    # Act
    record = await service.get_request(_SESSION_ID, "e1")

    # Assert
    assert record is not None and record.system == "S"


@pytest.mark.asyncio
async def test_returns_none_when_event_is_not_a_request_body() -> None:
    # Arrange
    event = _body_event("e1", "S")
    event.event_name = "api_request"
    service = LlmRequestQueryService(_EventRepositoryStub([event]))

    # Act
    record = await service.get_request(_SESSION_ID, "e1")

    # Assert
    assert record is None


@pytest.mark.asyncio
async def test_returns_none_when_event_belongs_to_another_session() -> None:
    # Arrange
    service = LlmRequestQueryService(_EventRepositoryStub([_body_event("e1", "S")]))

    # Act
    record = await service.get_request("other001", "e1")

    # Assert
    assert record is None
