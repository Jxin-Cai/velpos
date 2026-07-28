"""Synchronizes card execution state after a session completes or fails.

This service replaces the cross-layer _sync_team_card_execution method that
previously lived inside SessionQueryEngine with direct infr dependencies.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from application.team_board.stage_output_builder import StageOutputBuilder
from domain.session.service.message_conversion_service import MessageConversionService
from domain.team.acl.session_context_collector import SessionArtifact
from domain.team.model.status import CardExecutionStatus

if TYPE_CHECKING:
    from domain.session.acl.connection_manager import ConnectionManager
    from domain.session.model.session import Session
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.wish_card import WishCard
    from domain.team.repository.card_execution_repository import CardExecutionRepository
    from domain.team.repository.stage_output_repository import StageOutputRepository
    from domain.team.repository.team_repository import TeamRepository
    from domain.team.repository.wish_card_repository import WishCardRepository

logger = logging.getLogger(__name__)


class CardExecutionSyncService:
    def __init__(
        self,
        card_repo: WishCardRepository,
        execution_repo: CardExecutionRepository,
        stage_output_repo: StageOutputRepository,
        team_repo: TeamRepository,
        connection_manager: ConnectionManager | None = None,
        collect_artifacts_fn: Callable[[list, str], Iterable[SessionArtifact]] | None = None,
    ) -> None:
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._stage_output_repo = stage_output_repo
        self._team_repo = team_repo
        self._connection_manager = connection_manager
        self._collect_artifacts_fn = collect_artifacts_fn

    async def sync(
        self,
        session: Session,
        *,
        succeeded: bool,
        reason: str = "",
    ) -> None:
        if not session.card_execution_id:
            return

        execution = await self._execution_repo.find_by_id(session.card_execution_id)
        if execution is None:
            logger.error(
                "[session=%s] team execution not found: %s",
                session.session_id,
                session.card_execution_id,
            )
            return

        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            logger.error(
                "[session=%s] wish card not found for execution: %s",
                session.session_id,
                execution.id,
            )
            return

        expected_status = (
            CardExecutionStatus.COMPLETED if succeeded else CardExecutionStatus.FAILED
        )
        if execution.is_terminal:
            log = logger.info if execution.status is expected_status else logger.warning
            log(
                "[session=%s] skipping card execution sync because execution %s "
                "is already terminal with status=%s, expected=%s",
                session.session_id,
                execution.id,
                execution.status.value,
                expected_status.value,
            )
            return

        slot_availability: str | None = None

        if succeeded:
            slot_availability = await self._handle_success(session, card, execution)
        else:
            slot_availability = await self._handle_failure(
                session, card, execution, reason
            )

        await self._card_repo.save(card)
        await self._broadcast(card, execution, succeeded, slot_availability)

    async def _handle_success(
        self,
        session: Session,
        card: WishCard,
        execution: CardExecution,
    ) -> str | None:
        card.complete_execution(execution.id)

        existing_output = await self._stage_output_repo.find_latest_by_execution_id(
            execution.id
        )
        if existing_output is None:
            final_output = MessageConversionService.extract_assistant_text(
                session.messages
            )
            artifacts: Iterable[SessionArtifact] = ()
            if self._collect_artifacts_fn is not None:
                artifacts = self._collect_artifacts_fn(
                    session.messages, session.project_dir
                )
            stage_output = StageOutputBuilder.build(
                card=card,
                execution=execution,
                source_session_id=session.session_id,
                final_output=final_output,
                artifacts=artifacts,
                previous_output_id=execution.input_stage_output_id,
            )
            await self._stage_output_repo.save(stage_output)

        if execution.agent_slot_id:
            team = await self._team_repo.find_by_id(card.team_id)
            if team is not None:
                slot = team.find_agent_slot(execution.agent_slot_id)
                if slot is not None and not slot.is_available:
                    slot.mark_available()
                    await self._team_repo.save(team)
        return None

    async def _handle_failure(
        self,
        session: Session,
        card: WishCard,
        execution: CardExecution,
        reason: str,
    ) -> str | None:
        card.fail_execution(execution.id, reason.strip() or "Agent execution failed")

        slot_availability: str | None = None
        if execution.agent_slot_id:
            team = await self._team_repo.find_by_id(card.team_id)
            if team is not None:
                slot = team.find_agent_slot(execution.agent_slot_id)
                if slot is not None:
                    slot.mark_unstable()
                    await self._team_repo.save(team)
                    slot_availability = slot.availability.value
        return slot_availability

    async def _broadcast(
        self,
        card: WishCard,
        execution: CardExecution,
        succeeded: bool,
        slot_availability: str | None,
    ) -> None:
        if self._connection_manager is None:
            return
        latest = card.latest_execution
        payload: dict[str, object] = {
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "status": card.status.value,
            "current_slot_id": card.current_slot_id,
            "version": card.version,
            "updated_at": card.updated_at.isoformat(),
            "session_id": latest.session_id if latest else None,
            "execution_id": latest.id if latest else None,
            "failure_reason": latest.failure_reason if latest else None,
            "handoff_readiness": "ready" if succeeded else "none",
        }
        if slot_availability is not None:
            payload["slot_availability"] = slot_availability
            payload["slot_id"] = execution.agent_slot_id
        await self._connection_manager.broadcast_global({
            "event": "board_card_updated",
            "team_id": card.team_id,
            "card": payload,
        })
