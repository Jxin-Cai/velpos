from enum import Enum


class WishCardStatus(str, Enum):
    BACKLOG = "backlog"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class CardExecutionStatus(str, Enum):
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            CardExecutionStatus.COMPLETED,
            CardExecutionStatus.FAILED,
            CardExecutionStatus.CANCELLED,
        }


class SlotAvailability(str, Enum):
    AVAILABLE = "available"
    UNSTABLE = "unstable"


class HandoffStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
