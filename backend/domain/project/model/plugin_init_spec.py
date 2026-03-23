from __future__ import annotations

from dataclasses import dataclass, field

from domain.project.model.plugin_type import PluginType


@dataclass(frozen=True)
class PluginInitSpec:
    plugin_type: PluginType
    prereq_commands: list[str] = field(default_factory=list)
    prereq_install: str | None = None
    init_md_path: str = ""
    claude_md_template: str = ""
