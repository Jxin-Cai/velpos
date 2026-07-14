from __future__ import annotations

import json
import os
import re
from typing import Any

_MAX_PAYLOAD_SIZE = int(os.getenv("VELPOS_TRACE_PAYLOAD_MAX_SIZE", "4096"))

_REDACT_PATTERNS = [
    re.compile(r"(api[_\-]?key|secret|password|passwd|token|auth)[\"']?\s*[:=]\s*[\"']?\S+", re.IGNORECASE),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----"),
    re.compile(r"ghp_[a-zA-Z0-9]{36,}"),
    re.compile(r"gho_[a-zA-Z0-9]{36,}"),
    re.compile(r"xoxb-[a-zA-Z0-9\-]+"),
    re.compile(r"xoxp-[a-zA-Z0-9\-]+"),
]

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"api[_\-]?key|secret|password|passwd|token|auth|credential|private[_\-]?key",
    re.IGNORECASE,
)


def _redact_string(text: str) -> str:
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def _redact_value(data: Any, depth: int = 0) -> Any:
    if depth > 10:
        return "..."
    if isinstance(data, str):
        return _redact_string(data)
    if isinstance(data, dict):
        return {
            k: _REDACTED if _SENSITIVE_KEY.search(str(k)) else _redact_value(v, depth + 1)
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [_redact_value(item, depth + 1) for item in data[:50]]
    return data


def sanitize_and_truncate(data: Any, max_chars: int | None = None) -> str | None:
    if data is None:
        return None

    max_chars = max_chars or _MAX_PAYLOAD_SIZE

    if isinstance(data, str):
        redacted = _redact_string(data)
        if len(redacted) > max_chars:
            return redacted[:max_chars] + f"\n... [truncated, total {len(redacted)} chars]"
        return redacted

    redacted = _redact_value(data)
    try:
        serialized = json.dumps(redacted, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        serialized = str(redacted)

    if len(serialized) > max_chars:
        return serialized[:max_chars] + f"\n... [truncated, total {len(serialized)} chars]"
    return serialized
