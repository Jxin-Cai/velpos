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
    _user_id: int = 1
    _agents: dict[str, dict] = field(default_factory=dict)
    _plugins: dict[str, dict] = field(default_factory=dict)
    _sort_order: int = 0
    _project_type: str = "single"
    _team_config: dict = field(default_factory=dict)
    _active_claude_md_revision_id: str = ""
    _claude_md_file_hash: str = ""
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
    def user_id(self) -> int:
        return self._user_id

    @property
    def agents(self) -> dict[str, dict]:
        return dict(self._agents)

    def get_current_agent(self) -> dict | None:
        agent = self._agents.get("current")
        return dict(agent) if agent else None

    def load_agent(self, agent_id: str, language: str) -> None:
        locked_by = self._agents.get("locked_by_task")
        self._agents = {"current": {"id": agent_id, "language": language}}
        if locked_by:
            self._agents["locked_by_task"] = locked_by
        self._updated_at = datetime.now()

    def unload_agent(self) -> None:
        locked_by = self._agents.get("locked_by_task")
        self._agents = {}
        if locked_by:
            self._agents["locked_by_task"] = locked_by
        self._updated_at = datetime.now()

    def is_agent_locked(self) -> bool:
        return bool(self._agents.get("locked_by_task"))

    @property
    def plugins(self) -> dict[str, dict]:
        return dict(self._plugins)

    @property
    def project_type(self) -> str:
        return self._project_type

    @property
    def team_config(self) -> dict:
        return dict(self._team_config)

    @property
    def sort_order(self) -> int:
        return self._sort_order

    @property
    def active_claude_md_revision_id(self) -> str:
        return self._active_claude_md_revision_id

    @property
    def claude_md_file_hash(self) -> str:
        return self._claude_md_file_hash

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at

    # ------------------------------------------------------------------
    # Multi-plugin accessors
    # ------------------------------------------------------------------

    def get_plugin_init_status(self, plugin_type: PluginType) -> PluginInitStatus:
        plugin = self._plugins.get(plugin_type.value)
        if not plugin:
            return PluginInitStatus.NONE
        return PluginInitStatus(plugin["status"])

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, name: str, dir_path: str, project_type: str = "single", team_config: dict | None = None, user_id: int = 1) -> Project:
        now = datetime.now()
        return cls(
            _id=uuid.uuid4().hex[:8],
            _name=name,
            _dir_path=dir_path,
            _user_id=user_id,
            _agents={},
            _plugins={},
            _sort_order=0,
            _project_type=project_type,
            _team_config=team_config or {},
            _active_claude_md_revision_id="",
            _claude_md_file_hash="",
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
        project_type: str = "single",
        team_config: dict | None = None,
        active_claude_md_revision_id: str = "",
        claude_md_file_hash: str = "",
        user_id: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> Project:
        return cls(
            _id=id,
            _name=name,
            _dir_path=dir_path,
            _user_id=user_id,
            _agents=dict(agents) if agents else {},
            _plugins=dict(plugins) if plugins else {},
            _sort_order=sort_order,
            _project_type=project_type,
            _team_config=dict(team_config) if team_config else {},
            _active_claude_md_revision_id=active_claude_md_revision_id,
            _claude_md_file_hash=claude_md_file_hash,
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

    def update_claude_md_revision(self, revision_id: str, file_hash: str) -> None:
        self._active_claude_md_revision_id = revision_id
        self._claude_md_file_hash = file_hash
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

    def update_team_config(self, config: dict) -> None:
        self._team_config = dict(config)
        self._updated_at = datetime.now()

