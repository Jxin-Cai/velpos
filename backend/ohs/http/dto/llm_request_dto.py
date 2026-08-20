from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LlmToolDefinitionDto(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None


class LlmRequestSummaryDto(BaseModel):
    """Everything the request list needs, without the request text itself."""

    event_id: str
    sequence: int
    event_time: datetime
    span_id: str | None = None
    model: str | None = None
    change: str
    system_char_count: int = 0
    system_preview: str = ""
    tool_count: int = 0
    tool_names: list[str] = Field(default_factory=list)
    message_count: int = 0
    message_char_count: int = 0


class LlmRequestDetailDto(LlmRequestSummaryDto):
    """The full request envelope split into its three readable parts."""

    system: str = ""
    tools: list[LlmToolDefinitionDto] = Field(default_factory=list)
    messages: list[Any] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool | None = None


class LlmRequestListResponse(BaseModel):
    requests: list[LlmRequestSummaryDto] = Field(default_factory=list)
    has_more: bool = False
