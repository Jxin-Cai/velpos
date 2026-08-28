from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.market.model.market_categories import McpCategory, McpTransport


@dataclass
class McpServerEntry:
    """An MCP server listed in the admin MCP market."""

    _id: str
    _name: str
    _display_name: str
    _description: str
    _category: McpCategory
    _tags: tuple[str, ...]
    _transport: McpTransport
    _server_config: dict
    _repo_url: str
    _homepage_url: str
    _author: str
    _version: str
    _logo_emoji: str
    _created_by: int
    _created_at: datetime = field(default_factory=datetime.now)
    _updated_at: datetime = field(default_factory=datetime.now)
    _is_active: bool = True

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def category(self) -> McpCategory:
        return self._category

    @property
    def tags(self) -> tuple[str, ...]:
        return self._tags

    @property
    def transport(self) -> McpTransport:
        return self._transport

    @property
    def server_config(self) -> dict:
        return self._server_config

    @property
    def repo_url(self) -> str:
        return self._repo_url

    @property
    def homepage_url(self) -> str:
        return self._homepage_url

    @property
    def author(self) -> str:
        return self._author

    @property
    def version(self) -> str:
        return self._version

    @property
    def logo_emoji(self) -> str:
        return self._logo_emoji

    @property
    def created_by(self) -> int:
        return self._created_by

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def is_active(self) -> bool:
        return self._is_active

    @classmethod
    def create(
        cls,
        id: str,
        name: str,
        display_name: str,
        description: str,
        category: McpCategory,
        tags: tuple[str, ...],
        transport: McpTransport,
        server_config: dict,
        created_by: int,
        repo_url: str = "",
        homepage_url: str = "",
        author: str = "",
        version: str = "",
        logo_emoji: str = "🔌",
    ) -> McpServerEntry:
        now = datetime.now()
        return cls(
            _id=id,
            _name=name,
            _display_name=display_name,
            _description=description,
            _category=category,
            _tags=tags,
            _transport=transport,
            _server_config=server_config,
            _repo_url=repo_url,
            _homepage_url=homepage_url,
            _author=author,
            _version=version,
            _logo_emoji=logo_emoji,
            _created_by=created_by,
            _created_at=now,
            _updated_at=now,
        )

    @classmethod
    def reconstitute(
        cls,
        id: str,
        name: str,
        display_name: str,
        description: str,
        category: McpCategory,
        tags: tuple[str, ...],
        transport: McpTransport,
        server_config: dict,
        repo_url: str,
        homepage_url: str,
        author: str,
        version: str,
        logo_emoji: str,
        created_by: int,
        created_at: datetime,
        updated_at: datetime,
        is_active: bool,
    ) -> McpServerEntry:
        return cls(
            _id=id,
            _name=name,
            _display_name=display_name,
            _description=description,
            _category=category,
            _tags=tags,
            _transport=transport,
            _server_config=server_config,
            _repo_url=repo_url,
            _homepage_url=homepage_url,
            _author=author,
            _version=version,
            _logo_emoji=logo_emoji,
            _created_by=created_by,
            _created_at=created_at,
            _updated_at=updated_at,
            _is_active=is_active,
        )

    def update(
        self,
        name: str,
        display_name: str,
        description: str,
        category: McpCategory,
        tags: tuple[str, ...],
        transport: McpTransport,
        server_config: dict,
        repo_url: str,
        homepage_url: str,
        author: str,
        version: str,
        logo_emoji: str,
    ) -> None:
        self._name = name
        self._display_name = display_name
        self._description = description
        self._category = category
        self._tags = tags
        self._transport = transport
        self._server_config = server_config
        self._repo_url = repo_url
        self._homepage_url = homepage_url
        self._author = author
        self._version = version
        self._logo_emoji = logo_emoji
        self._updated_at = datetime.now()

    def to_client_config(self) -> dict:
        """Build the server object written into a client MCP config (.mcp.json)."""
        config = dict(self._server_config)
        if self._transport is not McpTransport.STDIO:
            config.setdefault("type", self._transport.value)
        return config

    def activate(self) -> None:
        self._is_active = True
        self._updated_at = datetime.now()

    def deactivate(self) -> None:
        self._is_active = False
        self._updated_at = datetime.now()
