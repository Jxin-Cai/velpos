import pytest

from domain.team.model.team import Team
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.model.wish_card import WishCard


def test_agent_slot_added_when_workspace_is_independent() -> None:
    # Arrange
    team = Team.create(project_id="project-1", name="Delivery team")

    # Act
    slot = team.add_agent_slot(
        name="backend",
        role="Backend engineer",
        workspace_ref="workspace/backend",
    )

    # Assert
    assert team.find_agent_slot(slot.id) == slot


def test_agent_slot_rejected_when_workspace_is_shared() -> None:
    # Arrange
    team = Team.create(project_id="project-1", name="Delivery team")
    team.add_agent_slot(
        name="backend",
        role="Backend engineer",
        workspace_ref="workspace/shared",
    )

    # Act
    def add_shared_workspace() -> None:
        team.add_agent_slot(
            name="frontend",
            role="Frontend engineer",
            workspace_ref="workspace/shared",
        )

    # Assert
    with pytest.raises(TeamDomainError):
        add_shared_workspace()


def test_multiple_cards_assigned_when_agent_slot_is_same() -> None:
    # Arrange
    first_card = WishCard.create(team_id="team-1", title="First card")
    second_card = WishCard.create(team_id="team-1", title="Second card")

    # Act
    first_execution = first_card.assign_to("slot-1")
    second_execution = second_card.assign_to("slot-1")

    # Assert
    assert first_execution.agent_slot_id == second_execution.agent_slot_id
