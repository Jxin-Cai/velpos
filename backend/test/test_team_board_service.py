from types import SimpleNamespace

import pytest

from application.team_board.commands import MoveWishCardCommand
from application.team_board.team_board_service import TeamBoardApplicationService
from domain.team.model.team_domain_error import TeamDomainError
from domain.team.model.wish_card import WishCard


@pytest.mark.asyncio
async def test_move_rejected_when_route_team_does_not_own_card() -> None:
    # Arrange
    card = WishCard.create(team_id="team-owner", title="Private card")
    service = object.__new__(TeamBoardApplicationService)
    service._card_repo = SimpleNamespace(find_by_id=lambda _card_id: _async_value(card))
    command = MoveWishCardCommand(
        team_id="different-team",
        card_id=card.id,
        target_slot_id="slot-1",
        card_version=card.version,
        idempotency_key="request-1",
    )

    # Act / Assert
    with pytest.raises(TeamDomainError, match="does not belong to team"):
        await service._move_card_locked(command)


async def _async_value(value):
    return value
