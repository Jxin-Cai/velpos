from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from application.settings.settings_application_service import SettingsApplicationService
from infr.client.claude_agent_gateway import ClaudeAgentGateway as ClaudeAgentGatewayImpl
from infr.config.app_config import app_config
from ohs.dependencies import get_settings_application_service, get_claude_agent_gateway
from ohs.http.api_response import ApiResponse

_SENSITIVE_ENV_KEYS = {"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"}

router = APIRouter(prefix="/api/settings", tags=["Settings"])

ServiceDep = Annotated[
    SettingsApplicationService,
    Depends(get_settings_application_service),
]

GatewayDep = Annotated[
    ClaudeAgentGatewayImpl,
    Depends(get_claude_agent_gateway),
]


class FetchModelsRequest(BaseModel):
    host: str = Field(default="", description="ANTHROPIC_BASE_URL override")
    api_key: str = Field(default="", description="ANTHROPIC_API_KEY override")


@router.get("", summary="Get settings")
async def get_settings(
    service: ServiceDep,
) -> ApiResponse[dict]:
    result = await service.get_settings()
    if app_config.mode == "pro":
        env = result.get("env", {})
        for key in _SENSITIVE_ENV_KEYS:
            if key in env:
                env[key] = "********"
    return ApiResponse.success(result)


@router.put("", summary="Update settings")
async def update_settings(
    data: Annotated[dict[str, Any], Body(...)],
    service: ServiceDep,
) -> ApiResponse[dict]:
    result = await service.update_settings(data)
    return ApiResponse.success(result)


@router.post("/fetch-models", summary="Fetch available models for a channel")
async def fetch_models(
    request: FetchModelsRequest,
    gateway: GatewayDep,
) -> ApiResponse[list]:
    models = await gateway.get_models_for_channel(
        host=request.host,
        api_key=request.api_key,
    )
    return ApiResponse.success(models)
