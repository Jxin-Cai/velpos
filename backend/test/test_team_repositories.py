from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from domain.session.model.session import Session
from domain.team.model.card_execution import CardExecution
from domain.team.model.handoff import Handoff
from domain.team.model.status import CardExecutionStatus, WishCardStatus
from domain.team.model.team import Team
from domain.team.model.wish_card import WishCard
from infr.config.base import Base
from infr.repository.card_execution_repository_impl import CardExecutionRepositoryImpl
from infr.repository.handoff_repository_impl import HandoffRepositoryImpl
from infr.repository.project_model import ProjectModel
from infr.repository.session_model import SessionModel
from infr.repository.session_repository_impl import SessionRepositoryImpl
from infr.repository.team_model import (
    AgentSlotModel,
    CardExecutionModel,
    CardHandoffModel,
    HandoffArtifactModel,
    TeamModel,
    WishCardModel,
)
from infr.repository.team_repository_impl import TeamRepositoryImpl
from infr.repository.wish_card_repository_impl import WishCardRepositoryImpl


@compiles(MEDIUMTEXT, "sqlite")
def _compile_mediumtext_for_sqlite(_type: MEDIUMTEXT, _compiler, **_kwargs) -> str:
    return "TEXT"


_TABLES = [
    ProjectModel.__table__,
    TeamModel.__table__,
    AgentSlotModel.__table__,
    WishCardModel.__table__,
    CardExecutionModel.__table__,
    CardHandoffModel.__table__,
    HandoffArtifactModel.__table__,
    SessionModel.__table__,
]
_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=_TABLES,
            )
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            ProjectModel(
                id="proj0001",
                name="Project",
                dir_path="/tmp/project",
                created_time=_NOW,
                updated_time=_NOW,
            )
        )
        await session.flush()
        yield session
        await session.rollback()
    await engine.dispose()


def _team() -> Team:
    team = Team(
        id="team-1",
        project_id="proj0001",
        name="Delivery",
        created_at=_NOW,
        updated_at=_NOW,
    )
    team.add_agent_slot("backend", "Backend engineer", "workspace/backend")
    team.add_agent_slot("reviewer", "Reviewer", "workspace/reviewer")
    return team


async def _save_team(session: AsyncSession) -> Team:
    team = _team()
    await TeamRepositoryImpl(session).save(team)
    return team


def _card(team: Team, created_at: datetime = _NOW) -> WishCard:
    return WishCard(
        id=f"card-{created_at.minute}",
        team_id=team.id,
        title=f"Card {created_at.minute}",
        description="Persist all card fields",
        status=WishCardStatus.BACKLOG,
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.mark.asyncio
async def test_team_round_trip_when_saved_with_agent_slots(db_session: AsyncSession) -> None:
    # Arrange
    team = _team()
    repository = TeamRepositoryImpl(db_session)

    # Act
    await repository.save(team)
    loaded = await repository.find_by_project_id(team.project_id)

    # Assert
    assert loaded == team


@pytest.mark.asyncio
async def test_team_none_when_id_does_not_exist(db_session: AsyncSession) -> None:
    # Arrange
    repository = TeamRepositoryImpl(db_session)

    # Act
    loaded = await repository.find_by_id("missing")

    # Assert
    assert loaded is None


@pytest.mark.asyncio
async def test_wish_card_round_trip_when_saved_with_execution(db_session: AsyncSession) -> None:
    # Arrange
    team = await _save_team(db_session)
    card = _card(team)
    execution = card.assign_to(team.agent_slots[0].id)
    card.start_execution(execution.id)
    repository = WishCardRepositoryImpl(db_session)

    # Act
    await repository.save(card)
    loaded = await repository.find_by_id(card.id)

    # Assert
    assert loaded == card


@pytest.mark.asyncio
async def test_wish_cards_ordered_by_created_time_when_listed(db_session: AsyncSession) -> None:
    # Arrange
    team = await _save_team(db_session)
    later = _card(team, _NOW + timedelta(minutes=2))
    earlier = _card(team, _NOW + timedelta(minutes=1))
    repository = WishCardRepositoryImpl(db_session)
    await repository.save(later)
    await repository.save(earlier)

    # Act
    cards = await repository.find_by_team_id(team.id)

    # Assert
    assert [card.id for card in cards] == [earlier.id, later.id]


@pytest.mark.asyncio
async def test_execution_round_trip_when_saved_independently(db_session: AsyncSession) -> None:
    # Arrange
    team = await _save_team(db_session)
    card = _card(team)
    await WishCardRepositoryImpl(db_session).save(card)
    execution = CardExecution(
        id="execution-1",
        card_id=card.id,
        agent_slot_id=team.agent_slots[0].id,
        status=CardExecutionStatus.FAILED,
        failure_reason="Expected failure",
        created_at=_NOW,
        started_at=_NOW + timedelta(seconds=1),
        ended_at=_NOW + timedelta(seconds=2),
        idempotency_key="move-request-1",
    )
    repository = CardExecutionRepositoryImpl(db_session)

    # Act
    await repository.save(execution)
    loaded = await repository.find_by_id(execution.id)

    # Assert
    assert loaded == execution


@pytest.mark.asyncio
async def test_executions_ordered_by_created_time_when_listed(db_session: AsyncSession) -> None:
    # Arrange
    team = await _save_team(db_session)
    card = _card(team)
    await WishCardRepositoryImpl(db_session).save(card)
    repository = CardExecutionRepositoryImpl(db_session)
    later = CardExecution(
        "execution-2", card.id, team.agent_slots[0].id,
        CardExecutionStatus.PREPARING, _NOW + timedelta(minutes=2),
    )
    earlier = CardExecution(
        "execution-1", card.id, team.agent_slots[0].id,
        CardExecutionStatus.PREPARING, _NOW + timedelta(minutes=1),
    )
    await repository.save(later)
    await repository.save(earlier)

    # Act
    executions = await repository.find_by_card_id(card.id)

    # Assert
    assert [execution.id for execution in executions] == [earlier.id, later.id]


@pytest.mark.asyncio
async def test_handoff_round_trip_when_saved_with_artifact(db_session: AsyncSession) -> None:
    # Arrange
    team = await _save_team(db_session)
    card = _card(team)
    execution = card.assign_to(team.agent_slots[0].id)
    await WishCardRepositoryImpl(db_session).save(card)
    handoff = Handoff.create(
        team.id,
        card.id,
        execution.id,
        team.agent_slots[0].id,
        team.agent_slots[1].id,
        "Continue implementation",
    )
    handoff.add_artifact("notes", "artifacts/notes.md", "text/markdown")
    repository = HandoffRepositoryImpl(db_session)

    # Act
    await repository.save(handoff)
    loaded = await repository.find_by_id(handoff.id)

    # Assert
    assert loaded == handoff


@pytest.mark.asyncio
async def test_handoffs_ordered_by_created_time_when_listed(
    db_session: AsyncSession,
) -> None:
    # Arrange
    team = await _save_team(db_session)
    card = _card(team)
    execution = card.assign_to(team.agent_slots[0].id)
    await WishCardRepositoryImpl(db_session).save(card)
    repository = HandoffRepositoryImpl(db_session)
    later = Handoff.create(
        team.id,
        card.id,
        execution.id,
        team.agent_slots[0].id,
        team.agent_slots[1].id,
        "Later handoff",
    )
    later.created_at = _NOW + timedelta(minutes=2)
    earlier = Handoff.create(
        team.id,
        card.id,
        execution.id,
        team.agent_slots[0].id,
        team.agent_slots[1].id,
        "Earlier handoff",
    )
    earlier.created_at = _NOW + timedelta(minutes=1)
    await repository.save(later)
    await repository.save(earlier)

    # Act
    handoffs = await repository.find_by_card_id(card.id)

    # Assert
    assert [handoff.id for handoff in handoffs] == [earlier.id, later.id]


@pytest.mark.asyncio
async def test_session_associations_round_trip_when_execution_is_linked(
    db_session: AsyncSession,
) -> None:
    # Arrange
    team = await _save_team(db_session)
    card = _card(team)
    execution = card.assign_to(team.agent_slots[0].id)
    await WishCardRepositoryImpl(db_session).save(card)
    session = Session.create(
        card_execution_id=execution.id,
        agent_slot_id=team.agent_slots[0].id,
    )
    repository = SessionRepositoryImpl(db_session)

    # Act
    await repository.save(session)
    loaded = await repository.find_by_id(session.session_id)

    # Assert
    assert loaded is not None
    assert loaded.card_execution_id == execution.id
    assert loaded.agent_slot_id == team.agent_slots[0].id


def test_session_associations_none_when_created_without_team_fields() -> None:
    # Arrange and Act
    session = Session.create(model="legacy-model")

    # Assert
    assert session.card_execution_id is None
    assert session.agent_slot_id is None
