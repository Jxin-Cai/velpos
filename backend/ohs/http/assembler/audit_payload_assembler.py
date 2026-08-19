from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Claude Code can be configured to emit whole API request and response bodies as
# log records. Sending a page of those verbatim makes the telemetry response tens
# of megabytes, so the list view gets clipped copies and the reader fetches the
# verbatim payload for the one event they open.
MAX_STRING_LENGTH = 2000
MAX_SEQUENCE_ITEMS = 200
MAX_DEPTH = 8


@dataclass
class _TrimState:
    truncated: bool = False


@dataclass(frozen=True)
class TrimmedPayload:
    payload: Any
    truncated: bool


def trim_audit_payload(
    payload: Any,
    max_string_length: int = MAX_STRING_LENGTH,
) -> TrimmedPayload:
    """Return a copy of an audit payload with oversized content clipped."""
    state = _TrimState()
    trimmed = _trim(payload, max_string_length, depth=0, state=state)
    return TrimmedPayload(payload=trimmed, truncated=state.truncated)


def _trim(value: Any, max_string_length: int, depth: int, state: _TrimState) -> Any:
    if depth >= MAX_DEPTH:
        if isinstance(value, (dict, list, tuple)) and value:
            state.truncated = True
            return None
        return value

    if isinstance(value, str):
        return _trim_string(value, max_string_length, state)
    if isinstance(value, dict):
        return {
            key: _trim(item, max_string_length, depth + 1, state)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        kept = list(value[:MAX_SEQUENCE_ITEMS])
        if len(value) > len(kept):
            state.truncated = True
        return [_trim(item, max_string_length, depth + 1, state) for item in kept]
    return value


def _trim_string(value: str, max_string_length: int, state: _TrimState) -> str:
    if len(value) <= max_string_length:
        return value
    state.truncated = True
    return f"{value[:max_string_length]}…[truncated, {len(value)} chars total]"
