from __future__ import annotations

from enum import Enum


class ClaudeMdRevisionState(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"
