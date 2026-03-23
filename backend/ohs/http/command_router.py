from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.command.command_application_service import CommandApplicationService
from ohs.dependencies import get_command_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.command_dto import CommandInfo, CommandListResponse

router = APIRouter(prefix="/api/commands", tags=["Command"])

ServiceDep = Annotated[
    CommandApplicationService,
    Depends(get_command_application_service),
]


@router.get("", summary="List available commands")
async def list_commands(
    service: ServiceDep,
    project_dir: str = Query(..., description="Project directory path"),
) -> ApiResponse[CommandListResponse]:
    commands = await service.list_commands(project_dir)
    items = [CommandInfo(**c) for c in commands]
    return ApiResponse.success(CommandListResponse(commands=items))
