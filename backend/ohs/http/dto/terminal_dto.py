from __future__ import annotations

from pydantic import BaseModel, Field


class ExecuteTerminalRequest(BaseModel):
    command: str = Field(
        ...,
        min_length=1,
        description="Shell command to execute",
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Timeout in seconds (1-300)",
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory for the command",
    )


class OpenPathRequest(BaseModel):
    path: str = Field(
        ...,
        min_length=1,
        description="File or directory path to open",
    )
