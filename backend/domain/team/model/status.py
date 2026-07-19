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


class HandoffStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
