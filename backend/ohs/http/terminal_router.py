from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.terminal.command.execute_terminal_command import ExecuteTerminalCommand
from application.terminal.terminal_application_service import TerminalApplicationService
from ohs.dependencies import get_terminal_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.terminal_dto import ExecuteTerminalRequest, OpenPathRequest

router = APIRouter(prefix="/api/terminal", tags=["Terminal"])

ServiceDep = Annotated[
    TerminalApplicationService,
    Depends(get_terminal_application_service),
]


@router.post("/execute", summary="Execute terminal command")
async def execute_command(
    request: ExecuteTerminalRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    command = ExecuteTerminalCommand(
        command=request.command,
        timeout=request.timeout,
        cwd=request.cwd,
    )
    result = await service.execute_command(command)
    return ApiResponse.success(result)


@router.post("/open-path", summary="Open file or directory with system handler")
async def open_path(
    request: OpenPathRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    result = await service.open_path(request.path)
    return ApiResponse.success(result)
