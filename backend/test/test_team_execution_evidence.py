from application.team_board.failure_taxonomy import classify_execution_failure
from domain.team.model.status import (
    ExecutionFailureCategory,
    ExecutionFailurePhase,
    ExecutionTrigger,
)
from domain.team.model.wish_card import WishCard


def test_record_responsibility_chain_when_workflow_assigns_card() -> None:
    # Arrange
    card = WishCard.create("team-1", "Ship feature", creator_id="user-1")

    # Act
    execution = card.assign_to(
        "worker-1",
        triggered_by=ExecutionTrigger.WORKFLOW,
        delegated_by_slot_id="leader-1",
        flow_plan_id="plan-1",
        flow_step_id="step-1",
    )

    # Assert
    assert card.attribution_chain == [{
        "sequence": 1,
        "execution_id": execution.id,
        "agent_slot_id": "worker-1",
        "delegated_by_slot_id": "leader-1",
        "trigger": "workflow",
        "flow_plan_id": "plan-1",
        "flow_step_id": "step-1",
        "instruction": "",
        "assigned_at": execution.created_at.isoformat(),
    }]


def test_classify_retryable_network_failure_when_connection_is_lost() -> None:
    # Arrange
    reason = "Connection reset while dispatching the agent query"

    # Act
    failure = classify_execution_failure(reason)

    # Assert
    assert failure == (
        type(failure)(
            category=ExecutionFailureCategory.NETWORK_ERROR,
            phase=ExecutionFailurePhase.DISPATCH,
            retryable=True,
        )
    )


def test_classify_non_retryable_validation_failure_when_request_is_invalid() -> None:
    # Arrange
    reason = "Invalid tool arguments"

    # Act
    failure = classify_execution_failure(reason)

    # Assert
    assert failure.category is ExecutionFailureCategory.VALIDATION
    assert failure.phase is ExecutionFailurePhase.EXECUTION
    assert failure.retryable is False


def test_classify_retryable_reconciliation_failure_when_cli_receives_sighup() -> None:
    # Arrange
    reason = "Command failed with exit code 129 (exit code: 129)"

    # Act
    failure = classify_execution_failure(reason)

    # Assert
    assert failure.category is ExecutionFailureCategory.RECONCILIATION
    assert failure.phase is ExecutionFailurePhase.RECONCILIATION
    assert failure.retryable is True
