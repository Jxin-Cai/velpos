from __future__ import annotations

import enum


class ChannelInitStatus(str, enum.Enum):
    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
