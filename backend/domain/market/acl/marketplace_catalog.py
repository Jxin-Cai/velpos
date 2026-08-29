from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from domain.market.model.market_categories import MarketplaceSort, McpTransport


@dataclass(frozen=True)
class RemoteMcpServer:
    """An MCP server listed by an open-source marketplace catalog."""

    ref: str
    name: str
    display_name: str
    description: str
    version: str
    transport: McpTransport
    server_config: dict
    repo_url: str = ""
    homepage_url: str = ""
    author: str = ""
    logo_url: str = ""
    category: str = ""
    stars: int = 0
    downloads: int = 0


@dataclass(frozen=True)
class RemoteMcpServerPage:
    items: tuple[RemoteMcpServer, ...] = field(default_factory=tuple)
    total: int = 0
    has_next: bool = False


@dataclass(frozen=True)
class RemoteSkill:
    """A skill listed by an open-source skill catalog.

    `content` holds the full SKILL.md text; catalogs may leave it empty in
    search results and only populate it on `get_skill`.
    """

    ref: str
    name: str
    display_name: str
    description: str
    content: str = ""
    repo_url: str = ""
    author: str = ""
    stars: int = 0


@dataclass(frozen=True)
class RemoteSkillPage:
    items: tuple[RemoteSkill, ...] = field(default_factory=tuple)
    total: int = 0
    has_next: bool = False


class McpMarketplaceCatalog(ABC):
    """Read-side gateway to an open-source MCP server marketplace."""

    @abstractmethod
    async def search(
        self,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 30,
        sort: MarketplaceSort = MarketplaceSort.STARS,
    ) -> RemoteMcpServerPage:
        ...

    @abstractmethod
    async def get_server(self, ref: str) -> RemoteMcpServer | None:
        ...


class SkillMarketplaceCatalog(ABC):
    """Read-side gateway to an open-source skill marketplace."""

    @abstractmethod
    async def search(
        self,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 30,
        sort: MarketplaceSort = MarketplaceSort.STARS,
    ) -> RemoteSkillPage:
        ...

    @abstractmethod
    async def get_skill(self, ref: str) -> RemoteSkill | None:
        ...
