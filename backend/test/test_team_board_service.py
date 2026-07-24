from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.session.command.create_session_command import CreateSessionCommand
from application.team_board.commands import MoveWishCardCommand
from application.team_board.team_board_service import TeamBoardApplicationService
from domain.team.acl.workspace_gateway import WorkspaceUnavailableError
from domain.team.model.status import SlotAvailability
from domain.team.model.team import Team
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.model.wish_card import WishCard


@pytest.mark.asyncio
async def test_move_rejected_when_route_team_does_not_own_card() -> None:
    # Arrange
    card = WishCard.create(team_id="team-owner", title="Private card")
    service = object.__new__(TeamBoardApplicationService)
    service._card_repo = SimpleNamespace(find_by_id=lambda _card_id: _async_value(card))
    command = MoveWishCardCommand(
        team_id="different-team",
        card_id=card.id,
        target_slot_id="slot-1",
        card_version=card.version,
        idempotency_key="request-1",
    )

    # Act / Assert
    with pytest.raises(TeamDomainError, match="does not belong to team"):
        await service._move_card_locked(command)


@pytest.mark.asyncio
async def test_slot_marked_unstable_when_execution_workspace_is_unavailable() -> None:
    # Arrange
    team = Team.create(project_id="project-1", name="Delivery")
    slot = team.add_agent_slot(
        name="Backend",
        role="backend-architect",
        workspace_ref="/removed/team-backend",
    )
    saved_teams: list[Team] = []

    async def save_team(value: Team) -> None:
        saved_teams.append(value)

    def fail_to_create_workspace(_workspace_ref: str, _execution_id: str) -> str:
        raise WorkspaceUnavailableError("agent workspace is missing or invalid")

    service = object.__new__(TeamBoardApplicationService)
    service._team_repo = SimpleNamespace(save=save_team)
    service._workspace = SimpleNamespace(
        create_execution_workspace=fail_to_create_workspace
    )

    # Act / Assert
    with pytest.raises(TeamDomainError, match="workspace is unavailable"):
        await service._prepare_execution_workspace(team, slot, "execution-1")
    assert slot.availability is SlotAvailability.UNSTABLE
    assert saved_teams == [team]


@pytest.mark.asyncio
async def test_default_model_used_when_team_execution_session_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("DEFAULT_MODEL", "team-default-model")
    captured_commands: list[CreateSessionCommand] = []

    async def create_session(command: CreateSessionCommand) -> SimpleNamespace:
        captured_commands.append(command)
        return SimpleNamespace(session_id="session-1")

    service = object.__new__(TeamBoardApplicationService)
    service._session_service = SimpleNamespace(create_session=create_session)
    team = SimpleNamespace(project_id="project-1", name="Delivery")
    card = SimpleNamespace(title="Implement API", description="Build the endpoint")
    execution = SimpleNamespace(id="execution-1", agent_slot_id="slot-1")

    # Act
    await service._create_execution_session(
        team=team,
        card=card,
        execution=execution,
        workspace_path="/workspace/execution-1",
        handoff=None,
    )

    # Assert
    assert captured_commands[0].model == "team-default-model"


@pytest.mark.asyncio
async def test_execution_not_failed_when_terminal_session_is_recent() -> None:
    # Arrange
    execution = SimpleNamespace(
        id="execution-1",
        card_id="card-1",
        session_id="session-1",
    )
    session = SimpleNamespace(is_running=False, updated_time=datetime.now())
    service = object.__new__(TeamBoardApplicationService)
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session)
    )
    service._card_repo = SimpleNamespace(find_by_id=AsyncMock())

    # Act
    await service._reconcile_stuck_execution(execution)

    # Assert
    service._card_repo.find_by_id.assert_not_awaited()


async def _async_value(value):
    return value
