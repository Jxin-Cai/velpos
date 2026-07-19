from collections.abc import Callable

import pytest

from domain.team.model.card_execution import CardExecution
from domain.team.model.status import CardExecutionStatus, WishCardStatus
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.model.wish_card import WishCard


def test_execution_prepared_when_backlog_card_is_assigned() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")

    # Act
    execution = card.assign_to("slot-1")

    # Assert
    assert execution.status is CardExecutionStatus.PREPARING
    assert card.status is WishCardStatus.PREPARING
    assert card.active_execution == execution


def test_idempotency_key_preserved_when_card_is_assigned() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")

    # Act
    execution = card.assign_to("slot-1", "move-request-1")

    # Assert
    assert execution.idempotency_key == "move-request-1"


def test_card_running_when_execution_starts() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")

    # Act
    card.start_execution(execution.id)

    # Assert
    assert execution.status is CardExecutionStatus.RUNNING
    assert card.status is WishCardStatus.RUNNING


def test_card_completed_when_running_execution_completes() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)

    # Act
    card.complete_execution(execution.id)

    # Assert
    assert execution.status is CardExecutionStatus.COMPLETED
    assert card.status is WishCardStatus.COMPLETED
    assert card.active_execution is None


def test_new_execution_created_when_completed_card_is_reassigned() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    first_execution = card.assign_to("slot-1")
    card.start_execution(first_execution.id)
    card.complete_execution(first_execution.id)

    # Act
    second_execution = card.assign_to("slot-2")

    # Assert
    assert second_execution.id != first_execution.id
    assert card.status is WishCardStatus.PREPARING
    assert len(card.executions) == 2


@pytest.mark.parametrize(
    "finish_execution",
    [
        lambda card, execution_id: card.fail_execution(execution_id, "failed"),
        lambda card, execution_id: card.cancel_execution(execution_id),
    ],
    ids=["failed", "cancelled"],
)
def test_new_execution_created_when_failed_card_is_retried(finish_execution: Callable[[WishCard, str], None]) -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)
    finish_execution(card, execution.id)

    # Act
    retry = card.retry_on("slot-1")

    # Assert
    assert retry.id != execution.id
    assert card.status is WishCardStatus.PREPARING


def test_assignment_rejected_when_card_is_preparing() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    card.assign_to("slot-1")

    # Act
    def assign_again() -> None:
        card.assign_to("slot-2")

    # Assert
    with pytest.raises(TeamDomainError):
        assign_again()


def test_assignment_rejected_when_card_is_running() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)

    # Act
    def assign_again() -> None:
        card.assign_to("slot-2")

    # Assert
    with pytest.raises(TeamDomainError):
        assign_again()


@pytest.mark.parametrize(
    "finish_execution",
    [
        lambda card, execution_id: card.fail_execution(execution_id, "failed"),
        lambda card, execution_id: card.cancel_execution(execution_id),
    ],
    ids=["failed", "cancelled"],
)
def test_new_execution_created_when_interrupted_card_is_reassigned(
    finish_execution: Callable[[WishCard, str], None],
) -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")
    finish_execution(card, execution.id)

    # Act
    next_execution = card.assign_to("slot-2")

    # Assert
    assert next_execution.agent_slot_id == "slot-2"
    assert card.status is WishCardStatus.PREPARING


@pytest.mark.parametrize(
    "finish_execution",
    [
        lambda card, execution_id: card.complete_execution(execution_id),
        lambda card, execution_id: card.fail_execution(execution_id, "failed"),
        lambda card, execution_id: card.cancel_execution(execution_id),
    ],
    ids=["completed", "failed", "cancelled"],
)
def test_card_archived_when_execution_is_terminal(
    finish_execution: Callable[[WishCard, str], None],
) -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)
    finish_execution(card, execution.id)

    # Act
    card.archive()

    # Assert
    assert card.status is WishCardStatus.ARCHIVED
    assert card.current_slot_id is None


def test_archive_rejected_when_card_is_running() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    execution = card.assign_to("slot-1")
    card.start_execution(execution.id)

    # Act
    def archive_running_card() -> None:
        card.archive()

    # Assert
    with pytest.raises(TeamDomainError):
        archive_running_card()


def test_second_active_execution_detected_when_card_is_inconsistent() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Implement domain")
    card.executions.extend(
        [
            CardExecution.create(card.id, "slot-1"),
            CardExecution.create(card.id, "slot-2"),
        ]
    )

    # Act
    def get_active_execution() -> CardExecution | None:
        return card.active_execution

    # Assert
    with pytest.raises(TeamDomainError):
        get_active_execution()


def test_execution_transition_rejected_when_execution_is_terminal() -> None:
    # Arrange
    execution = CardExecution.create(card_id="card-1", agent_slot_id="slot-1")
    execution.cancel()

    # Act
    def restart_execution() -> None:
        execution.start()

    # Assert
    with pytest.raises(TeamDomainError):
        restart_execution()
