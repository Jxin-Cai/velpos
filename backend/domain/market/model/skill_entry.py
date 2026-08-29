from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.market.model.market_categories import EntrySource, SkillCategory


@dataclass
class SkillEntry:
    """A skill listed in the admin skill market. `content` holds the full SKILL.md text."""

    _id: str
    _name: str
    _display_name: str
    _description: str
    _category: SkillCategory
    _tags: tuple[str, ...]
    _content: str
    _repo_url: str
    _author: str
    _version: str
    _logo_emoji: str
    _created_by: int
    _source: EntrySource = EntrySource.CUSTOM
    _source_ref: str = ""
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
    def category(self) -> SkillCategory:
        return self._category

    @property
    def tags(self) -> tuple[str, ...]:
        return self._tags

    @property
    def content(self) -> str:
        return self._content

    @property
    def repo_url(self) -> str:
        return self._repo_url

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
    def source(self) -> EntrySource:
        return self._source

    @property
    def source_ref(self) -> str:
        return self._source_ref

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
        category: SkillCategory,
        tags: tuple[str, ...],
        content: str,
        created_by: int,
        repo_url: str = "",
        author: str = "",
        version: str = "",
        logo_emoji: str = "🎯",
        source: EntrySource = EntrySource.CUSTOM,
        source_ref: str = "",
    ) -> SkillEntry:
        now = datetime.now()
        return cls(
            _id=id,
            _name=name,
            _display_name=display_name,
            _description=description,
            _category=category,
            _tags=tags,
            _content=content,
            _repo_url=repo_url,
            _author=author,
            _version=version,
            _logo_emoji=logo_emoji,
            _created_by=created_by,
            _source=source,
            _source_ref=source_ref,
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
        category: SkillCategory,
        tags: tuple[str, ...],
        content: str,
        repo_url: str,
        author: str,
        version: str,
        logo_emoji: str,
        created_by: int,
        created_at: datetime,
        updated_at: datetime,
        is_active: bool,
        source: EntrySource = EntrySource.CUSTOM,
        source_ref: str = "",
    ) -> SkillEntry:
        return cls(
            _id=id,
            _name=name,
            _display_name=display_name,
            _description=description,
            _category=category,
            _tags=tags,
            _content=content,
            _repo_url=repo_url,
            _author=author,
            _version=version,
            _logo_emoji=logo_emoji,
            _created_by=created_by,
            _source=source,
            _source_ref=source_ref,
            _created_at=created_at,
            _updated_at=updated_at,
            _is_active=is_active,
        )

    def update(
        self,
        name: str,
        display_name: str,
        description: str,
        category: SkillCategory,
        tags: tuple[str, ...],
        content: str,
        repo_url: str,
        author: str,
        version: str,
        logo_emoji: str,
    ) -> None:
        self._name = name
        self._display_name = display_name
        self._description = description
        self._category = category
        self._tags = tags
        self._content = content
        self._repo_url = repo_url
        self._author = author
        self._version = version
        self._logo_emoji = logo_emoji
        self._updated_at = datetime.now()

    def activate(self) -> None:
        self._is_active = True
        self._updated_at = datetime.now()

    def deactivate(self) -> None:
        self._is_active = False
        self._updated_at = datetime.now()
