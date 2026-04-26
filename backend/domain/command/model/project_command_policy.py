from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProjectCommandPolicy:
    id: str
    project_id: str
    command_name: str
    command_type: str
    enabled: bool = True
    visible: bool = True
    default_args: dict[str, Any] = field(default_factory=dict)
    updated_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        project_id: str,
        command_name: str,
        command_type: str,
        enabled: bool = True,
        visible: bool = True,
        default_args: dict[str, Any] | None = None,
    ) -> ProjectCommandPolicy:
        return cls(
            id=uuid.uuid4().hex[:8],
            project_id=project_id,
            command_name=command_name,
            command_type=command_type or "unknown",
            enabled=enabled,
            visible=visible,
            default_args=dict(default_args or {}),
            updated_time=datetime.now(),
        )

    def update(
        self,
        enabled: bool | None = None,
        visible: bool | None = None,
        default_args: dict[str, Any] | None = None,
        command_type: str | None = None,
    ) -> None:
        if enabled is not None:
            self.enabled = enabled
        if visible is not None:
            self.visible = visible
        if default_args is not None:
            self.default_args = dict(default_args)
        if command_type is not None:
            self.command_type = command_type or "unknown"
        self.updated_time = datetime.now()
