from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from application.memory.project_memory_application_service import ProjectMemoryApplicationService
from domain.memory.model.project_memory_entry import ProjectMemoryEntry
from ohs.dependencies import get_project_memory_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/project-memories", tags=["Project Memory"])

ServiceDep = Annotated[
    ProjectMemoryApplicationService,
    Depends(get_project_memory_application_service),
]


class ProjectMemoryRequest(BaseModel):
    project_id: str = Field(default="")
    project_dir: str = Field(default="")
    memory_type: str = Field(default="note")
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(default="")
    source_session_id: str = Field(default="")
    source_message_id: str = Field(default="")
    visibility: str = Field(default="project")


class ProjectMemoryUpdateRequest(BaseModel):
    memory_type: str | None = None
    title: str | None = Field(default=None, max_length=255)
    content: str | None = None
    visibility: str | None = None
    state: str | None = None


def _memory_to_dict(entry: ProjectMemoryEntry) -> dict:
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "memory_type": entry.memory_type,
        "title": entry.title,
        "content": entry.content,
        "source_session_id": entry.source_session_id,
        "source_message_id": entry.source_message_id,
        "visibility": entry.visibility,
        "state": entry.state,
        "created_time": entry.created_time.isoformat(),
        "updated_time": entry.updated_time.isoformat(),
    }


@router.get("", summary="List project memories")
async def list_project_memories(
    service: ServiceDep,
    project_id: str = Query(default=""),
    project_dir: str = Query(default=""),
) -> ApiResponse[dict]:
    memories = await service.list_memories(project_id=project_id, project_dir=project_dir)
    return ApiResponse.success({"memories": [_memory_to_dict(memory) for memory in memories]})


@router.post("", summary="Create project memory")
async def create_project_memory(
    request: ProjectMemoryRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    memory = await service.create_memory(
        project_id=request.project_id,
        project_dir=request.project_dir,
        memory_type=request.memory_type,
        title=request.title,
        content=request.content,
        source_session_id=request.source_session_id,
        source_message_id=request.source_message_id,
        visibility=request.visibility,
    )
    return ApiResponse.success({"memory": _memory_to_dict(memory)})


@router.patch("/{memory_id}", summary="Update project memory")
async def update_project_memory(
    memory_id: str,
    request: ProjectMemoryUpdateRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    memory = await service.update_memory(
        memory_id=memory_id,
        title=request.title,
        content=request.content,
        memory_type=request.memory_type,
        visibility=request.visibility,
        state=request.state,
    )
    return ApiResponse.success({"memory": _memory_to_dict(memory)})


@router.delete("/{memory_id}", summary="Delete project memory")
async def delete_project_memory(
    memory_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_memory(memory_id)
    return ApiResponse.success()
