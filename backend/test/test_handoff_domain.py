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


def test_handoff_accepted_when_created_between_different_slots() -> None:
    # Arrange & Act
    handoff = _create_handoff()

    # Assert
    assert handoff.status is HandoffStatus.ACCEPTED
    assert handoff.resolved_at is not None


def test_creation_rejected_when_target_is_source_slot() -> None:
    # Arrange
    handoff_arguments = {
        "team_id": "team-1",
        "card_id": "card-1",
        "source_execution_id": "execution-1",
        "source_agent_slot_id": "slot-1",
        "target_agent_slot_id": "slot-1",
        "summary": "Continue the work.",
    }

    # Act & Assert
    with pytest.raises(TeamDomainError):
        Handoff.create(**handoff_arguments)


def test_creation_rejected_when_required_field_is_blank() -> None:
    # Act & Assert
    with pytest.raises(TeamDomainError):
        Handoff.create(
            team_id="team-1",
            card_id="card-1",
            source_execution_id="execution-1",
            source_agent_slot_id="slot-1",
            target_agent_slot_id="slot-2",
            summary="  ",
        )


def test_artifact_added_when_valid_name_and_path() -> None:
    # Arrange
    handoff = _create_handoff()

    # Act
    artifact = handoff.add_artifact(name="report.pdf", path="/output/report.pdf", media_type="application/pdf")

    # Assert
    assert artifact.name == "report.pdf"
    assert artifact.path == "/output/report.pdf"
    assert len(handoff.artifacts) == 1


def test_artifact_rejected_when_name_is_blank() -> None:
    # Arrange
    handoff = _create_handoff()

    # Act & Assert
    with pytest.raises(TeamDomainError):
        handoff.add_artifact(name="  ", path="/output/report.pdf")
