import pytest

from domain.team.model.handoff import Handoff
from domain.team.model.status import HandoffStatus
from domain.team.model.team_domain_error import TeamDomainError


def _create_handoff() -> Handoff:
    return Handoff.create(
        team_id="team-1",
        card_id="card-1",
        source_execution_id="execution-1",
        source_agent_slot_id="slot-1",
        target_agent_slot_id="slot-2",
        summary="Continue from the completed analysis.",
    )


def test_handoff_pending_when_created_between_different_slots() -> None:
    # Arrange
    handoff = _create_handoff()

    # Act
    status = handoff.status

    # Assert
    assert status is HandoffStatus.PENDING


def test_handoff_rejected_when_target_is_source_slot() -> None:
    # Arrange
    handoff_arguments = {
        "team_id": "team-1",
        "card_id": "card-1",
        "source_execution_id": "execution-1",
        "source_agent_slot_id": "slot-1",
        "target_agent_slot_id": "slot-1",
        "summary": "Continue the work.",
    }

    # Act
    def create_handoff() -> None:
        Handoff.create(**handoff_arguments)

    # Assert
    with pytest.raises(TeamDomainError):
        create_handoff()


def test_handoff_accepted_when_pending() -> None:
    # Arrange
    handoff = _create_handoff()

    # Act
    handoff.accept()

    # Assert
    assert handoff.status is HandoffStatus.ACCEPTED
    assert handoff.resolved_at is not None


def test_handoff_transition_rejected_when_already_resolved() -> None:
    # Arrange
    handoff = _create_handoff()
    handoff.reject()

    # Act
    def accept_rejected_handoff() -> None:
        handoff.accept()

    # Assert
    with pytest.raises(TeamDomainError):
        accept_rejected_handoff()
