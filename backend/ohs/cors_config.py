"""CORS origin configuration helpers.

Kept as a standalone module so tests can import the pure helpers without
pulling in the full application initialisation chain (database engine, etc.).
"""
from __future__ import annotations

#: Safe localhost-only default for zero-config dev deployments.
#: Covers the Vite dev server (port 3231) and the backend itself (port 8083)
#: served over both ``localhost`` and ``127.0.0.1``.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3231,http://127.0.0.1:3231,"
    "http://localhost:8083,http://127.0.0.1:8083"
)


def parse_cors_origins(raw: str) -> list[str]:
    """Split a comma-separated CORS origins string into a deduplicated list.

    Empty segments (e.g. from trailing commas) are silently dropped.
    """
    return [o.strip() for o in raw.split(",") if o.strip()]
