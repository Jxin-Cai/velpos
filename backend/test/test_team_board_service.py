from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.session.command.create_session_command import CreateSessionCommand
from application.team_board.commands import MoveWishCardCommand
from application.team_board.card_execution_service import CardExecutionService
from application.team_board.execution_reconciliation_service import ExecutionReconciliationService
from application.team_board.leader_session_manager import (
    LeaderSessionManager,
    resolve_leader_api_base_url,
)
from application.team_board.team_workspace_helpers import (
    ensure_agent_project,
    prepare_execution_workspace,
)
from domain.team.acl.workspace_gateway import WorkspaceUnavailableError
from domain.team.model.status import SlotAvailability
from domain.session.model.session_status import SessionStatus
from domain.team.model.team import Team
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.model.wish_card import WishCard
from application.team_board.stage_output_builder import StageOutputBuilder
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType


def test_leader_api_base_url_uses_backend_port_when_dedicated_port_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.delenv("VELPOS_PORT", raising=False)
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.setenv("BACKEND_PORT", "9123")

    # Act
    result = resolve_leader_api_base_url()

    # Assert
    assert result == "http://localhost:9123"


def test_leader_prompt_contains_current_coordination_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_PORT", "8083")
    team = Team.create(project_id="project-1", name="Delivery")
    leader = team.add_agent_slot(
        name="Leader",
        role="product-manager",
        workspace_ref="/teams/delivery-leader",
    )
    worker = team.add_agent_slot(
        name="Developer",
        role="frontend-developer",
        workspace_ref="/teams/delivery-developer",
    )
    from domain.team.model.status import SlotRole

    leader.slot_role = SlotRole.LEADER
    card = WishCard.create(
        team_id=team.id,
        title="Implement login",
        description="Create the login flow",
    )
    service = object.__new__(CardExecutionService)
    service._leader_session_manager = SimpleNamespace(
        build_coordination_context=LeaderSessionManager.build_coordination_context
    )

    # Act
    prompt = service._build_leader_prompt(team, card, None, None)

    # Assert
    expected_identifiers = (
        "http://localhost:8083",
        team.id,
        card.id,
        leader.id,
        worker.id,
    )
    assert all(identifier in prompt for identifier in expected_identifiers)


@pytest.mark.asyncio
async def test_new_leader_session_created_when_persisted_session_is_in_error() -> None:
    # Arrange
    team = Team.create(project_id="project-1", name="Delivery")
    leader = team.add_agent_slot(
        name="Leader",
        role="product-manager",
        workspace_ref="/teams/delivery-leader",
    )
    team.leader_session_id = "failed-session"
    failed_session = SimpleNamespace(
        session_id="failed-session",
        status=SessionStatus.ERROR,
    )
    replacement_session = SimpleNamespace(
        session_id="replacement-session",
        status=SessionStatus.IDLE,
    )
    team_repo = SimpleNamespace(
        find_by_id=AsyncMock(return_value=team),
        save=AsyncMock(),
    )
    manager = LeaderSessionManager(
        team_repo=team_repo,
        project_repo=SimpleNamespace(),
        session_service=SimpleNamespace(
            get_session=AsyncMock(return_value=failed_session)
        ),
        session_service_factory=AsyncMock(),
    )
    manager._create_leader_session = AsyncMock(return_value=replacement_session)

    # Act
    result = await manager.get_or_create_session(team, leader)

    # Assert
    assert result is replacement_session


@pytest.mark.asyncio
async def test_automation_permission_restored_when_existing_leader_session_is_reused() -> None:
    # Arrange
    team = Team.create(project_id="project-1", name="Delivery")
    leader = team.add_agent_slot(
        name="Leader",
        role="product-manager",
        workspace_ref="/teams/delivery-leader",
    )
    team.leader_session_id = "healthy-session"
    healthy_session = SimpleNamespace(
        session_id="healthy-session",
        status=SessionStatus.IDLE,
    )
    session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=healthy_session),
        set_permission_mode=AsyncMock(),
    )
    manager = LeaderSessionManager(
        team_repo=SimpleNamespace(),
        project_repo=SimpleNamespace(),
        session_service=session_service,
        session_service_factory=AsyncMock(),
    )

    # Act
    result = await manager.get_or_create_session(team, leader)

    # Assert
    assert result is healthy_session
    session_service.set_permission_mode.assert_awaited_once_with(
        "healthy-session",
        "bypassPermissions",
    )


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
    project = await ensure_agent_project(
        "delivery",
        slot,
        project_repo,
        user_id=42,
    )

    # Assert
    assert project.name == "delivery-Software architect"
    assert project.user_id == 42


@pytest.mark.asyncio
async def test_agent_project_inherits_owner_when_recreated_for_team_project() -> None:
    # Arrange
    project_repo = SimpleNamespace(
        find_by_dir_path=AsyncMock(return_value=None),
        find_by_id=AsyncMock(return_value=SimpleNamespace(user_id=42)),
        save=AsyncMock(),
    )
    slot = SimpleNamespace(
        name="Backend",
        role="backend-architect",
        workspace_ref="/teams/delivery-backend",
    )

    # Act
    project = await ensure_agent_project(
        "delivery",
        slot,
        project_repo,
        team_project_id="team-project",
    )

    # Assert
    assert project.user_id == 42


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
    changed = await service._reconcile_stuck_execution(execution)

    # Assert
    assert changed is False
    service._card_repo.find_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_failed_when_terminal_session_is_stale() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Interrupted work")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)
    execution.session_id = "session-1"
    card_repo = SimpleNamespace(
        find_by_id=AsyncMock(return_value=card),
        save_state=AsyncMock(),
    )
    execution_repo = SimpleNamespace(
        save=AsyncMock(),
        save_terminal_if_non_terminal=AsyncMock(return_value=True),
    )
    service = object.__new__(ExecutionReconciliationService)
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=SimpleNamespace(
            is_running=False,
            updated_time=datetime.now() - timedelta(minutes=3),
        ))
    )
    service._card_repo = card_repo
    service._execution_repo = execution_repo

    # Act
    changed = await service._reconcile_stuck_execution(execution)

    # Assert
    assert changed is True
    assert card.latest_execution.is_terminal
    execution_repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_sync_replayed_when_terminal_session_has_result() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Completed work")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)
    execution.session_id = "session-1"
    terminal_session = SimpleNamespace(
        session_id="session-1",
        is_running=False,
        is_compacting=False,
        updated_time=datetime.now() - timedelta(minutes=3),
        messages=[
            Message.create(
                MessageType.RESULT,
                {"is_error": False, "text": "Completed"},
            )
        ],
    )
    sync_terminal_session = AsyncMock()
    service = object.__new__(ExecutionReconciliationService)
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=terminal_session)
    )
    service._terminal_session_sync_fn = sync_terminal_session
    service._card_repo = SimpleNamespace(find_by_id=AsyncMock())

    # Act
    changed = await service._reconcile_stuck_execution(execution)

    # Assert
    assert changed is True
    sync_terminal_session.assert_awaited_once_with(
        terminal_session,
        succeeded=True,
        reason="",
    )


@pytest.mark.asyncio
async def test_failure_sync_replayed_when_terminal_session_has_no_result() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Interrupted work")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)
    execution.session_id = "session-1"
    terminal_session = SimpleNamespace(
        session_id="session-1",
        status=SimpleNamespace(value="error"),
        is_running=False,
        is_compacting=False,
        updated_time=datetime.now() - timedelta(minutes=3),
        messages=[],
    )
    sync_terminal_session = AsyncMock()
    service = object.__new__(ExecutionReconciliationService)
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=terminal_session)
    )
    service._terminal_session_sync_fn = sync_terminal_session

    # Act
    changed = await service._reconcile_stuck_execution(execution)

    # Assert
    assert changed is True
    sync_terminal_session.assert_awaited_once_with(
        terminal_session,
        succeeded=False,
        reason="Session ended without a terminal result (status=error)",
    )


@pytest.mark.asyncio
async def test_execution_failed_immediately_when_startup_recovery_ignores_grace() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Interrupted work")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)
    execution.session_id = "session-1"
    service = object.__new__(ExecutionReconciliationService)
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=SimpleNamespace(
            is_running=False,
            updated_time=datetime.now(),
        ))
    )
    service._card_repo = SimpleNamespace(
        find_by_id=AsyncMock(return_value=card),
        save_state=AsyncMock(),
    )
    service._execution_repo = SimpleNamespace(
        save=AsyncMock(),
        save_terminal_if_non_terminal=AsyncMock(return_value=True),
    )

    # Act
    changed = await service._reconcile_stuck_execution(
        execution,
        ignore_terminal_session_grace=True,
    )

    # Assert
    assert changed is True
    assert card.latest_execution.is_terminal


@pytest.mark.asyncio
async def test_execution_not_reported_as_reconciled_when_session_is_running() -> None:
    # Arrange
    execution = SimpleNamespace(
        id="execution-1",
        session_id="session-1",
        timeout_at=None,
    )
    service = object.__new__(ExecutionReconciliationService)
    service._execution_repo = SimpleNamespace(
        find_non_terminal=AsyncMock(return_value=[execution])
    )
    service._session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=SimpleNamespace(is_running=True))
    )

    # Act
    reconciled = await service.reconcile_non_terminal_executions()

    # Assert
    assert reconciled == []


@pytest.mark.asyncio
async def test_execution_failed_when_wish_card_is_missing() -> None:
    # Arrange
    execution = WishCard.create(
        team_id="team-1",
        title="Orphaned work",
    ).assign_to("slot-1")
    execution_repo = SimpleNamespace(
        save=AsyncMock(),
        save_terminal_if_non_terminal=AsyncMock(return_value=True),
    )
    service = object.__new__(ExecutionReconciliationService)
    service._execution_repo = execution_repo
    service._card_repo = SimpleNamespace(
        find_by_id=AsyncMock(return_value=None)
    )

    # Act
    changed = await service._reconcile_one(execution)

    # Assert
    assert changed is True
    assert execution.is_terminal
    execution_repo.save.assert_awaited_once_with(execution)


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


# ── _build_card_context_parts helper ────────────────────────────────────────

def test_card_context_parts_excludes_card_id_by_default() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="My Card", description="Do the thing")

    # Act
    parts = CardExecutionService._build_card_context_parts(card, None, None)

    # Assert
    card_part = next(p for p in parts if "愿望卡" in p)
    assert card.title in card_part
    assert card.description in card_part
    assert card.id not in card_part


def test_card_context_parts_includes_card_id_when_flag_is_true() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="My Card", description="Do the thing")

    # Act
    parts = CardExecutionService._build_card_context_parts(
        card, None, None, include_card_id=True
    )

    # Assert
    card_part = next(p for p in parts if "愿望卡" in p)
    assert card.id in card_part
    assert card.title in card_part
    assert card.description in card_part


def test_card_context_parts_includes_stage_output_section_when_provided() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Stage2")
    source_execution = card.assign_to("slot-1")
    stage_output = StageOutputBuilder.build(
        card=card,
        execution=source_execution,
        source_session_id="session-1",
        final_output="Phase one finished.",
    )

    # Act
    parts = CardExecutionService._build_card_context_parts(card, stage_output, None)

    # Assert – stage output section comes before the card section
    stage_part = next(p for p in parts if stage_output.id in p)
    assert stage_output.checksum in stage_part
    assert "Phase one finished." in stage_part


# ── LeaderSessionManager.append_message delegation ──────────────────────────

@pytest.mark.asyncio
async def test_append_message_delegates_to_dispatch_execution_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    dispatched: list[tuple] = []

    async def fake_dispatch(factory, session_id, prompt):
        dispatched.append((factory, session_id, prompt))

    import application.team_board.leader_session_manager as lsm_module

    monkeypatch.setattr(lsm_module, "dispatch_execution_query", fake_dispatch)

    factory = AsyncMock()
    manager = LeaderSessionManager(
        team_repo=SimpleNamespace(),
        project_repo=SimpleNamespace(),
        session_service=SimpleNamespace(),
        session_service_factory=factory,
    )

    # Act
    await manager.append_message("session-42", "hello leader")

    # Assert
    assert len(dispatched) == 1
    assert dispatched[0][0] is factory
    assert dispatched[0][1] == "session-42"
    assert dispatched[0][2] == "hello leader"
