import enum


class SessionStatus(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    COMPACTING = "compacting"
