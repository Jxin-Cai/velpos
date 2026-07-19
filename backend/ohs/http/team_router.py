from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from application.team_board.commands import (
    AgentSlotConfig,
    ArchiveWishCardCommand,
    CreateTeamCommand,
    CreateWishCardCommand,
    DeleteWishCardCommand,
    MoveWishCardCommand,
    RetryExecutionCommand,
)
from application.team_board.team_board_service import TeamBoardApplicationService
from domain.team.model.team_domain_error import TeamDomainError
from ohs.dependencies import get_team_board_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/teams", tags=["Teams"])

ServiceDep = Annotated[TeamBoardApplicationService, Depends(get_team_board_service)]


class SlotDTO(BaseModel):
    display_name: str
    agent_profile_id: str
    slug: str = ""


class CreateTeamRequest(BaseModel):
    name: str
    project_id: str
    root_path: str
    slots: list[SlotDTO]


class CreateCardRequest(BaseModel):
    title: str
    description: str = ""


class MoveCardRequest(BaseModel):
    target_slot_id: str
    card_version: int
    idempotency_key: str


class ArchiveCardRequest(BaseModel):
    card_version: int


@router.post("", summary="Create a team with agent slots")
async def create_team(body: CreateTeamRequest, service: ServiceDep) -> ApiResponse[dict]:
    cmd = CreateTeamCommand(
        name=body.name,
        project_id=body.project_id,
        root_path=body.root_path,
        slots=tuple(AgentSlotConfig(
            display_name=s.display_name,
            agent_profile_id=s.agent_profile_id,
            slug=s.slug,
        ) for s in body.slots),
    )
    team = await service.create_team(cmd)
    return ApiResponse.success({"id": team.id, "name": team.name})


@router.get("", summary="List teams for a project")
async def list_teams(project_id: str, service: ServiceDep) -> ApiResponse[list]:
    teams = await service.list_teams(project_id)
    return ApiResponse.success([{"id": team.id, "name": team.name} for team in teams])


@router.get("/{team_id}/board", summary="Get board with cards and executions")
async def get_board(team_id: str, service: ServiceDep) -> ApiResponse[dict]:
    try:
        team, cards = await service.get_board(team_id)
    except TeamDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    slots = [{"id": s.id, "display_name": s.name, "agent_profile_id": s.role}
             for s in team.agent_slots]
    card_list = []
    for card in cards:
        latest = card.latest_execution
        card_list.append({
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "status": card.status.value,
            "current_slot_id": card.current_slot_id,
            "version": card.version,
            "session_id": latest.session_id if latest else None,
            "execution_id": latest.id if latest else None,
            "failure_reason": latest.failure_reason if latest else None,
            "needs_user_action": await service.execution_needs_user_action(latest),
            "execution_history": await service.get_card_history(latest.id) if latest else [],
        })
    return ApiResponse.success({"team_id": team.id, "name": team.name, "slots": slots, "cards": card_list})


@router.post("/{team_id}/cards", summary="Create a wish card")
async def create_card(team_id: str, body: CreateCardRequest, service: ServiceDep) -> ApiResponse[dict]:
    cmd = CreateWishCardCommand(team_id=team_id, title=body.title, description=body.description)
    try:
        card = await service.create_card(cmd)
    except TeamDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ApiResponse.success({
        "id": card.id,
        "title": card.title,
        "description": card.description,
        "status": card.status.value,
        "current_slot_id": card.current_slot_id,
        "version": card.version,
        "session_id": None,
    })


@router.post("/{team_id}/cards/{card_id}/archive", summary="Archive a finished wish card")
async def archive_card(
    team_id: str, card_id: str, body: ArchiveCardRequest, service: ServiceDep
) -> ApiResponse[dict]:
    try:
        card = await service.archive_card(ArchiveWishCardCommand(
            team_id=team_id,
            card_id=card_id,
            card_version=body.card_version,
        ))
    except TeamDomainError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.success({
        "id": card.id,
        "status": card.status.value,
        "current_slot_id": card.current_slot_id,
        "version": card.version,
    })


@router.delete("/{team_id}/cards/{card_id}", summary="Delete an archived wish card")
async def delete_card(team_id: str, card_id: str, service: ServiceDep) -> ApiResponse[dict]:
    try:
        await service.delete_archived_card(DeleteWishCardCommand(
            team_id=team_id,
            card_id=card_id,
        ))
    except TeamDomainError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ApiResponse.success({"id": card_id})


@router.post("/{team_id}/cards/{card_id}/moves", summary="Move card to an agent slot")
async def move_card(
    team_id: str, card_id: str, body: MoveCardRequest, service: ServiceDep
) -> ApiResponse[dict]:
    cmd = MoveWishCardCommand(
        team_id=team_id,
        card_id=card_id,
        target_slot_id=body.target_slot_id,
        card_version=body.card_version,
        idempotency_key=body.idempotency_key,
    )
    try:
        execution = await service.move_card(cmd)
    except TeamDomainError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse.success({
        "execution_id": execution.id,
        "status": execution.status.value,
        "session_id": execution.session_id,
    })


@router.post("/executions/{execution_id}/retry", summary="Retry a failed execution")
async def retry_execution(execution_id: str, service: ServiceDep) -> ApiResponse[dict]:
    cmd = RetryExecutionCommand(execution_id=execution_id)
    try:
        execution = await service.retry_execution(cmd)
    except TeamDomainError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse.success({
        "execution_id": execution.id,
        "status": execution.status.value,
    })


@router.get("/executions/{execution_id}", summary="Get execution details")
async def get_execution(execution_id: str, service: ServiceDep) -> ApiResponse[dict]:
    try:
        execution = await service.get_execution(execution_id)
    except TeamDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ApiResponse.success({
        "id": execution.id,
        "card_id": execution.card_id,
        "agent_slot_id": execution.agent_slot_id,
        "status": execution.status.value,
        "session_id": execution.session_id,
    })


@router.get("/executions/{execution_id}/history", summary="Get wish card execution history")
async def get_execution_history(execution_id: str, service: ServiceDep) -> ApiResponse[list[dict]]:
    try:
        history = await service.get_card_history(execution_id)
    except TeamDomainError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ApiResponse.success(history)
