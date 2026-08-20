from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

SYSTEM_PREVIEW_LENGTH = 400


class PromptChangeKind(str, Enum):
    """How a request's prompt envelope differs from the preceding request."""

    INITIAL = "initial"
    UNCHANGED = "unchanged"
    SYSTEM = "system"
    TOOLS = "tools"
    SYSTEM_AND_TOOLS = "system_and_tools"


@dataclass(frozen=True)
class LlmToolDefinition:
    """One tool exposed to the model in a request."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None

    @property
    def description_preview(self) -> str | None:
        if not self.description:
            return None
        return _preview(self.description, SYSTEM_PREVIEW_LENGTH)


@dataclass(frozen=True)
class LlmRequestRecord:
    """One provider request decomposed into its readable parts.

    Claude Code emits the whole request body as a single telemetry log record.
    Rendering that blob answers no question a reader actually has, so the body
    is split into the three envelopes that drive model behaviour: the system
    prompt, the message history, and the tool catalog.
    """

    event_id: str
    event_time: datetime
    span_id: str | None
    model: str | None
    system: str
    tools: tuple[LlmToolDefinition, ...]
    messages: tuple[Any, ...]
    change: PromptChangeKind
    sequence: int = 0
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool | None = None

    @property
    def system_char_count(self) -> int:
        return len(self.system)

    @property
    def system_preview(self) -> str:
        return _preview(self.system, SYSTEM_PREVIEW_LENGTH)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def message_char_count(self) -> int:
        return sum(len(_stringify(message)) for message in self.messages)


def _preview(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}…"


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)
