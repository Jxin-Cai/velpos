from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.plugin.plugin_application_service import PluginApplicationService
from ohs.dependencies import get_plugin_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.plugin_dto import (
    PluginActionRequest,
    PluginActionResponse,
    PluginInfo,
    PluginListResponse,
)

router = APIRouter(prefix="/api/plugins", tags=["Plugin"])

ServiceDep = Annotated[
    PluginApplicationService,
    Depends(get_plugin_application_service),
]


@router.get("", summary="List plugins")
async def list_plugins(
    service: ServiceDep,
    project_dir: str = Query(..., description="Project directory path"),
) -> ApiResponse[PluginListResponse]:
    result = await service.list_plugins(project_dir)
    plugins = [PluginInfo(**p) for p in result["plugins"]]
    return ApiResponse.success(PluginListResponse(plugins=plugins))


@router.post("/install", summary="Install plugin")
async def install_plugin(
    request: PluginActionRequest,
    service: ServiceDep,
) -> ApiResponse[PluginActionResponse]:
    message = await service.install_plugin(request.plugin, request.project_dir)
    return ApiResponse.success(PluginActionResponse(message=message))


@router.post("/uninstall", summary="Uninstall plugin")
async def uninstall_plugin(
    request: PluginActionRequest,
    service: ServiceDep,
) -> ApiResponse[PluginActionResponse]:
    message = await service.uninstall_plugin(request.plugin, request.project_dir)
    return ApiResponse.success(PluginActionResponse(message=message))
