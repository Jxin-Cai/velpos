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


class SlotRole(str, Enum):
    WORKER = "worker"
    LEADER = "leader"


class HandoffStatus(str, Enum):
    ACCEPTED = "accepted"


class StageOutputStatus(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


class FlowMode(str, Enum):
    WORKFLOW = "workflow"
    DECISION = "decision"


class FlowPlanStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FlowStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in {
            FlowStepStatus.COMPLETED,
            FlowStepStatus.FAILED,
            FlowStepStatus.SKIPPED,
        }


class ExecutionFailureCategory(str, Enum):
    VALIDATION = "validation"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    WORKSPACE_UNAVAILABLE = "workspace_unavailable"
    SESSION_LOST = "session_lost"
    NETWORK_ERROR = "network_error"
    ORCHESTRATION = "orchestration"
    PERSISTENCE = "persistence"
    CANCELLED_BY_USER = "cancelled_by_user"
    CANCELLED_BY_LEADER = "cancelled_by_leader"
    RECONCILIATION = "reconciliation"
    UNKNOWN = "unknown"


class ExecutionFailurePhase(str, Enum):
    PREPARATION = "preparation"
    DISPATCH = "dispatch"
    EXECUTION = "execution"
    HANDOFF = "handoff"
    ORCHESTRATION = "orchestration"
    RECONCILIATION = "reconciliation"


class ExecutionTrigger(str, Enum):
    USER = "user"
    LEADER = "leader"
    WORKFLOW = "workflow"
    DECISION = "decision"
    RETRY = "retry"
    RECOVERY = "recovery"
