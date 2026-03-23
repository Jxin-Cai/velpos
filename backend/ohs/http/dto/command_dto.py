from __future__ import annotations

from pydantic import BaseModel


class CommandInfo(BaseModel):
    name: str
    description: str
    type: str
    isUserInvocable: bool


class CommandListResponse(BaseModel):
    commands: list[CommandInfo]
