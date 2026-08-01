from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Awaitable, Callable

from application.session.command.create_session_command import CreateSessionCommand
from infr.client.claude_settings_env import resolve_default_model
from application.team_board.execution_dispatch import dispatch_execution_query
from application.team_board.team_workspace_helpers import (
    ensure_agent_project,
    prepare_execution_workspace,
)
from domain.session.model.message_type import MessageType
from domain.shared.async_utils import safe_create_task
from domain.shared.business_exception import BusinessException
from domain.team.model.status import ExecutionFailureCategory, ExecutionFailurePhase
from domain.team.model.team_domain_error import TeamDomainError

if TYPE_CHECKING:
    from application.session.session_application_service import SessionApplicationService
    from domain.project.repository.project_repository import ProjectRepository
    from domain.session.acl.connection_manager import ConnectionManager
    from domain.team.acl.workspace_gateway import WorkspaceGateway
    from domain.team.model.card_execution import CardExecution
    from domain.team.repository.card_execution_repository import CardExecutionRepository
    from domain.team.repository.team_repository import TeamRepository
    from domain.team.repository.wish_card_repository import WishCardRepository

logger = logging.getLogger(__name__)


class ExecutionReconciliationService:
    _terminal_session_sync_grace = timedelta(minutes=2)

    def __init__(
        self,
        team_repo: TeamRepository,
        card_repo: WishCardRepository,
        execution_repo: CardExecutionRepository,
        workspace_gateway: WorkspaceGateway,
        session_service: SessionApplicationService,
        session_service_factory: Callable[[], Awaitable[SessionApplicationService]],
        project_repo: ProjectRepository,
        connection_manager: ConnectionManager | None = None,
        terminal_session_sync_fn: Callable[..., Awaitable[None]] | None = None,
        flow_engine=None,
    ) -> None:
        self._team_repo = team_repo
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._workspace = workspace_gateway
        self._session_service = session_service
        self._session_service_factory = session_service_factory
        self._project_repo = project_repo
        self._connection_manager = connection_manager
        self._terminal_session_sync_fn = terminal_session_sync_fn
        self._flow_engine = flow_engine

    async def reconcile_non_terminal_executions(
        self,
        *,
        ignore_terminal_session_grace: bool = False,
    ) -> list[str]:
        non_terminal = await self._execution_repo.find_non_terminal()
        reconciled: list[str] = []
        for execution in non_terminal:
            try:
                changed = await self._reconcile_one(
                    execution,
                    ignore_terminal_session_grace=ignore_terminal_session_grace,
                )
                if changed:
                    reconciled.append(execution.id)
            except Exception:
                logger.exception("reconciliation failed for execution %s", execution.id)
        flow_engine = getattr(self, "_flow_engine", None)
        if flow_engine is not None:
            try:
                reconciled.extend(await flow_engine.reconcile_active_plans())
            except Exception:
                logger.exception("flow plan reconciliation failed")
        return reconciled

    async def _reconcile_one(
        self,
        execution: CardExecution,
        *,
        ignore_terminal_session_grace: bool = False,
    ) -> bool:
        # Check for timeout first
        if await self._check_timeout(execution):
            return True
        if execution.session_id is not None:
            return await self._reconcile_stuck_execution(
                execution,
                ignore_terminal_session_grace=ignore_terminal_session_grace,
            )
        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            execution.fail(
                "Wish card not found during reconciliation",
                ExecutionFailureCategory.RECONCILIATION,
                ExecutionFailurePhase.RECONCILIATION,
                False,
            )
            await self._execution_repo.save(execution)
            logger.warning(
                "reconcile: failed execution %s because card %s was not found",
                execution.id,
                execution.card_id,
            )
            return True
        team = await self._team_repo.find_by_id(card.team_id)
        if team is None:
            card.fail_execution(
                execution.id,
                "Team not found during reconciliation",
                ExecutionFailureCategory.RECONCILIATION,
                ExecutionFailurePhase.RECONCILIATION,
                False,
            )
            await self._card_repo.save(card)
            logger.warning(
                "reconcile: failed execution %s because team %s was not found",
                execution.id,
                card.team_id,
            )
            return True
        target_slot = team.find_agent_slot(execution.agent_slot_id)
        if target_slot is None:
            card.fail_execution(
                execution.id,
                "Target slot no longer exists",
                ExecutionFailureCategory.AGENT_ERROR,
                ExecutionFailurePhase.ORCHESTRATION,
                False,
            )
            await self._card_repo.save(card)
            return True

        try:
            workspace_path = await prepare_execution_workspace(
                team, target_slot, execution.id, self._workspace, self._team_repo
            )
        except TeamDomainError as error:
            failure_reason = str(error)
            card.fail_execution(
                execution.id,
                failure_reason,
                ExecutionFailureCategory.WORKSPACE_UNAVAILABLE,
                ExecutionFailurePhase.PREPARATION,
                True,
            )
            await self._card_repo.save(card)
            return True

        card.start_execution(execution.id)
        await self._card_repo.save(card)
        active_execution = card.active_execution
        if active_execution is None:
            raise TeamDomainError(f"active execution not found after start: {execution.id}")
        agent_project = await ensure_agent_project(
            team.name,
            target_slot,
            self._project_repo,
            team_project_id=team.project_id,
        )
        session, prompt = await self._create_execution_session(
            team=team, card=card, execution=active_execution,
            agent_project_id=agent_project.id,
            workspace_path=workspace_path,
        )
        active_execution.session_id = session.session_id
        await self._card_repo.save(card)
        safe_create_task(dispatch_execution_query(
            self._session_service_factory, session.session_id, prompt
        ))
        return True

    async def _reconcile_stuck_execution(
        self,
        execution: CardExecution,
        *,
        ignore_terminal_session_grace: bool = False,
    ) -> bool:
        try:
            session = await self._session_service.get_session(execution.session_id)
        except BusinessException:
            logger.warning(
                "reconcile: session %s not found for execution %s, failing execution",
                execution.session_id, execution.id,
            )
            card = await self._card_repo.find_by_id(execution.card_id)
            if card is None:
                execution.fail(
                    "Wish card not found during reconciliation",
                    ExecutionFailureCategory.RECONCILIATION,
                    ExecutionFailurePhase.RECONCILIATION,
                    False,
                )
                await self._execution_repo.save(execution)
                return True
            card.fail_execution(
                execution.id,
                "Session not found during reconciliation",
                ExecutionFailureCategory.SESSION_LOST,
                ExecutionFailurePhase.RECONCILIATION,
                True,
            )
            await self._card_repo.save(card)
            return True

        if session.is_running or getattr(session, "is_compacting", False):
            return False
        if (
            not ignore_terminal_session_grace
            and session.updated_time is not None
            and datetime.now() - session.updated_time < self._terminal_session_sync_grace
        ):
            logger.debug(
                "reconcile: deferring execution %s because session %s "
                "recently became terminal",
                execution.id,
                execution.session_id,
            )
            return False

        terminal_result = next(
            (
                message
                for message in reversed(getattr(session, "messages", ()))
                if message.message_type is MessageType.RESULT
            ),
            None,
        )
        terminal_session_sync_fn = getattr(self, "_terminal_session_sync_fn", None)
        if terminal_session_sync_fn is not None:
            succeeded = (
                terminal_result is not None
                and terminal_result.content.get("is_error") is not True
            )
            if succeeded:
                reason = ""
            elif terminal_result is not None:
                reason = str(
                    terminal_result.content.get("text")
                    or terminal_result.content.get("error")
                    or "Agent execution failed"
                )
            else:
                session_status = getattr(session.status, "value", str(session.status))
                reason = (
                    "Session ended without a terminal result "
                    f"(status={session_status})"
                )
            await terminal_session_sync_fn(
                session,
                succeeded=succeeded,
                reason=reason,
            )
            logger.info(
                "reconcile: replayed terminal sync for execution %s "
                "(session=%s, succeeded=%s)",
                execution.id,
                execution.session_id,
                succeeded,
            )
            return True

        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            execution.fail(
                "Wish card not found during reconciliation",
                ExecutionFailureCategory.RECONCILIATION,
            )
            await self._execution_repo.save(execution)
            return True

        active_exec = card.active_execution
        if active_exec is None or active_exec.id != execution.id:
            logger.info(
                "reconcile: execution %s is no longer active on card %s; skipping stuck-execution fix",
                execution.id,
                execution.card_id,
            )
            return False

        card.fail_execution(
            execution.id,
            "Execution stuck: session ended without terminal card sync",
            ExecutionFailureCategory.RECONCILIATION,
            ExecutionFailurePhase.RECONCILIATION,
            True,
        )  # active_exec.status → FAILED

        saved = await self._execution_repo.save_terminal_if_non_terminal(active_exec)
        if not saved:
            logger.info(
                "reconcile: stuck-execution race lost for %s "
                "(already transitioned by sync callback); skipping",
                execution.id,
            )
            return False

        await self._card_repo.save_state(card)
        logger.info(
            "reconcile: failed stuck execution %s (session=%s)",
            execution.id, execution.session_id,
        )
        return True

    async def _check_timeout(self, execution: CardExecution) -> bool:
        """Check if the execution has exceeded its timeout. Returns True if timed out."""
        from datetime import datetime, timezone

        if execution.timeout_at is None:
            return False
        if datetime.now(timezone.utc) <= execution.timeout_at:
            return False

        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            # Orphaned execution: no card to guard, no concurrent sync possible.
            execution.fail(
                "Execution timed out",
                ExecutionFailureCategory.TIMEOUT,
                ExecutionFailurePhase.EXECUTION,
                True,
            )
            await self._execution_repo.save(execution)
            return True

        # Grab a reference to the active execution BEFORE domain mutation so we
        # can pass the mutated object to the atomic conditional save below.
        active_exec = card.active_execution
        if active_exec is None or active_exec.id != execution.id:
            logger.info(
                "reconcile: execution %s is no longer active on card %s; skipping timeout",
                execution.id,
                execution.card_id,
            )
            return False

        card.fail_execution(
            execution.id,
            "Execution timed out",
            ExecutionFailureCategory.TIMEOUT,
            ExecutionFailurePhase.EXECUTION,
            True,
        )  # active_exec.status → FAILED

        # Atomic conditional write — wins only if the DB row is still non-terminal.
        saved = await self._execution_repo.save_terminal_if_non_terminal(active_exec)
        if not saved:
            logger.info(
                "reconcile: timeout race lost for execution %s "
                "(already transitioned by sync callback); skipping",
                execution.id,
            )
            return False

        await self._card_repo.save_state(card)
        logger.info(
            "reconcile: timed out execution %s (timeout_at=%s)",
            execution.id,
            execution.timeout_at.isoformat(),
        )
        return True

    async def _create_execution_session(
        self,
        team,
        card,
        execution: CardExecution,
        agent_project_id: str,
        workspace_path: str,
    ):
        prompt_parts: list[str] = [
            f"## 愿望卡\n标题: {card.title}\n描述: {card.description}",
            "## 阶段完成要求\n"
            "完成工作后，请在最终回复中简洁说明：本阶段结论、已完成、"
            "关键决策、产物、验证、待处理事项和下一阶段建议。",
        ]
        session_cmd = CreateSessionCommand(
            model=resolve_default_model(),
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
