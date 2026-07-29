from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Awaitable, Callable

from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.run_query_command import RunQueryCommand
from application.team_board.team_workspace_helpers import (
    ensure_agent_project,
    prepare_execution_workspace,
)
from domain.shared.async_utils import safe_create_task
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
    ) -> None:
        self._team_repo = team_repo
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._workspace = workspace_gateway
        self._session_service = session_service
        self._session_service_factory = session_service_factory
        self._project_repo = project_repo
        self._connection_manager = connection_manager

    async def reconcile_non_terminal_executions(self) -> list[str]:
        non_terminal = await self._execution_repo.find_non_terminal()
        reconciled: list[str] = []
        for execution in non_terminal:
            try:
                await self._reconcile_one(execution)
                reconciled.append(execution.id)
            except Exception:
                logger.exception("reconciliation failed for execution %s", execution.id)
        return reconciled

    async def _reconcile_one(self, execution: CardExecution) -> None:
        if execution.session_id is not None:
            await self._reconcile_stuck_execution(execution)
            return
        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            logger.warning("reconcile: card %s not found for execution %s, skipping", execution.card_id, execution.id)
            return
        team = await self._team_repo.find_by_id(card.team_id)
        if team is None:
            logger.warning("reconcile: team %s not found for card %s, skipping", card.team_id, card.id)
            return
        target_slot = team.find_agent_slot(execution.agent_slot_id)
        if target_slot is None:
            execution.fail("Target slot no longer exists")
            await self._execution_repo.save(execution)
            return

        try:
            workspace_path = await prepare_execution_workspace(
                team, target_slot, execution.id, self._workspace, self._team_repo
            )
        except TeamDomainError as error:
            failure_reason = str(error)
            card.fail_execution(execution.id, failure_reason)
            execution.fail(failure_reason)
            await self._card_repo.save(card)
            await self._execution_repo.save(execution)
            return

        card.start_execution(execution.id)
        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        agent_project = await ensure_agent_project(team.name, target_slot, self._project_repo)
        session, prompt = await self._create_execution_session(
            team=team, card=card, execution=execution,
            agent_project_id=agent_project.id,
            workspace_path=workspace_path,
        )
        execution.session_id = session.session_id
        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        safe_create_task(self._dispatch_execution_query(
            session.session_id, prompt
        ))

    async def _reconcile_stuck_execution(self, execution: CardExecution) -> None:
        try:
            session = await self._session_service.get_session(execution.session_id)
        except Exception:
            logger.warning(
                "reconcile: session %s not found for execution %s, failing execution",
                execution.session_id, execution.id,
            )
            card = await self._card_repo.find_by_id(execution.card_id)
            if card is None:
                return
            card.fail_execution(execution.id, "Session not found during reconciliation")
            await self._card_repo.save(card)
            await self._execution_repo.save(execution)
            return

        if session.is_running:
            return
        if (
            session.updated_time is not None
            and datetime.now() - session.updated_time < self._terminal_session_sync_grace
        ):
            logger.debug(
                "reconcile: deferring execution %s because session %s "
                "recently became terminal",
                execution.id,
                execution.session_id,
            )
            return

        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            return
        card.fail_execution(execution.id, "Execution stuck: session ended without terminal card sync")
        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        logger.info(
            "reconcile: failed stuck execution %s (session=%s)",
            execution.id, execution.session_id,
        )

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

    async def _dispatch_execution_query(self, session_id: str, prompt: str) -> None:
        service = await self._session_service_factory()
        try:
            await service.submit_query(RunQueryCommand(session_id=session_id, prompt=prompt))
            await service.commit()
        finally:
            await service.close()
