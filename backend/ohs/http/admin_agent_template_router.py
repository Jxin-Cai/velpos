from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from application.agent.agent_template_application_service import (
    AgentTemplateApplicationService,
    CreateAgentTemplateCommand,
    UpdateAgentTemplateCommand,
)
from domain.user.model.user import User
from ohs.auth_dependency import require_admin
from ohs.dependencies import get_agent_template_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(
    prefix="/api/admin/agent-templates",
    tags=["Admin - Agent Templates"],
    dependencies=[Depends(require_admin)],
)

ServiceDep = Annotated[
    AgentTemplateApplicationService,
    Depends(get_agent_template_application_service),
]


class MarketplaceConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=512)


class LocalPluginConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)


class PluginsConfig(BaseModel):
    marketplaces: list[MarketplaceConfig] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    local_plugins: list[LocalPluginConfig] = Field(default_factory=list)


class AgentTemplateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name_en: str = Field(min_length=1, max_length=128)
    name_zh: str = Field(min_length=1, max_length=128)
    description_en: str = Field(default="")
    description_zh: str = Field(default="")
    category: str = Field(default="custom", min_length=1, max_length=64)
    emoji: str = Field(default="🤖", max_length=16)
    color: str = Field(default="#6366f1", max_length=32)
    prompt_en: str = Field(min_length=1)
    prompt_zh: str = Field(min_length=1)
    plugins_config: PluginsConfig | None = None


@router.get("", summary="List all agent templates (admin)")
async def list_templates(
    service: ServiceDep,
) -> ApiResponse[list]:
    templates = await service.list_all_templates()
    return ApiResponse.success([
        {
            "id": t.id,
            "name_en": t.name_en,
            "name_zh": t.name_zh,
            "description_en": t.description_en,
            "description_zh": t.description_zh,
            "category": t.category,
            "emoji": t.emoji,
            "color": t.color,
            "prompt_en": t.prompt_en,
            "prompt_zh": t.prompt_zh,
            "plugins_config": t.plugins_config,
            "created_by": t.created_by,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in templates
    ])


@router.post("", summary="Create agent template")
async def create_template(
    request: AgentTemplateRequest,
    service: ServiceDep,
    admin: Annotated[User, Depends(require_admin)],
) -> ApiResponse[dict]:
    command = CreateAgentTemplateCommand(
        name_en=request.name_en,
        name_zh=request.name_zh,
        description_en=request.description_en,
        description_zh=request.description_zh,
        category=request.category,
        emoji=request.emoji,
        color=request.color,
        prompt_en=request.prompt_en,
        prompt_zh=request.prompt_zh,
        created_by=admin.id,
        plugins_config=(
            request.plugins_config.model_dump()
            if request.plugins_config is not None
            else None
        ),
    )
    template = await service.create_template(command)
    return ApiResponse.success({"id": template.id})


@router.put("/{template_id}", summary="Update agent template")
async def update_template(
    template_id: str,
    request: AgentTemplateRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    command = UpdateAgentTemplateCommand(
        template_id=template_id,
        name_en=request.name_en,
        name_zh=request.name_zh,
        description_en=request.description_en,
        description_zh=request.description_zh,
        category=request.category,
        emoji=request.emoji,
        color=request.color,
        prompt_en=request.prompt_en,
        prompt_zh=request.prompt_zh,
        plugins_config=(
            request.plugins_config.model_dump()
            if request.plugins_config is not None
            else None
        ),
    )
    await service.update_template(command)
    return ApiResponse.success({"id": template_id})


@router.delete("/{template_id}", summary="Delete agent template")
async def delete_template(
    template_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_template(template_id)
    return ApiResponse.success(None)
