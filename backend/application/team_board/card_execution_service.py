from __future__ import annotations

import logging
import os
from html import escape
from typing import TYPE_CHECKING, Awaitable, Callable

from application.session.command.create_session_command import CreateSessionCommand
from application.team_board.execution_dispatch import dispatch_execution_query
from application.team_board.team_workspace_helpers import (
    ensure_agent_project,
    prepare_execution_workspace,
)
from domain.shared.async_utils import KeyedLockPool, safe_create_task
from domain.team.model.status import CardExecutionStatus, ExecutionTrigger
from domain.team.model.team_domain_error import TeamDomainError

if TYPE_CHECKING:
    from application.session.session_application_service import SessionApplicationService
    from application.team_board.commands import (
        ArchiveWishCardCommand,
        CreateWishCardCommand,
        DeleteWishCardCommand,
        MoveWishCardCommand,
        RetryExecutionCommand,
    )
    from application.team_board.leader_session_manager import LeaderSessionManager
    from collections.abc import Iterable
    from domain.project.repository.project_repository import ProjectRepository
    from domain.session.acl.connection_manager import ConnectionManager
    from domain.session.repository.session_repository import SessionRepository
    from domain.team.acl.session_context_collector import SessionArtifact
    from domain.team.acl.workspace_gateway import WorkspaceGateway
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.handoff import Handoff
    from domain.team.model.stage_output import StageOutput
    from domain.team.model.team import Team
    from domain.team.model.wish_card import WishCard
    from domain.team.repository.card_execution_repository import CardExecutionRepository
    from domain.team.repository.handoff_repository import HandoffRepository
    from domain.team.repository.stage_output_repository import StageOutputRepository
    from domain.team.repository.team_repository import TeamRepository
    from domain.team.repository.wish_card_repository import WishCardRepository

logger = logging.getLogger(__name__)


def _format_handoff_artifact_links(handoff: Handoff) -> str:
    return "\n".join(
        (
            '- <a class="file-path-link" data-file-path="'
            f'{escape(artifact.path, quote=True)}" href="#" title="Click to open">'
            f"{escape(artifact.name)}</a> — `{artifact.path}`"
        )
        for artifact in handoff.artifacts
    )


class CardExecutionService:
    _card_lock_pool = KeyedLockPool(max_size=1_000)

    def __init__(
        self,
        team_repo: TeamRepository,
        card_repo: WishCardRepository,
        execution_repo: CardExecutionRepository,
        handoff_repo: HandoffRepository,
        stage_output_repo: StageOutputRepository,
        workspace_gateway: WorkspaceGateway,
        session_service: SessionApplicationService,
        session_service_factory: Callable[[], Awaitable[SessionApplicationService]],
        project_repo: ProjectRepository,
        connection_manager: ConnectionManager | None = None,
        session_repo: SessionRepository | None = None,
        fail_execution_fn: Callable[..., Awaitable[None]] | None = None,
        collect_artifacts_fn: Callable[[list, str], Iterable[SessionArtifact]] | None = None,
        leader_session_manager: LeaderSessionManager | None = None,
    ) -> None:
        self._team_repo = team_repo
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._handoff_repo = handoff_repo
        self._stage_output_repo = stage_output_repo
        self._workspace = workspace_gateway
        self._session_service = session_service
        self._session_service_factory = session_service_factory
        self._project_repo = project_repo
        self._connection_manager = connection_manager
        self._session_repo = session_repo
        self._fail_execution_fn = fail_execution_fn
        self._collect_artifacts_fn = collect_artifacts_fn
        self._leader_session_manager = leader_session_manager

    # ── Public use cases ──────────────────────────────────────

    async def create_card(self, cmd: CreateWishCardCommand) -> WishCard:
        from domain.team.model.wish_card import WishCard

        team = await self._team_repo.find_by_id(cmd.team_id)
        if team is None:
            raise TeamDomainError(f"Team {cmd.team_id} not found")
        card = WishCard.create(
            team_id=team.id,
            title=cmd.title,
            description=cmd.description,
        )
        await self._card_repo.save(card)
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return card

    async def archive_card(self, cmd: ArchiveWishCardCommand) -> WishCard:
        card = await self._require_team_card(cmd.team_id, cmd.card_id)
        if card.version != cmd.card_version:
            raise TeamDomainError(
                f"Card version mismatch: expected {cmd.card_version}, got {card.version}"
            )
        card.archive()
        await self._card_repo.save(card)
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return card

    async def delete_archived_card(self, cmd: DeleteWishCardCommand) -> None:
        from domain.team.model.status import WishCardStatus

        card = await self._require_team_card(cmd.team_id, cmd.card_id)
        if card.status is not WishCardStatus.ARCHIVED:
            raise TeamDomainError("only archived wish cards can be deleted")

        executions = await self._execution_repo.find_by_card_id(card.id)
        if executions and self._session_repo is not None:
            await self._session_repo.clear_card_execution_references(
                [execution.id for execution in executions]
            )
        await self._handoff_repo.remove_by_card_id(card.id)
        await self._stage_output_repo.remove_by_card_id(card.id)
        await self._execution_repo.remove_by_card_id(card.id)
        await self._card_repo.remove(card)
        await self._broadcast_board_event("board_card_deleted", cmd.team_id, card.id)

    async def move_card(self, cmd: MoveWishCardCommand) -> CardExecution:
        card_lock = await self._card_lock_pool.acquire(cmd.card_id)
        try:
            async with card_lock:
                return await self._move_card_locked(cmd)
        finally:
            await self._card_lock_pool.unref(cmd.card_id)

    async def retry_execution(self, cmd: RetryExecutionCommand) -> CardExecution:
        # Early validation outside the lock to fail fast before acquiring resources.
        old_execution = await self._execution_repo.find_by_id(cmd.execution_id)
        if old_execution is None:
            raise TeamDomainError(f"Execution {cmd.execution_id} not found")
        if old_execution.status not in (CardExecutionStatus.FAILED, CardExecutionStatus.CANCELLED):
            raise TeamDomainError(
                f"Only failed/cancelled executions can be retried, got {old_execution.status}"
            )

        # Acquire the same per-card lock used by move_card so that retry and
        # move cannot race on the same card, and two concurrent retries of the
        # same execution are serialised.
        card_lock = await self._card_lock_pool.acquire(old_execution.card_id)
        try:
            async with card_lock:
                return await self._retry_execution_locked(cmd)
        finally:
            await self._card_lock_pool.unref(old_execution.card_id)

    async def _retry_execution_locked(self, cmd: RetryExecutionCommand) -> CardExecution:
        """Core retry logic.  Must be called while holding the per-card lock."""
        # Re-read authoritative state inside the lock so that the second of two
        # concurrent retries sees the updated card status and raises promptly.
        old_execution = await self._execution_repo.find_by_id(cmd.execution_id)
        if old_execution is None:
            raise TeamDomainError(f"Execution {cmd.execution_id} not found")
        if old_execution.status not in (CardExecutionStatus.FAILED, CardExecutionStatus.CANCELLED):
            raise TeamDomainError(
                f"Only failed/cancelled executions can be retried, got {old_execution.status}"
            )

        card = await self._card_repo.find_by_id(old_execution.card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {old_execution.card_id} not found")
        team = await self._team_repo.find_by_id(card.team_id)
        if team is None:
            raise TeamDomainError(f"Team {card.team_id} not found")
        target_slot = team.find_agent_slot(old_execution.agent_slot_id)
        if target_slot is None:
            raise TeamDomainError(f"Slot {old_execution.agent_slot_id} not found")

        input_stage_output = (
            await self._stage_output_repo.find_by_id(old_execution.input_stage_output_id)
            if old_execution.input_stage_output_id
            else None
        )
        new_execution = card.retry_on(
            target_slot.id,
            old_execution.input_stage_output_id,
        )
        workspace_path = await prepare_execution_workspace(
            team, target_slot, new_execution.id, self._workspace, self._team_repo
        )

        card.start_execution(new_execution.id)
        await self._card_repo.save(card)
        await self._execution_repo.save(new_execution)
        agent_project = await ensure_agent_project(team.name, target_slot, self._project_repo)
        session, prompt = await self._create_execution_session(
            team=team,
            card=card,
            execution=new_execution,
            agent_project_id=agent_project.id,
            workspace_path=workspace_path,
            handoff=None,
            input_stage_output=input_stage_output,
        )
        new_execution.session_id = session.session_id

        await self._card_repo.save(card)
        await self._execution_repo.save(new_execution)
        safe_create_task(self._dispatch_execution_query_with_failsafe(
            session.session_id, prompt, card.id, new_execution.id
        ))
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return new_execution

    # ── Private orchestration ─────────────────────────────────

    async def _move_card_locked(self, cmd: MoveWishCardCommand) -> CardExecution:
        from domain.team.model.card_execution import CardExecution

        idempotency_key = cmd.idempotency_key.strip()
        if not idempotency_key:
            raise TeamDomainError("idempotency_key must not be blank")
        card = await self._card_repo.find_by_id(cmd.card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {cmd.card_id} not found")
        if card.team_id != cmd.team_id:
            raise TeamDomainError(f"Wish card {cmd.card_id} does not belong to team {cmd.team_id}")
        prior_executions = await self._execution_repo.find_by_card_id(card.id)
        duplicate = next(
            (
                execution
                for execution in prior_executions
                if execution.idempotency_key == idempotency_key
            ),
            None,
        )
        if duplicate is not None:
            if duplicate.agent_slot_id != cmd.target_slot_id:
                raise TeamDomainError(
                    "idempotency_key was already used for a different agent slot"
                )
            return duplicate
        if card.version != cmd.card_version:
            raise TeamDomainError(
                f"Card version mismatch: expected {cmd.card_version}, got {card.version}"
            )
        if not card.can_be_assigned:
            raise TeamDomainError(
                f"Card in status {card.status} cannot be assigned"
            )

        team = await self._team_repo.find_by_id(card.team_id)
        if team is None:
            raise TeamDomainError(f"Team {card.team_id} not found")
        target_slot = team.find_agent_slot(cmd.target_slot_id)
        if target_slot is None:
            raise TeamDomainError(f"Slot {cmd.target_slot_id} not found in team {team.id}")

        if target_slot.is_leader:
            return await self._move_card_to_leader(team, card, target_slot, idempotency_key, cmd)

        previous_execution = await self._find_last_completed_execution(card)

        input_stage_output = (
            await self._ensure_stage_output(previous_execution, card)
            if previous_execution is not None
            else None
        )
        execution = card.assign_to(
            target_slot.id,
            idempotency_key,
            input_stage_output.id if input_stage_output is not None else None,
            triggered_by=ExecutionTrigger(cmd.triggered_by),
            delegated_by_slot_id=cmd.delegated_by_slot_id,
            flow_plan_id=cmd.flow_plan_id,
            flow_step_id=cmd.flow_step_id,
            delegation_context=cmd.delegation_context,
        )
        workspace_path = await prepare_execution_workspace(
            team, target_slot, execution.id, self._workspace, self._team_repo
        )
        await self._execution_repo.save(execution)

        if previous_execution is not None:
            handoff = await self._prepare_handoff(
                previous_execution,
                execution,
                target_slot,
                card,
                input_stage_output,
            )
        else:
            handoff = None

        card.start_execution(execution.id)
        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        agent_project = await ensure_agent_project(team.name, target_slot, self._project_repo)
        session, prompt = await self._create_execution_session(
            team=team,
            card=card,
            execution=execution,
            agent_project_id=agent_project.id,
            workspace_path=workspace_path,
            handoff=handoff,
            input_stage_output=input_stage_output,
            delegation_context=cmd.delegation_context,
        )
        execution.session_id = session.session_id

        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        safe_create_task(self._dispatch_execution_query_with_failsafe(
            session.session_id, prompt, card.id, execution.id
        ))
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return execution

    async def _move_card_to_leader(
        self,
        team: Team,
        card: WishCard,
        leader_slot,
        idempotency_key: str,
        cmd: MoveWishCardCommand,
    ) -> CardExecution:
        """Handle card movement to the Leader slot using the persistent Leader session."""
        if self._leader_session_manager is None:
            raise TeamDomainError("Leader session manager is not configured")

        # Get or create the Leader's persistent session
        leader_session = await self._leader_session_manager.get_or_create_session(
            team, leader_slot
        )

        # Resolve previous execution context
        previous_execution = await self._find_last_completed_execution(card)
        input_stage_output = (
            await self._ensure_stage_output(previous_execution, card)
            if previous_execution is not None
            else None
        )

        # Create execution via domain model
        execution = card.assign_to(
            leader_slot.id,
            idempotency_key,
            input_stage_output.id if input_stage_output is not None else None,
            triggered_by=ExecutionTrigger.LEADER,
            delegated_by_slot_id=cmd.delegated_by_slot_id,
            flow_plan_id=cmd.flow_plan_id,
            flow_step_id=cmd.flow_step_id,
            delegation_context=cmd.delegation_context,
        )

        # Point execution at the Leader's persistent session (no new session created)
        execution.session_id = leader_session.session_id

        # Prepare handoff context
        if previous_execution is not None:
            handoff = await self._prepare_handoff(
                previous_execution, execution, leader_slot, card, input_stage_output
            )
        else:
            handoff = None

        card.start_execution(execution.id)
        await self._execution_repo.save(execution)
        await self._card_repo.save(card)

        # Build prompt with card context
        prompt = self._build_leader_prompt(team, card, handoff, input_stage_output)

        # Dispatch via LeaderSessionManager.append_message (no workspace prep needed)
        safe_create_task(
            self._dispatch_leader_message_with_failsafe(
                leader_session.session_id, prompt, card.id, execution.id
            )
        )
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return execution

    def _build_leader_prompt(
        self,
        team: Team,
        card: WishCard,
        handoff: Handoff | None,
        input_stage_output: StageOutput | None,
    ) -> str:
        if self._leader_session_manager is None:
            raise TeamDomainError("Leader session manager is not configured")
        prompt_parts = [
            self._leader_session_manager.build_coordination_context(team)
        ]
        prompt_parts.extend(
            self._build_card_context_parts(card, input_stage_output, handoff, include_card_id=True)
        )
        return "\n\n".join(prompt_parts)

    @staticmethod
    def _build_handoff_context_parts(
        input_stage_output: StageOutput | None,
        handoff: Handoff | None,
    ) -> list[str]:
        """Build the handoff/stage-output context section shared by leader and
        execution session prompts.

        Returns a list of prompt parts (each rendered as a Markdown section) so
        the caller can extend its own ``prompt_parts`` list directly.
        """
        parts: list[str] = []
        if input_stage_output is not None:
            parts.append(
                "## 上一阶段交接上下文\n"
                f"{input_stage_output.rendered_markdown}\n\n"
                f"上下文快照: `{input_stage_output.id}` "
                f"v{input_stage_output.revision} "
                f"sha256:{input_stage_output.checksum}"
            )
        elif handoff:
            parts.append(f"## 上一阶段交接上下文\n{handoff.summary}")
            if handoff.artifacts:
                artifact_lines = _format_handoff_artifact_links(handoff)
                parts.append(f"## 产物\n{artifact_lines}")
        return parts

    @staticmethod
    def _build_card_context_parts(
        card: WishCard,
        input_stage_output: StageOutput | None,
        handoff: Handoff | None,
        *,
        include_card_id: bool = False,
    ) -> list[str]:
        """Return prompt parts for handoff/stage-output context plus the card description.

        Callers append further sections (e.g. completion requirements) after this call.
        Pass ``include_card_id=True`` when the card identity must be explicit in the
        prompt (used by the Leader slot which dispatches to named worker slots).
        """
        parts = list(CardExecutionService._build_handoff_context_parts(input_stage_output, handoff))
        if include_card_id:
            parts.append(
                f"## 愿望卡\n"
                f"Card ID: `{card.id}`\n"
                f"标题: {card.title}\n"
                f"描述: {card.description}"
            )
        else:
            parts.append(f"## 愿望卡\n标题: {card.title}\n描述: {card.description}")
        return parts

    async def _dispatch_leader_message_with_failsafe(
        self, session_id: str, prompt: str, card_id: str, execution_id: str
    ) -> None:
        try:
            assert self._leader_session_manager is not None
            await self._leader_session_manager.append_message(session_id, prompt)
        except Exception:
            logger.error(
                "[session=%s] leader dispatch failed for execution %s, marking FAILED",
                session_id,
                execution_id,
                exc_info=True,
            )
            if self._fail_execution_fn is not None:
                await self._fail_execution_fn(card_id, execution_id, session_id)

    async def _require_team_card(self, team_id: str, card_id: str) -> WishCard:
        card = await self._card_repo.find_by_id(card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {card_id} not found")
        if card.team_id != team_id:
            raise TeamDomainError(f"Wish card {card_id} does not belong to team {team_id}")
        return card

    async def _broadcast_board_event(self, event: str, team_id: str, card_id: str | None = None) -> None:
        if self._connection_manager is None:
            return
        payload: dict[str, object] = {"event": event, "team_id": team_id}
        if card_id is not None:
            payload["card_id"] = card_id
        await self._connection_manager.broadcast_global(payload)

    async def _prepare_handoff(
        self,
        source_execution: CardExecution,
        target_execution: CardExecution,
        target_slot,
        card: WishCard,
        stage_output: StageOutput | None,
    ) -> Handoff:
        from domain.team.model.handoff import Handoff

        if stage_output is None:
            raise TeamDomainError("Completed execution has no ready stage output")
        handoff = Handoff.create(
            team_id=card.team_id,
            card_id=card.id,
            source_execution_id=source_execution.id,
            source_agent_slot_id=source_execution.agent_slot_id,
            target_agent_slot_id=target_slot.id,
            summary=stage_output.rendered_markdown,
            target_execution_id=target_execution.id,
            stage_output_id=stage_output.id,
            consumed_revision=stage_output.revision,
            consumed_checksum=stage_output.checksum,
        )
        for artifact in stage_output.artifacts:
            handoff.add_artifact(
                name=artifact.name,
                path=artifact.path,
                media_type=artifact.media_type,
            )
        await self._handoff_repo.save(handoff)
        return handoff

    async def _ensure_stage_output(
        self,
        source_execution: CardExecution,
        card: WishCard,
    ) -> StageOutput:
        from application.team_board.stage_output_builder import StageOutputBuilder
        from domain.session.service.message_conversion_service import MessageConversionService

        existing = await self._stage_output_repo.find_latest_by_execution_id(
            source_execution.id
        )
        if existing is not None:
            return existing
        if not source_execution.session_id:
            raise TeamDomainError("Completed execution has no source session")

        try:
            session = await self._session_service.get_session(source_execution.session_id)
            artifacts: Iterable[SessionArtifact] = ()
            if self._collect_artifacts_fn is not None:
                artifacts = self._collect_artifacts_fn(session.messages, session.project_dir)
            stage_output = StageOutputBuilder.build(
                card=card,
                execution=source_execution,
                source_session_id=session.session_id,
                final_output=MessageConversionService.extract_assistant_text(session.messages),
                artifacts=artifacts,
                previous_output_id=source_execution.input_stage_output_id,
            )
        except Exception:
            logger.warning(
                "[card=%s exec=%s] StageOutput build failed, generating DEGRADED fallback",
                card.id,
                source_execution.id,
                exc_info=True,
            )
            stage_output = StageOutputBuilder.build(
                card=card,
                execution=source_execution,
                source_session_id=source_execution.session_id,
                final_output="本阶段已结束，但无法提取完整输出（构建失败）。",
                artifacts=(),
                previous_output_id=source_execution.input_stage_output_id,
            )
        await self._stage_output_repo.save(stage_output)
        return stage_output

    async def _create_execution_session(
        self,
        team: Team,
        card: WishCard,
        execution: CardExecution,
        agent_project_id: str,
        workspace_path: str,
        handoff: Handoff | None,
        input_stage_output: StageOutput | None = None,
        delegation_context: str = "",
    ):
        prompt_parts = self._build_card_context_parts(card, input_stage_output, handoff)
        if delegation_context.strip():
            prompt_parts.append(
                f"## Leader 补充指示\n{delegation_context.strip()}"
            )
        prompt_parts.append(
            "## 阶段完成要求\n"
            "完成工作后，请在最终回复中简洁说明：本阶段结论、已完成、"
            "关键决策、产物、验证、待处理事项和下一阶段建议。"
        )

        session_cmd = CreateSessionCommand(
            model=os.getenv("DEFAULT_MODEL", "default"),
            project_id=agent_project_id,
            project_dir=workspace_path,
            name=f"[{team.name}] {card.title}",
            card_execution_id=execution.id,
            agent_slot_id=execution.agent_slot_id,
        )
        session = await self._session_service.create_session(session_cmd)
        if self._connection_manager is not None:
            await self._connection_manager.broadcast_global({
                "event": "team_session_created",
                "team_id": team.id,
                "project_id": agent_project_id,
                "session_id": session.session_id,
            })
        return session, "\n\n".join(prompt_parts)

    async def _dispatch_execution_query_with_failsafe(
        self, session_id: str, prompt: str, card_id: str, execution_id: str
    ) -> None:
        try:
            await dispatch_execution_query(self._session_service_factory, session_id, prompt)
        except Exception:
            logger.error(
                "[session=%s] dispatch failed for execution %s, marking FAILED",
                session_id,
                execution_id,
                exc_info=True,
            )
            if self._fail_execution_fn is not None:
                await self._fail_execution_fn(card_id, execution_id, session_id)

    async def _find_last_completed_execution(self, card: WishCard) -> CardExecution | None:
        executions = await self._execution_repo.find_by_card_id(card.id)
        for ex in reversed(executions):
            if ex.status == CardExecutionStatus.COMPLETED:
                return ex
        return None
