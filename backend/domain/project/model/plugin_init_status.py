from __future__ import annotations

import enum


class PluginInitStatus(enum.Enum):
    NONE = "none"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
