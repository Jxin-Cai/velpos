from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.session import Session
from domain.session.model.trace_span import TraceSpan
from infr.repository.project_model import ProjectModel
from infr.repository.session_model import SessionModel
from infr.repository.session_repository_impl import SessionRepositoryImpl
from infr.repository.team_model import (
    AgentSlotModel,
    CardExecutionModel,
    TeamModel,
    WishCardModel,
)
from infr.repository.trace_span_model import TraceSpanModel
from infr.repository.trace_span_repository_impl import TraceSpanRepositoryImpl
from test.db_fixture import sqlite_session

# SessionModel carries foreign keys into the team aggregate, so those tables must
# exist for the schema to be created even though this suite never writes them.
_TABLES = [
    ProjectModel.__table__,
    TeamModel.__table__,
    AgentSlotModel.__table__,
    WishCardModel.__table__,
    CardExecutionModel.__table__,
    SessionModel.__table__,
    TraceSpanModel.__table__,
]
_RUN_ID = "run-1"


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with sqlite_session(_TABLES) as session:
        yield session


async def _persisted_session(db_session: AsyncSession) -> Session:
    session = Session.create(model="claude-test", project_id="proj0001")
    await SessionRepositoryImpl(db_session).save(session)
    return session


def _span(session_id: str, sequence: int) -> TraceSpan:
    span = TraceSpan.create(
        session_id=session_id,
        run_id=_RUN_ID,
        span_type=TraceSpan.SPAN_TYPE_TOOL_CALL,
        name="Read",
    )
    span.sequence = sequence
    return span


@pytest.mark.asyncio
async def test_changes_run_version_when_span_revision_increases(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = TraceSpanRepositoryImpl(db_session)
    span = _span(session.session_id, sequence=1)
    await repository.save(span)
    version_before = await repository.find_run_version(session.session_id, _RUN_ID)

    # Act — a restarted collector replays low sequence numbers, so only the
    # revision proves that the span was rewritten.
    span.complete(output_preview="done")
    span.revision += 1
    await repository.update(span)

    # Assert
    version_after = await repository.find_run_version(session.session_id, _RUN_ID)
    assert version_after != version_before


@pytest.mark.asyncio
async def test_changes_run_version_when_span_is_appended(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = TraceSpanRepositoryImpl(db_session)
    await repository.save(_span(session.session_id, sequence=1))
    version_before = await repository.find_run_version(session.session_id, _RUN_ID)

    # Act
    await repository.save(_span(session.session_id, sequence=2))

    # Assert
    version_after = await repository.find_run_version(session.session_id, _RUN_ID)
    assert version_after != version_before


@pytest.mark.asyncio
async def test_keeps_run_version_stable_when_run_is_untouched(
    db_session: AsyncSession,
) -> None:
    # Arrange
    session = await _persisted_session(db_session)
    repository = TraceSpanRepositoryImpl(db_session)
    await repository.save(_span(session.session_id, sequence=1))

    # Act
    first = await repository.find_run_version(session.session_id, _RUN_ID)
    second = await repository.find_run_version(session.session_id, _RUN_ID)

    # Assert
    assert first == second
