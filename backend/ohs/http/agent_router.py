from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.agent.agent_application_service import AgentApplicationService
from ohs.dependencies import get_agent_application_service, get_project_repository
from ohs.http.api_response import ApiResponse
from ohs.http.dto.agent_dto import (
    AgentCategoryInfo,
    AgentInfo,
    AgentListResponse,
    LoadAgentRequest,
    UnloadAgentRequest,
)
from ohs.http.dto.project_dto import ProjectResponse

router = APIRouter(prefix="/api/agents", tags=["Agent"])

ServiceDep = Annotated[
    AgentApplicationService,
    Depends(get_agent_application_service),
]


@router.get("", summary="List all agents by category")
async def list_agents(
    service: ServiceDep,
    language: str = Query(default="en", pattern="^(en|zh)$"),
) -> ApiResponse[AgentListResponse]:
    result = await service.list_agents(language)
    categories = [
        AgentCategoryInfo(
            id=c["id"],
            name=c["name"],
            agents=[AgentInfo(**a) for a in c["agents"]],
        )
        for c in result["categories"]
    ]
    return ApiResponse.success(AgentListResponse(categories=categories))


@router.post("/projects/{project_id}/load", summary="Load agent for project")
async def load_agent(
    project_id: str,
    request: LoadAgentRequest,
    service: ServiceDep,
    project_repo=Depends(get_project_repository),
) -> ApiResponse[ProjectResponse]:
    project = await service.load_agent(
        project_id, request.agent_id, request.language, project_repo,
    )
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.post("/projects/{project_id}/unload", summary="Unload agent from project")
async def unload_agent(
    project_id: str,
    request: UnloadAgentRequest,
    service: ServiceDep,
    project_repo=Depends(get_project_repository),
) -> ApiResponse[ProjectResponse]:
    project = await service.unload_agent(
        project_id, project_repo,
    )
    return ApiResponse.success(ProjectResponse.from_domain(project))
