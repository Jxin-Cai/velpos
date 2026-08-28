from __future__ import annotations

LIKE_ESCAPE_CHAR = "\\"


def escape_like(keyword: str) -> str:
    """Escape LIKE wildcards so user keywords match literally (use with ilike(..., escape=LIKE_ESCAPE_CHAR))."""
    return (
        keyword.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", LIKE_ESCAPE_CHAR + "%")
        .replace("_", LIKE_ESCAPE_CHAR + "_")
    )
