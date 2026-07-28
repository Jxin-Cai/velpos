from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.team.model.agent_slot import AgentSlot
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.team import Team
    from domain.team.model.wish_card import WishCard


class TeamBoardAssembler:
    """Converts Team domain models to response DTOs for the board API."""

    @staticmethod
    def to_board_response(
        team: Team,
        cards: list[WishCard],
        readiness_map: dict[str, str],
        user_action_map: dict[str, bool],
        summary_map: dict[str, str] | None = None,
    ) -> dict:
        return {
            "team_id": team.id,
            "name": team.name,
            "slots": [TeamBoardAssembler._to_slot_dto(s) for s in team.agent_slots],
            "cards": [
                TeamBoardAssembler._to_card_summary_dto(
                    card,
                    readiness_map.get(card.id, "none"),
                    user_action_map.get(card.id, False),
                    (summary_map or {}).get(card.id, ""),
                )
                for card in cards
            ],
        }

    @staticmethod
    def _to_slot_dto(slot: AgentSlot) -> dict:
        return {
            "id": slot.id,
            "display_name": slot.name,
            "agent_profile_id": slot.role,
            "availability": slot.availability.value,
        }

    @staticmethod
    def _to_card_summary_dto(
        card: WishCard,
        handoff_readiness: str,
        needs_user_action: bool,
        latest_stage_summary: str = "",
    ) -> dict:
        latest = card.latest_execution
        return {
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "status": card.status.value,
            "current_slot_id": card.current_slot_id,
            "version": card.version,
            "session_id": latest.session_id if latest else None,
            "execution_id": latest.id if latest else None,
            "failure_reason": latest.failure_reason if latest else None,
            "needs_user_action": needs_user_action,
            "handoff_readiness": handoff_readiness,
            "execution_count": len(card.executions),
            "latest_stage_summary": latest_stage_summary,
        }

    @staticmethod
    def to_card_created_response(card: WishCard) -> dict:
        return {
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "status": card.status.value,
            "current_slot_id": card.current_slot_id,
            "version": card.version,
            "session_id": None,
        }

    @staticmethod
    def to_card_status_response(card: WishCard) -> dict:
        return {
            "id": card.id,
            "status": card.status.value,
            "current_slot_id": card.current_slot_id,
            "version": card.version,
        }

    @staticmethod
    def to_execution_response(execution: CardExecution) -> dict:
        return {
            "execution_id": execution.id,
            "status": execution.status.value,
            "session_id": execution.session_id,
        }

    @staticmethod
    def to_execution_detail_response(execution: CardExecution) -> dict:
        return {
            "id": execution.id,
            "card_id": execution.card_id,
            "agent_slot_id": execution.agent_slot_id,
            "status": execution.status.value,
            "session_id": execution.session_id,
        }
