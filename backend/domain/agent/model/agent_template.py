from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentTemplate:
    _id: str
    _name_en: str
    _name_zh: str
    _description_en: str
    _description_zh: str
    _category: str
    _emoji: str
    _color: str
    _prompt_en: str
    _prompt_zh: str
    _plugins_config: dict | None
    _created_by: int
    _created_at: datetime = field(default_factory=datetime.now)
    _updated_at: datetime = field(default_factory=datetime.now)
    _is_active: bool = True

    @property
    def id(self) -> str:
        return self._id

    @property
    def name_en(self) -> str:
        return self._name_en

    @property
    def name_zh(self) -> str:
        return self._name_zh

    @property
    def description_en(self) -> str:
        return self._description_en

    @property
    def description_zh(self) -> str:
        return self._description_zh

    @property
    def category(self) -> str:
        return self._category

    @property
    def emoji(self) -> str:
        return self._emoji

    @property
    def color(self) -> str:
        return self._color

    @property
    def prompt_en(self) -> str:
        return self._prompt_en

    @property
    def prompt_zh(self) -> str:
        return self._prompt_zh

    @property
    def plugins_config(self) -> dict | None:
        return self._plugins_config

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
        name_en: str,
        name_zh: str,
        description_en: str,
        description_zh: str,
        category: str,
        emoji: str,
        color: str,
        prompt_en: str,
        prompt_zh: str,
        created_by: int,
        plugins_config: dict | None = None,
    ) -> AgentTemplate:
        now = datetime.now()
        return cls(
            _id=id,
            _name_en=name_en,
            _name_zh=name_zh,
            _description_en=description_en,
            _description_zh=description_zh,
            _category=category,
            _emoji=emoji,
            _color=color,
            _prompt_en=prompt_en,
            _prompt_zh=prompt_zh,
            _plugins_config=plugins_config,
            _created_by=created_by,
            _created_at=now,
            _updated_at=now,
        )

    @classmethod
    def reconstitute(
        cls,
        id: str,
        name_en: str,
        name_zh: str,
        description_en: str,
        description_zh: str,
        category: str,
        emoji: str,
        color: str,
        prompt_en: str,
        prompt_zh: str,
        plugins_config: dict | None,
        created_by: int,
        created_at: datetime,
        updated_at: datetime,
        is_active: bool,
    ) -> AgentTemplate:
        return cls(
            _id=id,
            _name_en=name_en,
            _name_zh=name_zh,
            _description_en=description_en,
            _description_zh=description_zh,
            _category=category,
            _emoji=emoji,
            _color=color,
            _prompt_en=prompt_en,
            _prompt_zh=prompt_zh,
            _plugins_config=plugins_config,
            _created_by=created_by,
            _created_at=created_at,
            _updated_at=updated_at,
            _is_active=is_active,
        )

    def update(
        self,
        name_en: str,
        name_zh: str,
        description_en: str,
        description_zh: str,
        category: str,
        emoji: str,
        color: str,
        prompt_en: str,
        prompt_zh: str,
        plugins_config: dict | None = None,
    ) -> None:
        self._name_en = name_en
        self._name_zh = name_zh
        self._description_en = description_en
        self._description_zh = description_zh
        self._category = category
        self._emoji = emoji
        self._color = color
        self._prompt_en = prompt_en
        self._prompt_zh = prompt_zh
        self._plugins_config = plugins_config
        self._updated_at = datetime.now()

    def deactivate(self) -> None:
        self._is_active = False
        self._updated_at = datetime.now()

    def activate(self) -> None:
        self._is_active = True
        self._updated_at = datetime.now()
