from __future__ import annotations

from dataclasses import dataclass

from domain.team.model.status import ExecutionFailureCategory, ExecutionFailurePhase


@dataclass(frozen=True)
class ClassifiedExecutionFailure:
    category: ExecutionFailureCategory
    phase: ExecutionFailurePhase
    retryable: bool


def classify_execution_failure(reason: str) -> ClassifiedExecutionFailure:
    """Classify terminal agent errors without depending on transport-specific types."""
    normalized = reason.casefold()
    if any(
        token in normalized
        for token in (
            "exit code 129",
            "backend process restarted",
            "process interrupted",
            "connection closed for session",
        )
    ):
        return ClassifiedExecutionFailure(
            ExecutionFailureCategory.RECONCILIATION,
            ExecutionFailurePhase.RECONCILIATION,
            True,
        )
    if any(token in normalized for token in ("timed out", "timeout", "deadline exceeded")):
        return ClassifiedExecutionFailure(
            ExecutionFailureCategory.TIMEOUT,
            ExecutionFailurePhase.EXECUTION,
            True,
        )
    if any(token in normalized for token in ("connection", "network", "econn", "unreachable")):
        return ClassifiedExecutionFailure(
            ExecutionFailureCategory.NETWORK_ERROR,
            ExecutionFailurePhase.DISPATCH,
            True,
        )
    if any(token in normalized for token in ("session not found", "session lost")):
        return ClassifiedExecutionFailure(
            ExecutionFailureCategory.SESSION_LOST,
            ExecutionFailurePhase.RECONCILIATION,
            True,
        )
    if any(token in normalized for token in ("workspace", "worktree", "permission denied")):
        return ClassifiedExecutionFailure(
            ExecutionFailureCategory.WORKSPACE_UNAVAILABLE,
            ExecutionFailurePhase.PREPARATION,
            True,
        )
    if any(token in normalized for token in ("invalid", "validation", "bad request")):
        return ClassifiedExecutionFailure(
            ExecutionFailureCategory.VALIDATION,
            ExecutionFailurePhase.EXECUTION,
            False,
        )
    return ClassifiedExecutionFailure(
        ExecutionFailureCategory.AGENT_ERROR,
        ExecutionFailurePhase.EXECUTION,
        False,
    )
