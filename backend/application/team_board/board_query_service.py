from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.shared.business_exception import BusinessException
from domain.team.model.status import CardExecutionStatus
from domain.team.model.team_domain_error import TeamDomainError

if TYPE_CHECKING:
    from application.session.session_application_service import SessionApplicationService
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.stage_output import StageOutput
    from domain.team.model.team import Team
    from domain.team.model.wish_card import WishCard
    from domain.team.repository.card_execution_repository import CardExecutionRepository
    from domain.team.repository.handoff_repository import HandoffRepository
    from domain.team.repository.stage_output_repository import StageOutputRepository
    from domain.team.repository.team_repository import TeamRepository
    from domain.team.repository.wish_card_repository import WishCardRepository

logger = logging.getLogger(__name__)


class BoardQueryService:
    def __init__(
        self,
        team_repo: TeamRepository,
        card_repo: WishCardRepository,
        execution_repo: CardExecutionRepository,
        handoff_repo: HandoffRepository,
        stage_output_repo: StageOutputRepository,
        session_service: SessionApplicationService,
    ) -> None:
        self._team_repo = team_repo
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._handoff_repo = handoff_repo
        self._stage_output_repo = stage_output_repo
        self._session_service = session_service

    async def get_board(self, team_id: str) -> tuple[Team, list[WishCard]]:
        from domain.team.model.wish_card import WishCard

        team = await self._team_repo.find_by_id(team_id)
        if team is None:
            raise TeamDomainError(f"Team {team_id} not found")
        cards = await self._card_repo.find_by_team_id(team_id)
        return team, cards

    async def get_execution(self, execution_id: str) -> CardExecution:
        execution = await self._execution_repo.find_by_id(execution_id)
        if execution is None:
            raise TeamDomainError("execution not found")
        return execution

    async def get_latest_stage_summary(self, card_id: str) -> str:
        """Return the stage summary from the most recent output of a card."""
        outputs = await self._stage_output_repo.find_by_card_id(card_id)
        if not outputs:
            return ""
        latest = max(outputs, key=lambda o: o.revision)
        return latest.content.get("stage_summary", "") if latest.content else ""

    async def get_handoff_readiness(self, execution: CardExecution | None) -> str:
        if execution is None or execution.status is not CardExecutionStatus.COMPLETED:
            return "none"
        output = await self._stage_output_repo.find_latest_by_execution_id(execution.id)
        return output.status.value if output is not None else "legacy"

    async def execution_needs_user_action(self, execution: CardExecution | None) -> bool:
        if execution is None or execution.status is not CardExecutionStatus.RUNNING or not execution.session_id:
            return False
        session = await self._session_service.get_session(execution.session_id)
        return bool(session.pending_request_context)

    async def get_card_history(self, execution_id: str) -> list[dict[str, object]]:
        execution = await self.get_execution(execution_id)
        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {execution.card_id} not found")
        team = await self._team_repo.find_by_id(card.team_id)
        if team is None:
            raise TeamDomainError(f"Team {card.team_id} not found")
        slot_names = {slot.id: slot.name for slot in team.agent_slots}

        handoffs = await self._handoff_repo.find_by_card_id(card.id)
        stage_outputs = await self._stage_output_repo.find_by_card_id(card.id)
        handoff_by_source = {h.source_execution_id: h for h in handoffs}
        handoff_by_target = {
            h.target_execution_id: h
            for h in handoffs
            if h.target_execution_id is not None
        }
        output_by_execution: dict[str, StageOutput] = {}
        for output in stage_outputs:
            current = output_by_execution.get(output.execution_id)
            if current is None or output.revision > current.revision:
                output_by_execution[output.execution_id] = output

        result: list[dict[str, object]] = []
        executions = card.executions
        for idx, item in enumerate(executions):
            sdk_session_id = ""
            if item.session_id:
                try:
                    session = await self._session_service.get_session(item.session_id)
                    sdk_session_id = session.sdk_session_id
                    if sdk_session_id.startswith("fork:"):
                        sdk_session_id = ""
                except BusinessException:
                    sdk_session_id = ""
            entry: dict[str, object] = {
                "execution_id": item.id,
                "agent_slot_id": item.agent_slot_id,
                "agent_name": slot_names.get(item.agent_slot_id, item.agent_slot_id),
                "status": item.status.value,
                "session_id": item.session_id,
                "sdk_session_id": sdk_session_id,
                "created_at": item.created_at.isoformat(),
                "started_at": item.started_at.isoformat() if item.started_at else None,
                "ended_at": item.ended_at.isoformat() if item.ended_at else None,
                "failure_reason": item.failure_reason,
                "input_stage_output_id": item.input_stage_output_id,
            }
            stage_output = output_by_execution.get(item.id)
            entry["output"] = (
                self._serialize_stage_output(stage_output)
                if stage_output is not None
                else None
            )
            previous_id = executions[idx - 1].id if idx > 0 else None
            handoff = handoff_by_target.get(item.id)
            if handoff is None and previous_id:
                handoff = handoff_by_source.get(previous_id)
            if handoff is not None:
                entry["handoff"] = {
                    "id": handoff.id,
                    "summary": handoff.summary,
                    "stage_output_id": handoff.stage_output_id,
                    "consumed_revision": handoff.consumed_revision,
                    "consumed_checksum": handoff.consumed_checksum,
                    "source_agent_name": slot_names.get(
                        handoff.source_agent_slot_id, handoff.source_agent_slot_id
                    ),
                    "artifacts": [
                        {"name": a.name, "path": a.path, "media_type": a.media_type}
                        for a in handoff.artifacts
                    ],
                }
            else:
                entry["handoff"] = None
            result.append(entry)
        return result

    @staticmethod
    def _serialize_stage_output(stage_output: StageOutput) -> dict[str, object]:
        return {
            "id": stage_output.id,
            "revision": stage_output.revision,
            "schema_version": stage_output.schema_version,
            "status": stage_output.status.value,
            "content": stage_output.content,
            "rendered_markdown": stage_output.rendered_markdown,
            "checksum": stage_output.checksum,
            "compression_method": stage_output.compression_method,
            "created_at": stage_output.created_at.isoformat(),
            "artifacts": [
                {
                    "id": artifact.id,
                    "name": artifact.name,
                    "path": artifact.path,
                    "media_type": artifact.media_type,
                }
                for artifact in stage_output.artifacts
            ],
        }
