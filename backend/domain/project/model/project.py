from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from domain.project.model.plugin_init_status import PluginInitStatus
from domain.project.model.plugin_type import PluginType


@dataclass
class Project:
    _id: str
    _name: str
    _dir_path: str
    _agents: dict[str, dict] = field(default_factory=dict)
    _plugins: dict[str, dict] = field(default_factory=dict)
    _sort_order: int = 0
    _created_at: datetime = field(default_factory=datetime.now)
    _updated_at: datetime | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def dir_path(self) -> str:
        return self._dir_path

    @property
    def agents(self) -> dict[str, dict]:
        return dict(self._agents)

    def get_current_agent(self) -> dict | None:
        return self._agents.get("current")

    def load_agent(self, agent_id: str, language: str) -> None:
        self._agents = {"current": {"id": agent_id, "language": language}}
        self._updated_at = datetime.now()

    def unload_agent(self) -> None:
        self._agents = {}
        self._updated_at = datetime.now()

    @property
    def plugins(self) -> dict[str, dict]:
        return dict(self._plugins)

    @property
    def sort_order(self) -> int:
        return self._sort_order

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at

    # ------------------------------------------------------------------
    # Multi-plugin accessors
    # ------------------------------------------------------------------

    def has_plugin(self, plugin_type: PluginType) -> bool:
        return plugin_type.value in self._plugins

    def get_plugin_init_status(self, plugin_type: PluginType) -> PluginInitStatus:
        plugin = self._plugins.get(plugin_type.value)
        if not plugin:
            return PluginInitStatus.NONE
        return PluginInitStatus(plugin["status"])

    def get_plugin_init_session_id(self, plugin_type: PluginType) -> str:
        plugin = self._plugins.get(plugin_type.value)
        return plugin.get("session_id", "") if plugin else ""

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, name: str, dir_path: str) -> Project:
        now = datetime.now()
        return cls(
            _id=uuid.uuid4().hex[:8],
            _name=name,
            _dir_path=dir_path,
            _agents={},
            _plugins={},
            _sort_order=0,
            _created_at=now,
            _updated_at=now,
        )

    @classmethod
    def reconstitute(
        cls,
        id: str,
        name: str,
        dir_path: str,
        agents: dict[str, dict],
        plugins: dict[str, dict] | None = None,
        sort_order: int = 0,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> Project:
        return cls(
            _id=id,
            _name=name,
            _dir_path=dir_path,
            _agents=agents,
            _plugins=plugins or {},
            _sort_order=sort_order,
            _created_at=created_at or datetime.now(),
            _updated_at=updated_at,
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def rename(self, name: str) -> None:
        self._name = name
        self._updated_at = datetime.now()

    def update_sort_order(self, sort_order: int) -> None:
        self._sort_order = sort_order
        self._updated_at = datetime.now()

    # ------------------------------------------------------------------
    # Plugin mutations
    # ------------------------------------------------------------------

    def start_plugin_init(
        self, plugin_type: PluginType, init_session_id: str
    ) -> None:
        key = plugin_type.value
        existing = self._plugins.get(key, {})
        if existing.get("status") == PluginInitStatus.INITIALIZING.value:
            raise ValueError(f"Plugin {key} init is already in progress")
        self._plugins[key] = {
            "status": PluginInitStatus.INITIALIZING.value,
            "session_id": init_session_id,
        }
        self._updated_at = datetime.now()

    def complete_plugin_init(self, plugin_type: PluginType) -> None:
        key = plugin_type.value
        plugin = self._plugins.get(key)
        if not plugin or plugin["status"] != PluginInitStatus.INITIALIZING.value:
            raise ValueError(f"Plugin {key} init is not in progress")
        plugin["status"] = PluginInitStatus.READY.value
        self._updated_at = datetime.now()

    def fail_plugin_init(self, plugin_type: PluginType) -> None:
        key = plugin_type.value
        if key in self._plugins:
            self._plugins[key]["status"] = PluginInitStatus.ERROR.value
            self._updated_at = datetime.now()

    def reset_plugin(self, plugin_type: PluginType) -> None:
        key = plugin_type.value
        if self._plugins.pop(key, None) is not None:
            self._updated_at = datetime.now()

