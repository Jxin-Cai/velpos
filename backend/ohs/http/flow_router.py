from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from application.team_board.commands import (
    AdvanceFlowCommand,
    CancelFlowPlanCommand,
    CompleteFlowPlanCommand,
    RegisterFlowPlanCommand,
)
from application.team_board.flow_engine_service import FlowEngineService
from application.team_board.board_query_service import BoardQueryService
from domain.team.model.flow_plan import FlowPlan
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.repository.flow_plan_repository import FlowPlanRepository
from infr.config.database import get_async_session
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/teams", tags=["Flow"])


# ── Dependency injection ─────────────────────────────────────


async def _get_flow_engine_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> FlowEngineService:
    from application.team_board.card_execution_service import CardExecutionService
    from application.team_board.leader_session_manager import LeaderSessionManager
    from infr.repository.card_execution_repository_impl import CardExecutionRepositoryImpl
    from infr.repository.flow_plan_repository_impl import FlowPlanRepositoryImpl
    from infr.repository.handoff_repository_impl import HandoffRepositoryImpl
    from infr.repository.stage_output_repository_impl import StageOutputRepositoryImpl
    from infr.repository.team_repository_impl import TeamRepositoryImpl
    from infr.repository.wish_card_repository_impl import WishCardRepositoryImpl
    from infr.repository.session_repository_impl import SessionRepositoryImpl
    from infr.repository.project_repository_impl import ProjectRepositoryImpl
    from infr.workspace.filesystem_workspace_gateway import FilesystemWorkspaceGateway
    from ohs.dependencies import (
        _connection_manager,
        _create_session_service,
        get_session_application_service,
        _fail_execution_on_dispatch_error,
    )
    from infr.client.session_context_collector_impl import SessionContextCollectorImpl

    team_repo = TeamRepositoryImpl(db_session)
    card_repo = WishCardRepositoryImpl(db_session)
    execution_repo = CardExecutionRepositoryImpl(db_session)
    handoff_repo = HandoffRepositoryImpl(db_session)
    stage_output_repo = StageOutputRepositoryImpl(db_session)
    flow_plan_repo = FlowPlanRepositoryImpl(db_session)
    session_repo = SessionRepositoryImpl(db_session)
    project_repo = ProjectRepositoryImpl(db_session)
    workspace_gw = FilesystemWorkspaceGateway()

    session_service = await get_session_application_service(db_session)

    leader_session_manager = LeaderSessionManager(
        team_repo=team_repo,
        project_repo=project_repo,
        session_service=session_service,
        session_service_factory=_create_session_service,
    )

    card_execution_service = CardExecutionService(
        team_repo=team_repo,
        card_repo=card_repo,
        execution_repo=execution_repo,
        handoff_repo=handoff_repo,
        stage_output_repo=stage_output_repo,
        workspace_gateway=workspace_gw,
        session_service=session_service,
        session_service_factory=_create_session_service,
        project_repo=project_repo,
        connection_manager=_connection_manager,
        session_repo=session_repo,
        fail_execution_fn=_fail_execution_on_dispatch_error,
        collect_artifacts_fn=SessionContextCollectorImpl.collect_session_artifacts,
        leader_session_manager=leader_session_manager,
    )

    return FlowEngineService(
        flow_plan_repo=flow_plan_repo,
        team_repo=team_repo,
        card_repo=card_repo,
        execution_repo=execution_repo,
        stage_output_repo=stage_output_repo,
        leader_session_manager=leader_session_manager,
        move_card_fn=card_execution_service.move_card,
        connection_manager=_connection_manager,
        commit_fn=db_session.commit,
    )


async def _get_board_query_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> BoardQueryService:
    from infr.repository.card_execution_repository_impl import CardExecutionRepositoryImpl
    from infr.repository.handoff_repository_impl import HandoffRepositoryImpl
    from infr.repository.stage_output_repository_impl import StageOutputRepositoryImpl
    from infr.repository.team_repository_impl import TeamRepositoryImpl
    from infr.repository.wish_card_repository_impl import WishCardRepositoryImpl
    from ohs.dependencies import get_session_application_service

    session_service = await get_session_application_service(db_session)

    return BoardQueryService(
        team_repo=TeamRepositoryImpl(db_session),
        card_repo=WishCardRepositoryImpl(db_session),
        execution_repo=CardExecutionRepositoryImpl(db_session),
        handoff_repo=HandoffRepositoryImpl(db_session),
        stage_output_repo=StageOutputRepositoryImpl(db_session),
        session_service=session_service,
    )


async def _get_flow_plan_repository(
    db_session: AsyncSession = Depends(get_async_session),
) -> FlowPlanRepository:
    from infr.repository.flow_plan_repository_impl import FlowPlanRepositoryImpl

    return FlowPlanRepositoryImpl(db_session)


FlowEngineDep = Annotated[FlowEngineService, Depends(_get_flow_engine_service)]
BoardQueryDep = Annotated[BoardQueryService, Depends(_get_board_query_service)]
FlowPlanRepoDep = Annotated[FlowPlanRepository, Depends(_get_flow_plan_repository)]


# ── Request/Response DTOs ────────────────────────────────────


class RegisterFlowPlanRequest(BaseModel):
    card_id: str
    mode: str
    step_slot_ids: list[str]


class AdvanceFlowRequest(BaseModel):
    card_id: str
    target_slot_id: str
    context: str = ""


class CompleteFlowPlanRequest(BaseModel):
    summary: str = ""


class CancelFlowPlanRequest(BaseModel):
    reason: str = ""


# ── Assembler helpers ────────────────────────────────────────


def _to_plan_response(plan: FlowPlan) -> dict:
    return {
        "id": plan.id,
        "team_id": plan.team_id,
        "card_id": plan.card_id,
        "mode": plan.mode.value,
        "status": plan.status.value,
        "steps": [
            {
                "id": step.id,
                "sequence": step.sequence,
                "target_slot_id": step.target_slot_id,
                "status": step.status.value,
                "execution_id": step.execution_id,
                "leader_notified_at": (
                    step.leader_notified_at.isoformat()
                    if step.leader_notified_at else None
                ),
            }
            for step in plan.steps
        ],
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }


def _to_agent_response(slot) -> dict:
    from infr.agent.catalog import get_agent_by_id

    profile = get_agent_by_id(slot.role) or {}
    return {
        "id": slot.id,
        "display_name": slot.name,
        "agent_profile_id": slot.role,
        "description": (
            profile.get("description_zh")
            or profile.get("description_en")
            or ""
        ),
        "capabilities": [
            plugin.get("name", "")
            for plugin in profile.get("plugins", [])
            if isinstance(plugin, dict) and plugin.get("name")
        ],
        "availability": slot.availability.value,
        "is_leader": slot.is_leader,
    }


# ── Endpoints ────────────────────────────────────────────────


@router.post("/{team_id}/flow/plans", summary="Register a flow plan")
async def register_flow_plan(
    team_id: str, body: RegisterFlowPlanRequest, service: FlowEngineDep
) -> ApiResponse[dict]:
    cmd = RegisterFlowPlanCommand(
        team_id=team_id,
        card_id=body.card_id,
        mode=body.mode,
        step_slot_ids=tuple(body.step_slot_ids),
    )
    try:
        plan = await service.register_flow_plan(cmd)
    except TeamDomainError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.success(_to_plan_response(plan))


@router.get("/{team_id}/flow/board-status", summary="Get board status including active plans")
async def get_flow_board_status(
    team_id: str, query: BoardQueryDep, flow_plan_repo: FlowPlanRepoDep
) -> ApiResponse[dict]:
    try:
        team, cards = await query.get_board(team_id)
    except TeamDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    active_plans = await flow_plan_repo.find_active_by_team_id(team_id)

    return ApiResponse.success({
        "team_id": team.id,
        "slots": [_to_agent_response(slot) for slot in team.agent_slots],
        "cards": [
            {
                "id": card.id,
                "title": card.title,
                "status": card.status.value,
                "current_slot_id": card.current_slot_id,
            }
            for card in cards
        ],
        "active_plans": [_to_plan_response(p) for p in active_plans],
    })


@router.post("/{team_id}/flow/advance", summary="Advance card to next slot (decision mode)")
async def advance_flow(
    team_id: str, body: AdvanceFlowRequest, service: FlowEngineDep
) -> ApiResponse[dict]:
    cmd = AdvanceFlowCommand(
        team_id=team_id,
        card_id=body.card_id,
        target_slot_id=body.target_slot_id,
        context=body.context,
    )
    try:
        plan = await service.advance_flow(cmd)
    except TeamDomainError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.success(_to_plan_response(plan))


@router.post(
    "/{team_id}/flow/plans/{plan_id}/complete",
    summary="Complete a flow plan",
)
async def complete_flow_plan(
    team_id: str, plan_id: str, body: CompleteFlowPlanRequest, service: FlowEngineDep
) -> ApiResponse[dict]:
    try:
        plan = await service.complete_plan(plan_id, team_id)
    except TeamDomainError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.success(_to_plan_response(plan))


@router.post(
    "/{team_id}/flow/plans/{plan_id}/cancel",
    summary="Cancel a flow plan",
)
async def cancel_flow_plan(
    team_id: str, plan_id: str, body: CancelFlowPlanRequest, service: FlowEngineDep
) -> ApiResponse[dict]:
    try:
        plan = await service.cancel_plan(plan_id, team_id, reason=body.reason)
    except TeamDomainError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.success(_to_plan_response(plan))


@router.get("/{team_id}/agents", summary="List team agents")
async def list_team_agents(team_id: str, query: BoardQueryDep) -> ApiResponse[list]:
    try:
        team, _ = await query.get_board(team_id)
    except TeamDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    agents = [_to_agent_response(slot) for slot in team.agent_slots]
    return ApiResponse.success(agents)
