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

_CLI_PREFIX = "CLI command failed: "


def _extract_cli_message(error: str) -> str:
    if error.startswith(_CLI_PREFIX):
        return error[len(_CLI_PREFIX):]
    return error

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
    def sanitize_source_url(cls, value: str) -> str:
        md_link = re.match(r"^\[.*?\]\((.+?)\)$", value)
        if md_link:
            value = md_link.group(1)
        if re.match(r"^(github|gitlab|bitbucket)\.(com|org)/", value, re.IGNORECASE):
            value = f"https://{value}"
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
    try:
        await service.add_marketplace(request.source, request.token)
    except RuntimeError as e:
        return ApiResponse.fail(code=-1, message=_extract_cli_message(str(e)))
    return ApiResponse.success({"source": request.source})


@router.post("/marketplaces/{name}/refresh")
async def refresh_marketplace(
    name: str,
    request: RefreshMarketplaceRequest,
    service: ServiceDep,
) -> ApiResponse[None]:
    try:
        await service.update_marketplace(name, request.token)
    except RuntimeError as e:
        return ApiResponse.fail(code=-1, message=_extract_cli_message(str(e)))
    return ApiResponse.success(None)


@router.delete("/marketplaces/{name}")
async def remove_marketplace(name: str, service: ServiceDep) -> ApiResponse[None]:
    try:
        await service.remove_marketplace(name)
    except RuntimeError as e:
        return ApiResponse.fail(code=-1, message=_extract_cli_message(str(e)))
    return ApiResponse.success(None)


@router.get("/marketplaces/{name}/plugins")
async def list_marketplace_plugins(
    name: str,
    service: ServiceDep,
) -> ApiResponse[list]:
    return ApiResponse.success(await service.list_marketplace_plugins(name))
