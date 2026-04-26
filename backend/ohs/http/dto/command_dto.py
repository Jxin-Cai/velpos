from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CommandInfo(BaseModel):
    name: str
    description: str
    type: str
    isUserInvocable: bool
    enabled: bool = True
    visible: bool = True
    default_args: dict[str, Any] = {}
    policy: dict[str, Any] | None = None


class CommandListResponse(BaseModel):
    commands: list[CommandInfo]
