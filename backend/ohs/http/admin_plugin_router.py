from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from application.plugin.plugin_application_service import PluginApplicationService
from ohs.auth_dependency import require_admin
from ohs.dependencies import get_plugin_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(
    prefix="/api/admin/plugins",
    tags=["Admin - Claude Plugins"],
    dependencies=[Depends(require_admin)],
)

ServiceDep = Annotated[
    PluginApplicationService,
    Depends(get_plugin_application_service),
]


class AddMarketplaceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=1024)
    token: str = Field(default="", max_length=2048)

    @field_validator("source")
    @classmethod
    def reject_embedded_credentials(cls, value: str) -> str:
        if re.match(r"^[a-z][a-z0-9+.-]*://[^/\s]*@", value, re.IGNORECASE):
            raise ValueError("Do not embed credentials in the market URL; use the token field")
        return value


class RefreshMarketplaceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str = Field(default="", max_length=2048)


@router.get("/marketplaces")
async def list_marketplaces(service: ServiceDep) -> ApiResponse[list]:
    return ApiResponse.success(await service.list_marketplaces())


@router.post("/marketplaces")
async def add_marketplace(
    request: AddMarketplaceRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    await service.add_marketplace(request.source, request.token)
    return ApiResponse.success({"source": request.source})


@router.post("/marketplaces/{name}/refresh")
async def refresh_marketplace(
    name: str,
    request: RefreshMarketplaceRequest,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.update_marketplace(name, request.token)
    return ApiResponse.success(None)


@router.delete("/marketplaces/{name}")
async def remove_marketplace(name: str, service: ServiceDep) -> ApiResponse[None]:
    await service.remove_marketplace(name)
    return ApiResponse.success(None)


@router.get("/marketplaces/{name}/plugins")
async def list_marketplace_plugins(
    name: str,
    service: ServiceDep,
) -> ApiResponse[list]:
    return ApiResponse.success(await service.list_marketplace_plugins(name))
