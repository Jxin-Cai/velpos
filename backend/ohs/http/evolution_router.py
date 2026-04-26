from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from application.evolution.evolution_application_service import EvolutionApplicationService
from ohs.dependencies import get_evolution_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/evolution", tags=["Evolution"])

ServiceDep = Annotated[
    EvolutionApplicationService,
    Depends(get_evolution_application_service),
]


class EvolutionExtractRequest(BaseModel):
    project_id: str = ""
    project_dir: str = ""
    session_id: str = ""
    limit: int = Field(default=80, ge=1, le=200)


class EvolutionProposalRequest(BaseModel):
    project_dir: str
    lessons: list[dict[str, Any]] | None = None


@router.get("/proposals")
async def list_evolution_proposals(
    service: ServiceDep,
    project_id: str = Query(default=""),
    project_dir: str = Query(default=""),
):
    proposals = await service.list_proposals(project_id=project_id, project_dir=project_dir)
    return ApiResponse.success({"proposals": proposals})


@router.post("/extract")
async def extract_evolution_lessons(body: EvolutionExtractRequest, service: ServiceDep):
    data = await service.extract_lessons(
        project_id=body.project_id,
        project_dir=body.project_dir,
        session_id=body.session_id,
        limit=body.limit,
    )
    return ApiResponse.success(data)


@router.post("/proposals/{proposal_id}/claude-md-draft")
async def create_evolution_claude_md_draft(
    proposal_id: str,
    body: EvolutionProposalRequest,
    service: ServiceDep,
):
    data = await service.create_claude_md_proposal(
        proposal_id=proposal_id,
        project_dir=body.project_dir,
        lessons=body.lessons,
    )
    return ApiResponse.success(data)


@router.post("/proposals/{proposal_id}/approve")
async def approve_evolution_proposal(proposal_id: str, service: ServiceDep):
    return ApiResponse.success({"proposal": await service.approve(proposal_id)})


@router.post("/proposals/{proposal_id}/reject")
async def reject_evolution_proposal(proposal_id: str, service: ServiceDep):
    return ApiResponse.success({"proposal": await service.reject(proposal_id)})
