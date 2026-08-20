from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.execution_ledger_event import (
    ExecutionLedgerEvent,
    ExecutionLedgerEventType,
)
from domain.session.model.session import Session
from infr.repository.execution_ledger_event_model import ExecutionLedgerEventModel
from infr.repository.execution_ledger_event_repository_impl import (
    ExecutionLedgerEventRepositoryImpl,
)
from infr.repository.project_model import ProjectModel
from infr.repository.session_model import SessionModel
from infr.repository.session_repository_impl import SessionRepositoryImpl
from infr.repository.team_model import (
    AgentSlotModel,
    CardExecutionModel,
    TeamModel,
    WishCardModel,
)
from test.db_fixture import sqlite_session

_TABLES = [
    ProjectModel.__table__,
    TeamModel.__table__,
    AgentSlotModel.__table__,
    WishCardModel.__table__,
    CardExecutionModel.__table__,
    SessionModel.__table__,
    ExecutionLedgerEventModel.__table__,
]
_RUN_ID = "run-1"
_NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with sqlite_session(_TABLES) as session:
        yield session


async def _persisted_session(db_session: AsyncSession) -> Session:
    session = Session.create(model="claude-test", project_id="proj0001")
    await SessionRepositoryImpl(db_session).save(session)
    return session


def _log_event(
    session_id: str,
    event_id: str,
    event_name: str,
    payload: dict | None = None,
) -> ExecutionLedgerEvent:
    return ExecutionLedgerEvent.from_otel_record(
        event_id=event_id,
        session_id=session_id,
        run_id=_RUN_ID,
        signal="log",
        event_name=event_name,
        event_time=_NOW,
        payload=payload if payload is not None else {"signal": "log", "event_name": event_name},
    )


def _metric_event(session_id: str, event_id: str, metric_name: str, value: float) -> ExecutionLedgerEvent:
    return ExecutionLedgerEvent.from_otel_record(
        event_id=event_id,
        session_id=session_id,
        run_id=_RUN_ID,
        signal="metric",
        event_name=metric_name,
        event_time=_NOW,
        payload={"signal": "metric", "metric_name": metric_name, "value": value},
    )


@pytest.mark.asyncio
async def test_counts_log_events_by_name_when_run_has_mixed_signals(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([
        _log_event(session.session_id, "e1", "api_request"),
        _log_event(session.session_id, "e2", "api_error"),
        _log_event(session.session_id, "e3", "api_error"),
        _metric_event(session.session_id, "e4", "claude_code.cost.usage", 0.5),
    ])

    # Act
    counts = await repository.count_by_run(session.session_id, _RUN_ID)

    # Assert
    assert counts.log_counts_by_name == {"api_request": 1, "api_error": 2}


@pytest.mark.asyncio
async def test_separates_metric_samples_from_log_events_when_counting_run(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([
        _log_event(session.session_id, "e1", "api_request"),
        _metric_event(session.session_id, "e2", "claude_code.cost.usage", 0.5),
        _metric_event(session.session_id, "e3", "claude_code.token.usage", 12),
    ])

    # Act
    counts = await repository.count_by_run(session.session_id, _RUN_ID)

    # Assert
    assert (counts.log_event_count, counts.metric_sample_count) == (1, 2)


@pytest.mark.asyncio
async def test_names_unnamed_log_events_as_log_when_counting_run(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([_log_event(session.session_id, "e1", "")])

    # Act
    counts = await repository.count_by_run(session.session_id, _RUN_ID)

    # Assert
    assert counts.log_counts_by_name == {"log": 1}


@pytest.mark.asyncio
async def test_clamps_event_name_to_column_width_when_otel_falls_back_to_body(
    db_session: AsyncSession,
) -> None:
    # Arrange — OTel uses the record body as the name when no name attribute is
    # emitted, and a body has no length limit.
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([_log_event(session.session_id, "e1", "b" * 500)])

    # Act
    counts = await repository.count_by_run(session.session_id, _RUN_ID)

    # Assert
    assert list(counts.log_counts_by_name) == ["b" * 64]


@pytest.mark.asyncio
async def test_returns_only_requested_names_when_selecting_cost_events(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([
        _log_event(session.session_id, "e1", "api_request"),
        _log_event(session.session_id, "e2", "api_error"),
    ])

    # Act
    events = await repository.find_by_event_names(
        session.session_id,
        _RUN_ID,
        ExecutionLedgerEventType.OTEL_LOG,
        ("api_request",),
    )

    # Assert
    assert [event.event_id for event in events] == ["e1"]


@pytest.mark.asyncio
async def test_returns_newest_events_oldest_first_when_recent_page_requested(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([
        _log_event(session.session_id, f"e{index}", "api_request")
        for index in range(5)
    ])

    # Act
    events = await repository.find_recent_by_type(
        session.session_id,
        _RUN_ID,
        ExecutionLedgerEventType.OTEL_LOG,
        limit=2,
    )

    # Assert
    assert [event.event_id for event in events] == ["e3", "e4"]


@pytest.mark.asyncio
async def test_returns_verbatim_payload_when_single_event_requested(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    body = "x" * 10000
    await repository.save_batch([
        _log_event(
            session.session_id,
            "e1",
            "api_request_body",
            payload={"signal": "log", "event_name": "api_request_body", "body": body},
        ),
    ])

    # Act
    event = await repository.find_by_event_id(session.session_id, "e1")

    # Assert
    assert event is not None and event.payload["body"] == body


@pytest.mark.asyncio
async def test_returns_none_when_event_belongs_to_another_session(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = ExecutionLedgerEventRepositoryImpl(db_session)
    await repository.save_batch([_log_event(session.session_id, "e1", "api_request")])

    # Act
    event = await repository.find_by_event_id("other001", "e1")

    # Assert
    assert event is None
