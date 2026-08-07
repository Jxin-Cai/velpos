from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.plugin.plugin_application_service import PluginApplicationService
from infr.client.claude_agent_gateway import ClaudeAgentGateway
from ohs.auth_dependency import require_admin
from ohs.dependencies import get_claude_agent_gateway, get_plugin_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.plugin_dto import (
    MarketplaceInfo,
    MarketplaceListResponse,
    MarketplaceUpdateRequest,
    PluginActionRequest,
    PluginActionResponse,
    PluginInfo,
    PluginListResponse,
    PluginUpgradeAllRequest,
)

router = APIRouter(
    prefix="/api/plugins",
    tags=["Plugin"],
    dependencies=[Depends(require_admin)],
)

ServiceDep = Annotated[
    PluginApplicationService,
    Depends(get_plugin_application_service),
]
GatewayDep = Annotated[ClaudeAgentGateway, Depends(get_claude_agent_gateway)]


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


@router.post("/upgrade", summary="Upgrade a single plugin")
async def upgrade_plugin(
    request: PluginActionRequest,
    service: ServiceDep,
    gateway: GatewayDep,
) -> ApiResponse[PluginActionResponse]:
    message = await service.upgrade_plugin(request.plugin, request.project_dir)
    await gateway.disconnect_by_cwd(request.project_dir)
    return ApiResponse.success(PluginActionResponse(message=message))


@router.post("/upgrade-all", summary="Upgrade all project plugins")
async def upgrade_all_plugins(
    request: PluginUpgradeAllRequest,
    service: ServiceDep,
    gateway: GatewayDep,
) -> ApiResponse[PluginActionResponse]:
    message = await service.upgrade_all_plugins(request.project_dir)
    await gateway.disconnect_by_cwd(request.project_dir)
    return ApiResponse.success(PluginActionResponse(message=message))


@router.get("/marketplaces", summary="List configured marketplaces")
async def list_marketplaces(
    service: ServiceDep,
) -> ApiResponse[MarketplaceListResponse]:
    result = await service.list_marketplaces()
    marketplaces = [MarketplaceInfo(**m) for m in result]
    return ApiResponse.success(MarketplaceListResponse(marketplaces=marketplaces))


@router.post("/marketplaces/update", summary="Update marketplace(s)")
async def update_marketplace(
    request: MarketplaceUpdateRequest,
    service: ServiceDep,
) -> ApiResponse[PluginActionResponse]:
    message = await service.update_marketplace(request.name)
    return ApiResponse.success(PluginActionResponse(message=message))


@router.delete("/marketplaces/{name}", summary="Remove a marketplace")
async def remove_marketplace(
    name: str,
    service: ServiceDep,
) -> ApiResponse[PluginActionResponse]:
    message = await service.remove_marketplace(name)
    return ApiResponse.success(PluginActionResponse(message=message))
