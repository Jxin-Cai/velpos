from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CommandInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    type: str
    is_user_invocable: bool = Field(
        validation_alias="isUserInvocable", serialization_alias="isUserInvocable"
    )
    enabled: bool = True
    visible: bool = True
    default_args: dict[str, Any] = {}
    argument_hint: str = Field(
        default="", validation_alias="argumentHint", serialization_alias="argumentHint"
    )
    policy: dict[str, Any] | None = None


class CommandListResponse(BaseModel):
    commands: list[CommandInfo]
