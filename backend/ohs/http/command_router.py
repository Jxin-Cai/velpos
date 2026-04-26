from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.command.command_application_service import CommandApplicationService
from application.command_policy.command_policy_application_service import CommandPolicyApplicationService
from ohs.dependencies import get_command_application_service, get_command_policy_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.command_dto import CommandInfo, CommandListResponse

router = APIRouter(prefix="/api/commands", tags=["Command"])

ServiceDep = Annotated[
    CommandApplicationService,
    Depends(get_command_application_service),
]


PolicyServiceDep = Annotated[
    CommandPolicyApplicationService,
    Depends(get_command_policy_application_service),
]


@router.get("", summary="List available commands")
async def list_commands(
    service: ServiceDep,
    policy_service: PolicyServiceDep,
    project_dir: str = Query(..., description="Project directory path"),
) -> ApiResponse[CommandListResponse]:
    commands = await service.list_commands(project_dir)
    commands = await policy_service.filter_commands(commands, project_dir)
    items = [CommandInfo(**c) for c in commands]
    return ApiResponse.success(CommandListResponse(commands=items))
