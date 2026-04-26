from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from application.scheduler.scheduler_application_service import SchedulerApplicationService
from ohs.dependencies import get_scheduler_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/schedules", tags=["Scheduler"])

ServiceDep = Annotated[
    SchedulerApplicationService,
    Depends(get_scheduler_application_service),
]


class ScheduledTaskRequest(BaseModel):
    project_id: str = Field(default="")
    session_id: str = Field(default="")
    channel_id: str = Field(default="", max_length=8)
    name: str = Field(default="Scheduled task", max_length=255)
    prompt: str = Field(min_length=1)
    cron_expr: str = Field(default="*/30 * * * *", max_length=64)
    enabled: bool = True
    auto_unbind_after_run: bool = True
    delete_session_on_success: bool = False


class ScheduledTaskPatchRequest(BaseModel):
    session_id: str | None = Field(default=None)
    channel_id: str | None = Field(default=None, max_length=8)
    name: str | None = Field(default=None, max_length=255)
    prompt: str | None = None
    cron_expr: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    auto_unbind_after_run: bool | None = None
    delete_session_on_success: bool | None = None


@router.get("", summary="List scheduled tasks")
async def list_schedules(
    service: ServiceDep,
    project_id: str = Query(default=""),
) -> ApiResponse[dict]:
    return ApiResponse.success({"tasks": await service.list_tasks(project_id=project_id)})


@router.post("", summary="Create scheduled task")
async def create_schedule(
    request: ScheduledTaskRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    task = await service.create_task(
        project_id=request.project_id,
        session_id=request.session_id,
        name=request.name,
        prompt=request.prompt,
        cron_expr=request.cron_expr,
        enabled=request.enabled,
        channel_id=request.channel_id,
        auto_unbind_after_run=request.auto_unbind_after_run,
        delete_session_on_success=request.delete_session_on_success,
    )
    return ApiResponse.success({"task": service.task_to_dict(task)})


@router.patch("/{task_id}", summary="Update scheduled task")
async def update_schedule(
    task_id: str,
    request: ScheduledTaskPatchRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    task = await service.update_task(
        task_id,
        session_id=request.session_id,
        name=request.name,
        prompt=request.prompt,
        cron_expr=request.cron_expr,
        enabled=request.enabled,
        channel_id=request.channel_id,
        auto_unbind_after_run=request.auto_unbind_after_run,
        delete_session_on_success=request.delete_session_on_success,
    )
    return ApiResponse.success({"task": service.task_to_dict(task)})


@router.delete("/{task_id}", summary="Delete scheduled task")
async def delete_schedule(task_id: str, service: ServiceDep) -> ApiResponse[None]:
    await service.delete_task(task_id)
    return ApiResponse.success()


@router.post("/{task_id}/run-now", summary="Run scheduled task now")
async def run_schedule_now(task_id: str, service: ServiceDep) -> ApiResponse[dict]:
    run = await service.run_now(task_id)
    return ApiResponse.success({"run": service.run_to_dict(run)})
