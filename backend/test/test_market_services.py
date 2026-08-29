from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.agent.agent_application_service import AgentApplicationService
from application.market.mcp_market_application_service import (
    CreateMcpServerEntryCommand,
    ImportMcpServerEntryCommand,
    McpMarketApplicationService,
    slugify_entry_name,
)
from application.market.skill_market_application_service import (
    ImportSkillEntryCommand,
    SkillMarketApplicationService,
    UpdateSkillEntryCommand,
)
from domain.agent.model.agent_template import AgentTemplate
from domain.market.acl.marketplace_catalog import (
    RemoteMcpServer,
    RemoteMcpServerPage,
    RemoteSkill,
)
from domain.market.model.market_categories import (
    EntrySource,
    MarketplaceSort,
    McpCategory,
    McpTransport,
    SkillCategory,
)
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


def _remote_mcp_server(ref: str = "github.com/foo/bar-mcp") -> RemoteMcpServer:
    return RemoteMcpServer(
        ref=ref,
        name="bar-mcp",
        display_name="Bar MCP",
        description="Does bar things",
        version="1.0.0",
        transport=McpTransport.STDIO,
        server_config={"command": "npx", "args": ["-y", "bar-mcp"]},
        repo_url="https://github.com/foo/bar-mcp",
        author="foo",
        category="developer-tools",
        stars=120,
        downloads=4000,
    )


def _remote_skill(ref: str = "https://github.com/foo/skills/tree/main/skills/report") -> RemoteSkill:
    return RemoteSkill(
        ref=ref,
        name="report",
        display_name="report",
        description="Build reports",
        content="---\nname: report\n---\n\nSteps...",
        repo_url=ref,
        author="foo",
        stars=99,
    )


@pytest.mark.asyncio
async def test_imports_marketplace_mcp_entry_when_ref_is_new() -> None:
    # Arrange
    repository = SimpleNamespace(
        find_by_source_ref=AsyncMock(return_value=None),
        find_by_name=AsyncMock(return_value=None),
        save=AsyncMock(side_effect=lambda entry: entry),
    )
    catalog = SimpleNamespace(get_server=AsyncMock(return_value=_remote_mcp_server()))
    service = McpMarketApplicationService(repository, marketplace_catalog=catalog)

    # Act
    entry = await service.import_from_marketplace(
        ImportMcpServerEntryCommand(ref="github.com/foo/bar-mcp", created_by=1)
    )

    # Assert
    assert entry.source is EntrySource.MARKETPLACE
    assert entry.source_ref == "github.com/foo/bar-mcp"
    assert entry.category is McpCategory.DEVELOPER_TOOLS
    assert entry.name == "bar-mcp"


@pytest.mark.asyncio
async def test_rejects_marketplace_import_when_ref_already_imported() -> None:
    # Arrange
    repository = SimpleNamespace(find_by_source_ref=AsyncMock(return_value=_mcp_entry()))
    catalog = SimpleNamespace(get_server=AsyncMock())
    service = McpMarketApplicationService(repository, marketplace_catalog=catalog)

    # Act & Assert
    with pytest.raises(BusinessException):
        await service.import_from_marketplace(
            ImportMcpServerEntryCommand(ref="github.com/foo/bar-mcp", created_by=1)
        )


@pytest.mark.asyncio
async def test_allocates_suffixed_name_when_marketplace_name_conflicts() -> None:
    # Arrange
    repository = SimpleNamespace(
        find_by_source_ref=AsyncMock(return_value=None),
        find_by_name=AsyncMock(side_effect=[_mcp_entry(), None]),
        save=AsyncMock(side_effect=lambda entry: entry),
    )
    catalog = SimpleNamespace(get_server=AsyncMock(return_value=_remote_mcp_server()))
    service = McpMarketApplicationService(repository, marketplace_catalog=catalog)

    # Act
    entry = await service.import_from_marketplace(
        ImportMcpServerEntryCommand(ref="github.com/foo/bar-mcp", created_by=1)
    )

    # Assert
    assert entry.name == "bar-mcp-2"


@pytest.mark.asyncio
async def test_marks_imported_refs_when_browsing_marketplace() -> None:
    # Arrange
    imported = McpServerEntry.create(
        id="mcp-9",
        name="bar-mcp",
        display_name="Bar MCP",
        description="",
        category=McpCategory.OTHER,
        tags=(),
        transport=McpTransport.STDIO,
        server_config={"command": "npx"},
        created_by=1,
        source=EntrySource.MARKETPLACE,
        source_ref="github.com/foo/bar-mcp",
    )
    repository = SimpleNamespace(search=AsyncMock(return_value=[imported]))
    catalog = SimpleNamespace(
        search=AsyncMock(
            return_value=RemoteMcpServerPage(items=(_remote_mcp_server(),), total=1, has_next=False)
        )
    )
    service = McpMarketApplicationService(repository, marketplace_catalog=catalog)

    # Act
    view = await service.browse_marketplace(keyword="bar", sort=MarketplaceSort.DOWNLOADS)

    # Assert
    assert view.imported_refs == frozenset({"github.com/foo/bar-mcp"})


@pytest.mark.asyncio
async def test_imports_marketplace_skill_when_ref_is_new() -> None:
    # Arrange
    repository = SimpleNamespace(
        find_by_source_ref=AsyncMock(return_value=None),
        find_by_name=AsyncMock(return_value=None),
        save=AsyncMock(side_effect=lambda entry: entry),
    )
    catalog = SimpleNamespace(get_skill=AsyncMock(return_value=_remote_skill()))
    service = SkillMarketApplicationService(repository, marketplace_catalog=catalog)

    # Act
    entry = await service.import_from_marketplace(
        ImportSkillEntryCommand(ref=_remote_skill().ref, created_by=1)
    )

    # Assert
    assert entry.source is EntrySource.MARKETPLACE
    assert entry.content == _remote_skill().content
    assert entry.name == "report"


@pytest.mark.asyncio
async def test_rejects_marketplace_browse_when_catalog_not_configured() -> None:
    # Arrange
    service = SkillMarketApplicationService(SimpleNamespace())

    # Act & Assert
    with pytest.raises(BusinessException):
        await service.browse_marketplace()


def test_slugifies_upstream_ref_when_name_has_illegal_chars() -> None:
    # Arrange
    raw = "io.github.Some_Owner/My Repo!"

    # Act
    slug = slugify_entry_name(raw)

    # Assert
    assert slug == "my-repo"


@pytest.mark.asyncio
async def test_sorts_catalog_by_downloads_when_requested() -> None:
    # Arrange
    import time as time_module

    from infr.client.cline_mcp_catalog_impl import ClineMcpMarketplaceCatalog

    catalog = ClineMcpMarketplaceCatalog()
    low = _remote_mcp_server("github.com/foo/low")
    high = RemoteMcpServer(
        ref="github.com/foo/high",
        name="high",
        display_name="High",
        description="",
        version="",
        transport=McpTransport.STDIO,
        server_config={},
        stars=1,
        downloads=99999,
    )
    catalog._cache = (time_module.monotonic() + 60, (low, high))

    # Act
    page = await catalog.search(sort=MarketplaceSort.DOWNLOADS, limit=1)

    # Assert
    assert page.items[0].ref == "github.com/foo/high"
    assert page.total == 2
    assert page.has_next is True


def test_extracts_frontmatter_fields_when_metadata_is_nested() -> None:
    # Arrange
    from infr.client.skillsmp_catalog_impl import SkillsmpCatalog

    content = '---\nname: nano-pdf\ndescription: "Edit PDFs."\nmetadata:\n  emoji: x\n---\n\nBody'

    # Act
    fields = SkillsmpCatalog._parse_frontmatter(content)

    # Assert
    assert fields["name"] == "nano-pdf"
    assert fields["description"] == "Edit PDFs."
    assert "emoji" not in fields


def test_derives_raw_content_url_when_ref_is_tree_url() -> None:
    # Arrange
    from infr.client.skillsmp_catalog_impl import SkillsmpCatalog

    ref = "https://github.com/openclaw/openclaw/tree/main/skills/nano-pdf"

    # Act
    raw_url = SkillsmpCatalog._to_raw_content_url(ref)

    # Assert
    assert raw_url == "https://raw.githubusercontent.com/openclaw/openclaw/main/skills/nano-pdf/SKILL.md"
