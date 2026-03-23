from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClaudeSessionResponse(BaseModel):
    session_id: str
    summary: str | None
    last_modified: int
    file_size: int
    custom_title: str | None
    first_prompt: str | None
    git_branch: str | None
    cwd: str | None
    tag: str | None
    created_at: int | None


class ClaudeSessionListResponse(BaseModel):
    sessions: list[ClaudeSessionResponse]

    @classmethod
    def from_dicts(cls, items: list[dict[str, Any]]) -> ClaudeSessionListResponse:
        return cls(
            sessions=[ClaudeSessionResponse(**item) for item in items],
        )


class RenameSessionRequest(BaseModel):
    session_id: str = Field(min_length=1, description="Claude session UUID")
    title: str = Field(min_length=1, max_length=200, description="New session title")
    directory: str | None = Field(
        default=None,
        description="Project directory path for session lookup",
    )
