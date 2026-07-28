from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.session.command.create_session_command import CreateSessionCommand
from application.team_board.commands import MoveWishCardCommand
from application.team_board.card_execution_service import CardExecutionService
from application.team_board.execution_reconciliation_service import ExecutionReconciliationService
from application.team_board.team_workspace_helpers import (
    ensure_agent_project,
    prepare_execution_workspace,
)
from domain.team.acl.workspace_gateway import WorkspaceUnavailableError
from domain.team.model.status import SlotAvailability
from domain.team.model.team import Team
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.model.wish_card import WishCard
from application.team_board.stage_output_builder import StageOutputBuilder


@pytest.mark.asyncio
async def test_agent_project_uses_full_slot_name_when_project_is_missing() -> None:
    # Arrange
    project_repo = SimpleNamespace(
        find_by_dir_path=AsyncMock(return_value=None),
        save=AsyncMock(),
    )
    slot = SimpleNamespace(
        name="Software architect",
        role="software-architect",
        workspace_ref="/teams/delivery-agent-2",
    )

    # Act
    project = await ensure_agent_project("delivery", slot, project_repo)

    # Assert
    assert project.name == "delivery-Software architect"


@pytest.mark.asyncio
async def test_move_rejected_when_route_team_does_not_own_card() -> None:
    # Arrange
    card = WishCard.create(team_id="team-owner", title="Private card")
    service = object.__new__(CardExecutionService)
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

    workspace_gw = SimpleNamespace(
        create_execution_workspace=fail_to_create_workspace
    )
    team_repo = SimpleNamespace(save=save_team)

    # Act / Assert
    with pytest.raises(TeamDomainError, match="workspace is unavailable"):
        await prepare_execution_workspace(team, slot, "execution-1", workspace_gw, team_repo)
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

    service = object.__new__(CardExecutionService)
    service._session_service = SimpleNamespace(create_session=create_session)
    service._connection_manager = None
    team = SimpleNamespace(project_id="project-1", name="Delivery")
    card = SimpleNamespace(title="Implement API", description="Build the endpoint")
    execution = SimpleNamespace(id="execution-1", agent_slot_id="slot-1")

    # Act
    await service._create_execution_session(
        team=team,
        card=card,
        execution=execution,
        agent_project_id="agent-project-1",
        workspace_path="/workspace/execution-1",
        handoff=None,
    )

    # Assert
    assert captured_commands[0].model == "team-default-model"


@pytest.mark.asyncio
async def test_agent_project_used_when_team_execution_session_is_created() -> None:
    # Arrange
    captured_commands: list[CreateSessionCommand] = []

    async def create_session(command: CreateSessionCommand) -> SimpleNamespace:
        captured_commands.append(command)
        return SimpleNamespace(session_id="session-1")

    service = object.__new__(CardExecutionService)
    service._session_service = SimpleNamespace(create_session=create_session)
    service._connection_manager = None

    # Act
    await service._create_execution_session(
        team=SimpleNamespace(name="Delivery"),
        card=SimpleNamespace(title="Implement API", description="Build the endpoint"),
        execution=SimpleNamespace(id="execution-1", agent_slot_id="slot-1"),
        agent_project_id="agent-project-1",
        workspace_path="/workspace/execution-1",
        handoff=None,
    )

    # Assert
    assert captured_commands[0].project_id == "agent-project-1"


@pytest.mark.asyncio
async def test_frontend_notified_when_team_execution_session_is_created() -> None:
    # Arrange
    connection_manager = SimpleNamespace(broadcast_global=AsyncMock())
    service = object.__new__(CardExecutionService)
    service._session_service = SimpleNamespace(
        create_session=AsyncMock(return_value=SimpleNamespace(session_id="session-1"))
    )
    service._connection_manager = connection_manager

    # Act
    await service._create_execution_session(
        team=SimpleNamespace(id="team-1", name="Delivery"),
        card=SimpleNamespace(title="Implement API", description="Build the endpoint"),
        execution=SimpleNamespace(id="execution-1", agent_slot_id="slot-1"),
        agent_project_id="agent-project-1",
        workspace_path="/workspace/execution-1",
        handoff=None,
    )

    # Assert
    connection_manager.broadcast_global.assert_awaited_once_with({
        "event": "team_session_created",
        "team_id": "team-1",
        "project_id": "agent-project-1",
        "session_id": "session-1",
    })


@pytest.mark.asyncio
async def test_execution_not_failed_when_terminal_session_is_recent() -> None:
    # Arrange
    execution = SimpleNamespace(
        id="execution-1",
        card_id="card-1",
        session_id="session-1",
    )
    session = SimpleNamespace(is_running=False, updated_time=datetime.now())
    service = object.__new__(ExecutionReconciliationService)
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session)
    )
    service._card_repo = SimpleNamespace(find_by_id=AsyncMock())

    # Act
    await service._reconcile_stuck_execution(execution)

    # Assert
    service._card_repo.find_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_used_when_execution_session_is_created_from_previous_stage() -> None:
    # Arrange
    captured_commands: list[CreateSessionCommand] = []

    async def create_session(command: CreateSessionCommand) -> SimpleNamespace:
        captured_commands.append(command)
        return SimpleNamespace(session_id="session-2")

    card = WishCard.create(team_id="team-1", title="Continue implementation")
    source_execution = card.assign_to("slot-1")
    stage_output = StageOutputBuilder.build(
        card=card,
        execution=source_execution,
        source_session_id="session-1",
        final_output="Completed the domain model.",
    )
    service = object.__new__(CardExecutionService)
    service._session_service = SimpleNamespace(create_session=create_session)
    service._connection_manager = None

    # Act
    _, prompt = await service._create_execution_session(
        team=SimpleNamespace(project_id="project-1", name="Delivery"),
        card=card,
        execution=SimpleNamespace(id="execution-2", agent_slot_id="slot-2"),
        agent_project_id="agent-project-2",
        workspace_path="/workspace/execution-2",
        handoff=None,
        input_stage_output=stage_output,
    )

    # Assert
    assert stage_output.id in prompt
    assert stage_output.checksum in prompt
    assert "Completed the domain model." in prompt
    assert captured_commands[0].card_execution_id == "execution-2"


@pytest.mark.asyncio
async def test_handoff_references_exact_snapshot_when_stage_is_moved() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Continue implementation")
    source_execution = card.assign_to("slot-1")
    stage_output = StageOutputBuilder.build(
        card=card,
        execution=source_execution,
        source_session_id="session-1",
        final_output="Completed the domain model.",
    )
    saved_handoffs = []
    service = object.__new__(CardExecutionService)
    service._handoff_repo = SimpleNamespace(
        save=lambda handoff: _append_async(saved_handoffs, handoff)
    )
    target_execution = SimpleNamespace(id="execution-2")
    target_slot = SimpleNamespace(id="slot-2")

    # Act
    handoff = await service._prepare_handoff(
        source_execution,
        target_execution,
        target_slot,
        card,
        stage_output,
    )

    # Assert
    assert handoff.stage_output_id == stage_output.id
    assert handoff.target_execution_id == target_execution.id
    assert handoff.consumed_checksum == stage_output.checksum
    assert saved_handoffs == [handoff]


async def _async_value(value):
    return value


async def _append_async(items, value):
    items.append(value)
