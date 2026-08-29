from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from application.market.mcp_market_application_service import (
    CreateMcpServerEntryCommand,
    ImportMcpServerEntryCommand,
    McpMarketApplicationService,
    UpdateMcpServerEntryCommand,
)
from domain.market.model.market_categories import (
    EntrySource,
    MarketplaceSort,
    McpCategory,
    McpTransport,
)
from domain.market.model.mcp_server_entry import McpServerEntry
from domain.user.model.user import User
from ohs.auth_dependency import require_admin
from ohs.dependencies import get_mcp_market_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(
    prefix="/api/admin/market/mcp-servers",
    tags=["Admin - MCP Market"],
    dependencies=[Depends(require_admin)],
)

ServiceDep = Annotated[
    McpMarketApplicationService,
    Depends(get_mcp_market_application_service),
]

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

MCP_CATEGORY_LABELS: dict[McpCategory, dict[str, str]] = {
    McpCategory.SEARCH: {"zh": "搜索与数据提取", "en": "Search & Data Extraction"},
    McpCategory.BROWSER_AUTOMATION: {"zh": "浏览器自动化", "en": "Browser Automation"},
    McpCategory.DATABASE: {"zh": "数据库", "en": "Databases"},
    McpCategory.DEVELOPER_TOOLS: {"zh": "开发者工具", "en": "Developer Tools"},
    McpCategory.FILE_SYSTEM: {"zh": "文件系统", "en": "File Systems"},
    McpCategory.CLOUD_PLATFORM: {"zh": "云平台", "en": "Cloud Platforms"},
    McpCategory.COMMUNICATION: {"zh": "通信协作", "en": "Communication"},
    McpCategory.KNOWLEDGE_MEMORY: {"zh": "知识与记忆", "en": "Knowledge & Memory"},
    McpCategory.MONITORING: {"zh": "监控", "en": "Monitoring"},
    McpCategory.SECURITY: {"zh": "安全", "en": "Security"},
    McpCategory.FINANCE: {"zh": "金融", "en": "Finance"},
    McpCategory.MEDIA: {"zh": "多媒体", "en": "Media"},
    McpCategory.PRODUCTIVITY: {"zh": "办公效率", "en": "Productivity"},
    McpCategory.AI_SERVICE: {"zh": "AI 服务", "en": "AI Services"},
    McpCategory.OTHER: {"zh": "其他", "en": "Other"},
}


class McpServerEntryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128, pattern=_NAME_PATTERN.pattern)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="")
    category: McpCategory = McpCategory.OTHER
    tags: list[str] = Field(default_factory=list, max_length=16)
    transport: McpTransport = McpTransport.STDIO
    server_config: dict = Field(default_factory=dict)
    repo_url: str = Field(default="", max_length=512)
    homepage_url: str = Field(default="", max_length=512)
    author: str = Field(default="", max_length=128)
    version: str = Field(default="", max_length=64)
    logo_emoji: str = Field(default="🔌", max_length=16)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_server_config(self) -> "McpServerEntryRequest":
        if self.transport == McpTransport.STDIO:
            command = self.server_config.get("command")
            if not isinstance(command, str) or not command.strip():
                raise ValueError("stdio transport requires server_config.command")
        else:
            url = self.server_config.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"{self.transport.value} transport requires server_config.url")
        return self


class MarketplaceImportRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ref: str = Field(min_length=1, max_length=256)


def _to_dict(entry: McpServerEntry) -> dict:
    return {
        "id": entry.id,
        "name": entry.name,
        "display_name": entry.display_name,
        "description": entry.description,
        "category": entry.category.value,
        "tags": list(entry.tags),
        "transport": entry.transport.value,
        "server_config": entry.server_config,
        "repo_url": entry.repo_url,
        "homepage_url": entry.homepage_url,
        "author": entry.author,
        "version": entry.version,
        "logo_emoji": entry.logo_emoji,
        "source": entry.source.value,
        "source_ref": entry.source_ref,
        "created_by": entry.created_by,
        "is_active": entry.is_active,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


@router.get("/categories", summary="List MCP market categories")
async def list_categories() -> ApiResponse[list]:
    return ApiResponse.success([
        {
            "id": category.value,
            "name_zh": labels["zh"],
            "name_en": labels["en"],
        }
        for category, labels in MCP_CATEGORY_LABELS.items()
    ])


@router.get("", summary="Search MCP server entries")
async def search_entries(
    service: ServiceDep,
    keyword: Annotated[str | None, Query(max_length=128)] = None,
    category: Annotated[McpCategory | None, Query()] = None,
    only_active: Annotated[bool, Query()] = False,
    source: Annotated[EntrySource | None, Query()] = None,
) -> ApiResponse[list]:
    entries = await service.search_entries(
        keyword=keyword,
        category=category.value if category else None,
        only_active=only_active,
        source=source.value if source else None,
    )
    return ApiResponse.success([_to_dict(e) for e in entries])


@router.get("/marketplace", summary="Browse the open-source MCP marketplace")
async def browse_marketplace(
    service: ServiceDep,
    keyword: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
    sort: Annotated[MarketplaceSort, Query()] = MarketplaceSort.STARS,
) -> ApiResponse[dict]:
    view = await service.browse_marketplace(keyword=keyword, page=page, limit=limit, sort=sort)
    return ApiResponse.success({
        "items": [
            {
                "ref": server.ref,
                "name": server.name,
                "display_name": server.display_name,
                "description": server.description,
                "author": server.author,
                "category": server.category,
                "logo_url": server.logo_url,
                "repo_url": server.repo_url,
                "stars": server.stars,
                "downloads": server.downloads,
                "imported": server.ref in view.imported_refs,
            }
            for server in view.page.items
        ],
        "total": view.page.total,
        "has_next": view.page.has_next,
    })


@router.post("/marketplace/import", summary="Import an MCP server from the marketplace")
async def import_marketplace_entry(
    request: MarketplaceImportRequest,
    service: ServiceDep,
    admin: Annotated[User, Depends(require_admin)],
) -> ApiResponse[dict]:
    entry = await service.import_from_marketplace(
        ImportMcpServerEntryCommand(ref=request.ref, created_by=admin.id)
    )
    return ApiResponse.success(_to_dict(entry))


@router.post("", summary="Create MCP server entry")
async def create_entry(
    request: McpServerEntryRequest,
    service: ServiceDep,
    admin: Annotated[User, Depends(require_admin)],
) -> ApiResponse[dict]:
    command = CreateMcpServerEntryCommand(
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        category=request.category,
        tags=tuple(request.tags),
        transport=request.transport,
        server_config=request.server_config,
        created_by=admin.id,
        repo_url=request.repo_url,
        homepage_url=request.homepage_url,
        author=request.author,
        version=request.version,
        logo_emoji=request.logo_emoji,
    )
    entry = await service.create_entry(command)
    return ApiResponse.success({"id": entry.id})


@router.put("/{entry_id}", summary="Update MCP server entry")
async def update_entry(
    entry_id: str,
    request: McpServerEntryRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    command = UpdateMcpServerEntryCommand(
        entry_id=entry_id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        category=request.category,
        tags=tuple(request.tags),
        transport=request.transport,
        server_config=request.server_config,
        repo_url=request.repo_url,
        homepage_url=request.homepage_url,
        author=request.author,
        version=request.version,
        logo_emoji=request.logo_emoji,
        is_active=request.is_active,
    )
    await service.update_entry(command)
    return ApiResponse.success({"id": entry_id})


@router.delete("/{entry_id}", summary="Delete MCP server entry")
async def delete_entry(
    entry_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_entry(entry_id)
    return ApiResponse.success(None)
