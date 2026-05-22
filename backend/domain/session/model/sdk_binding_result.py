from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SdkBindingResult:
    accepted: bool
    resolved_id: str
    conflict_session_id: str = ""
