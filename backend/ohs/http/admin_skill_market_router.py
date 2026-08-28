from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from application.market.skill_market_application_service import (
    CreateSkillEntryCommand,
    SkillMarketApplicationService,
    UpdateSkillEntryCommand,
)
from domain.market.model.market_categories import SkillCategory
from domain.market.model.skill_entry import SkillEntry
from domain.user.model.user import User
from ohs.auth_dependency import require_admin
from ohs.dependencies import get_skill_market_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(
    prefix="/api/admin/market/skills",
    tags=["Admin - Skill Market"],
    dependencies=[Depends(require_admin)],
)

ServiceDep = Annotated[
    SkillMarketApplicationService,
    Depends(get_skill_market_application_service),
]

# Skill name doubles as the on-disk skills directory name — keep it slug-safe.
_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

SKILL_CATEGORY_LABELS: dict[SkillCategory, dict[str, str]] = {
    SkillCategory.DOCUMENT: {"zh": "文档处理", "en": "Document Processing"},
    SkillCategory.DEVELOPMENT: {"zh": "研发", "en": "Development"},
    SkillCategory.DATA_ANALYSIS: {"zh": "数据分析", "en": "Data Analysis"},
    SkillCategory.CREATIVE_DESIGN: {"zh": "创意设计", "en": "Creative Design"},
    SkillCategory.OFFICE_AUTOMATION: {"zh": "办公自动化", "en": "Office Automation"},
    SkillCategory.RESEARCH: {"zh": "调研分析", "en": "Research"},
    SkillCategory.COMMUNICATION: {"zh": "沟通协作", "en": "Communication"},
    SkillCategory.OTHER: {"zh": "其他", "en": "Other"},
}


class SkillEntryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128, pattern=_NAME_PATTERN.pattern)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="")
    category: SkillCategory = SkillCategory.OTHER
    tags: list[str] = Field(default_factory=list, max_length=16)
    content: str = Field(min_length=1)
    repo_url: str = Field(default="", max_length=512)
    author: str = Field(default="", max_length=128)
    version: str = Field(default="", max_length=64)
    logo_emoji: str = Field(default="🎯", max_length=16)
    is_active: bool = True


def _to_dict(entry: SkillEntry, include_content: bool = True) -> dict:
    payload = {
        "id": entry.id,
        "name": entry.name,
        "display_name": entry.display_name,
        "description": entry.description,
        "category": entry.category.value,
        "tags": list(entry.tags),
        "repo_url": entry.repo_url,
        "author": entry.author,
        "version": entry.version,
        "logo_emoji": entry.logo_emoji,
        "created_by": entry.created_by,
        "is_active": entry.is_active,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }
    if include_content:
        payload["content"] = entry.content
    return payload


@router.get("/categories", summary="List skill market categories")
async def list_categories() -> ApiResponse[list]:
    return ApiResponse.success([
        {
            "id": category.value,
            "name_zh": labels["zh"],
            "name_en": labels["en"],
        }
        for category, labels in SKILL_CATEGORY_LABELS.items()
    ])


@router.get("", summary="Search skill entries")
async def search_entries(
    service: ServiceDep,
    keyword: Annotated[str | None, Query(max_length=128)] = None,
    category: Annotated[SkillCategory | None, Query()] = None,
    only_active: Annotated[bool, Query()] = False,
) -> ApiResponse[list]:
    entries = await service.search_entries(
        keyword=keyword,
        category=category.value if category else None,
        only_active=only_active,
    )
    return ApiResponse.success([_to_dict(e, include_content=False) for e in entries])


@router.get("/{entry_id}", summary="Get skill entry detail")
async def get_entry(
    entry_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    entry = await service.get_entry(entry_id)
    return ApiResponse.success(_to_dict(entry))


@router.post("", summary="Create skill entry")
async def create_entry(
    request: SkillEntryRequest,
    service: ServiceDep,
    admin: Annotated[User, Depends(require_admin)],
) -> ApiResponse[dict]:
    command = CreateSkillEntryCommand(
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        category=request.category,
        tags=tuple(request.tags),
        content=request.content,
        created_by=admin.id,
        repo_url=request.repo_url,
        author=request.author,
        version=request.version,
        logo_emoji=request.logo_emoji,
    )
    entry = await service.create_entry(command)
    return ApiResponse.success({"id": entry.id})


@router.put("/{entry_id}", summary="Update skill entry")
async def update_entry(
    entry_id: str,
    request: SkillEntryRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    command = UpdateSkillEntryCommand(
        entry_id=entry_id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        category=request.category,
        tags=tuple(request.tags),
        content=request.content,
        repo_url=request.repo_url,
        author=request.author,
        version=request.version,
        logo_emoji=request.logo_emoji,
        is_active=request.is_active,
    )
    await service.update_entry(command)
    return ApiResponse.success({"id": entry_id})


@router.delete("/{entry_id}", summary="Delete skill entry")
async def delete_entry(
    entry_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_entry(entry_id)
    return ApiResponse.success(None)
