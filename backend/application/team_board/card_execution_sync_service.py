"""Synchronizes card execution state after a session completes or fails.

This service replaces the cross-layer _sync_team_card_execution method that
previously lived inside SessionQueryEngine with direct infr dependencies.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from application.team_board.stage_output_builder import StageOutputBuilder
from application.team_board.failure_taxonomy import classify_execution_failure
from domain.session.service.message_conversion_service import MessageConversionService
from domain.team.acl.session_context_collector import SessionArtifact
from domain.team.model.status import CardExecutionStatus, ExecutionFailureCategory

if TYPE_CHECKING:
    from application.team_board.flow_engine_service import FlowEngineService
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
        flow_engine: FlowEngineService | None = None,
    ) -> None:
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._stage_output_repo = stage_output_repo
        self._team_repo = team_repo
        self._connection_manager = connection_manager
        self._collect_artifacts_fn = collect_artifacts_fn
        self._flow_engine = flow_engine

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
        # Stale-snapshot early exit (optimisation — not a safety guarantee against races).
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

        # Capture in-card execution reference BEFORE domain mutation so we can
        # pass the mutated object to the atomic conditional save below.
        active_exec = card.active_execution
        if active_exec is None or active_exec.id != execution.id:
            logger.warning(
                "[session=%s] execution %s is not the active execution on card %s "
                "(active=%s); skipping sync to avoid overwriting a later state",
                session.session_id,
                execution.id,
                card.id,
                active_exec.id if active_exec else "none",
            )
            return

        # Apply domain mutations in memory only.
        if succeeded:
            card.complete_execution(execution.id)   # active_exec.status → COMPLETED
        else:
            classified_failure = classify_execution_failure(
                reason.strip() or "Agent execution failed"
            )
            card.fail_execution(
                execution.id,
                reason.strip() or "Agent execution failed",
                classified_failure.category,
                classified_failure.phase,
                classified_failure.retryable,
            )  # active_exec.status → FAILED

        # Atomic conditional DB write.  This is the first database write and
        # the sole arbiter of which concurrent writer claims the terminal
        # transition.  It succeeds only when the DB row is still non-terminal.
        saved = await self._execution_repo.save_terminal_if_non_terminal(active_exec)
        if not saved:
            fresh = await self._execution_repo.find_by_id(execution.id)
            logger.warning(
                "[session=%s] sync: terminal transition race lost for execution %s; "
                "winning DB state=%s; skipping card save, broadcast, and flow callbacks",
                session.session_id,
                execution.id,
                fresh.status.value if fresh else "unknown",
            )
            return

        # We won the atomic transition — carry out downstream side effects.
        slot_availability: str | None = None
        if succeeded:
            slot_availability = await self._handle_success(session, card, execution)
        else:
            slot_availability = await self._handle_failure(session, card, execution, reason)

        # The execution row was already persisted by the conditional update.
        # Persist only the parent card fields so a stale ORM child snapshot
        # cannot overwrite the terminal execution state.
        await self._card_repo.save_state(card)
        await self._broadcast(card, execution, succeeded, slot_availability)

        if self._flow_engine is not None:
            try:
                if succeeded:
                    await self._flow_engine.on_execution_completed(card.id, execution.id, session)
                else:
                    await self._flow_engine.on_execution_failed(
                        card.id,
                        execution.id,
                        reason,
                        active_exec.failure_category or ExecutionFailureCategory.UNKNOWN,
                    )
            except Exception:
                logger.error(
                    "[session=%s] FlowEngine callback failed for execution %s, "
                    "card sync was still committed",
                    session.session_id,
                    execution.id,
                    exc_info=True,
                )

    async def _handle_success(
        self,
        session: Session,
        card: WishCard,
        execution: CardExecution,
    ) -> str | None:
        # card.complete_execution() was already called in sync() before the
        # atomic save, so we proceed directly to side effects here.
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
        # card.fail_execution() was already called in sync() before the atomic
        # save, so we proceed directly to side effects here.
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
            "failure_category": (
                latest.failure_category.value if latest and latest.failure_category else None
            ),
            "failure_phase": (
                latest.failure_phase.value if latest and latest.failure_phase else None
            ),
            "failure_retryable": latest.failure_retryable if latest else None,
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
