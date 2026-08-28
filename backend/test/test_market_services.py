from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.agent.agent_application_service import AgentApplicationService
from application.market.mcp_market_application_service import (
    CreateMcpServerEntryCommand,
    McpMarketApplicationService,
)
from application.market.skill_market_application_service import (
    SkillMarketApplicationService,
    UpdateSkillEntryCommand,
)
from domain.agent.model.agent_template import AgentTemplate
from domain.market.model.market_categories import McpCategory, McpTransport, SkillCategory
from domain.market.model.mcp_server_entry import McpServerEntry
from domain.market.model.skill_entry import SkillEntry
from domain.shared.business_exception import BusinessException
from infr.client.agent_asset_installer_impl import FilesystemAgentAssetInstaller
from infr.repository.mcp_server_entry_repository_impl import McpServerEntryRepositoryImpl
from infr.repository.sql_like import escape_like
from sqlalchemy.exc import IntegrityError


def _mcp_entry(entry_id: str = "mcp-1", name: str = "github") -> McpServerEntry:
    return McpServerEntry.create(
        id=entry_id,
        name=name,
        display_name="GitHub",
        description="GitHub MCP server",
        category=McpCategory.DEVELOPER_TOOLS,
        tags=("git", "vcs"),
        transport=McpTransport.STDIO,
        server_config={"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
        created_by=1,
    )


def _skill_entry(entry_id: str = "skill-1", name: str = "pdf-report") -> SkillEntry:
    return SkillEntry.create(
        id=entry_id,
        name=name,
        display_name="PDF 报告",
        description="Generate PDF reports",
        category=SkillCategory.DOCUMENT,
        tags=("pdf",),
        content="---\nname: pdf-report\ndescription: Generate PDF reports\n---\n\nSteps...",
        created_by=1,
    )


@pytest.mark.asyncio
async def test_creates_mcp_entry_when_name_is_unique() -> None:
    # Arrange
    repository = SimpleNamespace(
        find_by_name=AsyncMock(return_value=None),
        save=AsyncMock(side_effect=lambda entry: entry),
    )
    service = McpMarketApplicationService(repository)
    command = CreateMcpServerEntryCommand(
        name="github",
        display_name="GitHub",
        description="GitHub MCP server",
        category=McpCategory.DEVELOPER_TOOLS,
        transport=McpTransport.STDIO,
        server_config={"command": "npx"},
        created_by=1,
    )

    # Act
    entry = await service.create_entry(command)

    # Assert
    assert entry.name == "github"
    repository.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejects_mcp_entry_creation_when_name_duplicated() -> None:
    # Arrange
    repository = SimpleNamespace(find_by_name=AsyncMock(return_value=_mcp_entry()))
    service = McpMarketApplicationService(repository)
    command = CreateMcpServerEntryCommand(
        name="github",
        display_name="GitHub",
        description="",
        category=McpCategory.DEVELOPER_TOOLS,
        transport=McpTransport.STDIO,
        server_config={"command": "npx"},
        created_by=1,
    )

    # Act & Assert
    with pytest.raises(BusinessException):
        await service.create_entry(command)


@pytest.mark.asyncio
async def test_rejects_skill_update_when_entry_missing() -> None:
    # Arrange
    repository = SimpleNamespace(find_by_id=AsyncMock(return_value=None))
    service = SkillMarketApplicationService(repository)
    command = UpdateSkillEntryCommand(
        entry_id="missing-id",
        name="pdf-report",
        display_name="PDF 报告",
        description="",
        category=SkillCategory.DOCUMENT,
        content="content",
    )

    # Act & Assert
    with pytest.raises(BusinessException):
        await service.update_entry(command)


def test_includes_transport_type_when_config_is_remote() -> None:
    # Arrange
    entry = McpServerEntry.create(
        id="mcp-2",
        name="remote-search",
        display_name="Remote Search",
        description="",
        category=McpCategory.SEARCH,
        tags=(),
        transport=McpTransport.SSE,
        server_config={"url": "https://mcp.example.com/sse"},
        created_by=1,
    )

    # Act
    config = entry.to_client_config()

    # Assert
    assert config == {"url": "https://mcp.example.com/sse", "type": "sse"}


@pytest.mark.asyncio
async def test_installs_market_assets_when_custom_agent_is_loaded() -> None:
    # Arrange
    template = AgentTemplate.create(
        id="custom-agent-id",
        name_en="Custom",
        name_zh="自定义",
        description_en="",
        description_zh="",
        category="custom",
        emoji="🤖",
        color="#123456",
        prompt_en="prompt",
        prompt_zh="提示词",
        created_by=1,
        plugins_config={"mcp_server_ids": ["mcp-1"], "skill_ids": ["skill-1"]},
    )
    template_repository = SimpleNamespace(find_by_id=AsyncMock(return_value=template))
    mcp_repository = SimpleNamespace(find_by_ids=AsyncMock(return_value=[_mcp_entry()]))
    skill_repository = SimpleNamespace(find_by_ids=AsyncMock(return_value=[_skill_entry()]))
    installer = SimpleNamespace(
        apply_mcp_servers=AsyncMock(),
        install_skill=AsyncMock(),
    )
    service = AgentApplicationService(
        agent_template_repository=template_repository,
        mcp_entry_repository=mcp_repository,
        skill_entry_repository=skill_repository,
        asset_installer=installer,
    )

    # Act
    await service._install_agent_assets("custom-agent-id", "/tmp/project")

    # Assert
    installer.apply_mcp_servers.assert_awaited_once_with(
        "/tmp/project",
        {"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]}},
    )
    installer.install_skill.assert_awaited_once_with(
        "/tmp/project", "pdf-report", _skill_entry().content,
    )


@pytest.mark.asyncio
async def test_keeps_asset_install_running_when_skill_lookup_fails() -> None:
    # Arrange
    template = AgentTemplate.create(
        id="custom-agent-id",
        name_en="Custom",
        name_zh="自定义",
        description_en="",
        description_zh="",
        category="custom",
        emoji="🤖",
        color="#123456",
        prompt_en="prompt",
        prompt_zh="提示词",
        created_by=1,
        plugins_config={"skill_ids": ["skill-1"]},
    )
    template_repository = SimpleNamespace(find_by_id=AsyncMock(return_value=template))
    skill_repository = SimpleNamespace(find_by_ids=AsyncMock(side_effect=RuntimeError("db down")))
    installer = SimpleNamespace(install_skill=AsyncMock())
    service = AgentApplicationService(
        agent_template_repository=template_repository,
        skill_entry_repository=skill_repository,
        asset_installer=installer,
    )

    # Act
    await service._install_agent_assets("custom-agent-id", "/tmp/project")

    # Assert
    installer.install_skill.assert_not_awaited()


@pytest.mark.asyncio
async def test_raises_business_exception_when_entry_name_conflicts_on_flush() -> None:
    # Arrange
    db_session = SimpleNamespace(
        get=AsyncMock(return_value=None),
        add=lambda model: None,
        flush=AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("duplicate name"))),
    )
    repository = McpServerEntryRepositoryImpl(db_session)

    # Act & Assert
    with pytest.raises(BusinessException):
        await repository.save(_mcp_entry())


def test_escapes_like_wildcards_when_keyword_contains_special_chars() -> None:
    # Arrange
    keyword = "50%_off\\deal"

    # Act
    escaped = escape_like(keyword)

    # Assert
    assert escaped == r"50\%\_off\\deal"


@pytest.mark.asyncio
async def test_merges_mcp_config_when_project_config_exists(tmp_path) -> None:
    # Arrange
    installer = FilesystemAgentAssetInstaller()
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"existing": {"command": "old"}}}),
        encoding="utf-8",
    )

    # Act
    await installer.apply_mcp_servers(str(tmp_path), {"github": {"command": "npx"}})

    # Assert
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["mcpServers"] == {
        "existing": {"command": "old"},
        "github": {"command": "npx"},
    }


@pytest.mark.asyncio
async def test_removes_only_named_servers_when_pruning_mcp_config(tmp_path) -> None:
    # Arrange
    installer = FilesystemAgentAssetInstaller()
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"github": {"command": "npx"}, "keep": {"command": "uvx"}}}),
        encoding="utf-8",
    )

    # Act
    await installer.remove_mcp_servers(str(tmp_path), ["github"])

    # Assert
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["mcpServers"] == {"keep": {"command": "uvx"}}


@pytest.mark.asyncio
async def test_writes_skill_file_when_skill_is_installed(tmp_path) -> None:
    # Arrange
    installer = FilesystemAgentAssetInstaller()

    # Act
    await installer.install_skill(str(tmp_path), "pdf-report", "skill body")

    # Assert
    skill_file = tmp_path / ".claude" / "skills" / "pdf-report" / "SKILL.md"
    assert skill_file.read_text(encoding="utf-8") == "skill body"


@pytest.mark.asyncio
async def test_rejects_skill_install_when_name_is_unsafe(tmp_path) -> None:
    # Arrange
    installer = FilesystemAgentAssetInstaller()

    # Act & Assert
    with pytest.raises(ValueError):
        await installer.install_skill(str(tmp_path), "../evil", "skill body")
