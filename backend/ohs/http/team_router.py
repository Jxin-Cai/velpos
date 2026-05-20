from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.team_task.team_coordinator_service import TeamCoordinatorService
from ohs.dependencies import get_team_coordinator_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/teams", tags=["Teams"])

ServiceDep = Annotated[
    TeamCoordinatorService,
    Depends(get_team_coordinator_service),
]


@router.get("/{project_id}/timeline/{session_id}", summary="Get team task timeline")
async def get_team_timeline(
    project_id: str,
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[list]:
    timeline = await service.get_team_timeline(session_id)
    return ApiResponse.success(timeline)


@router.get("/{project_id}/linked-sessions/{session_id}", summary="Get linked worker sessions")
async def get_linked_sessions(
    project_id: str,
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[list]:
    sessions = await service.get_linked_sessions(session_id)
    return ApiResponse.success(sessions)


@router.get("/{project_id}/tasks/{task_id}", summary="Get team task detail")
async def get_task_detail(
    project_id: str,
    task_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    detail = await service.get_task_detail(project_id, task_id)
    return ApiResponse.success(detail)


@router.post("/{project_id}/tasks/{task_id}/cancel", summary="Cancel a single team task")
async def cancel_task(
    project_id: str,
    task_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    await service.cancel_task(project_id, task_id)
    return ApiResponse.success({"task_id": task_id, "status": "cancelled"})


@router.post("/{project_id}/tasks/{task_id}/retry", summary="Retry a failed or cancelled task")
async def retry_task(
    project_id: str,
    task_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    result = await service.retry_task(project_id, task_id)
    return ApiResponse.success({"task_id": task_id, "result": result[:500]})


@router.get("/worker-context/{session_id}", summary="Get coordinator info for a worker session")
async def get_worker_context(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    ctx = await service.get_worker_context(session_id)
    return ApiResponse.success(ctx)
