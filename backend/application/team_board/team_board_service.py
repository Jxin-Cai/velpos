from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from html import escape
from typing import TYPE_CHECKING, Awaitable, Callable

from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.run_query_command import RunQueryCommand
from domain.shared.async_utils import KeyedLockPool, safe_create_task
from domain.shared.business_exception import BusinessException
from domain.team.acl.workspace_gateway import WorkspaceUnavailableError
from domain.team.model.status import CardExecutionStatus, HandoffStatus
from domain.team.model.team_domain_error import TeamDomainError

if TYPE_CHECKING:
    from application.session.session_application_service import SessionApplicationService
    from application.team_board.commands import (
        CreateTeamCommand,
        CreateWishCardCommand,
        ArchiveWishCardCommand,
        DeleteWishCardCommand,
        MoveWishCardCommand,
        RetryExecutionCommand,
    )
    from domain.team.acl.session_context_collector import SessionContext, SessionContextCollector
    from domain.team.acl.workspace_gateway import WorkspaceGateway
    from domain.team.model.agent_slot import AgentSlot
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.handoff import Handoff
    from domain.team.model.team import Team
    from domain.team.model.wish_card import WishCard
    from domain.team.repository.card_execution_repository import CardExecutionRepository
    from domain.team.repository.handoff_repository import HandoffRepository
    from domain.team.repository.team_repository import TeamRepository
    from domain.team.repository.wish_card_repository import WishCardRepository
    from domain.session.repository.session_repository import SessionRepository
    from domain.project.acl.plugin_manager import PluginManager
    from domain.session.acl.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


def format_handoff_artifact_links(handoff: Handoff) -> str:
    """Render artifacts as safe links handled by the Velpos message viewer.

    Browsers intentionally block ``file://`` links from an HTTP page.  The
    message viewer already owns a guarded ``file-path-link`` action that opens
    a local path through the backend, so handoff prompts use that contract too.
    """
    return "\n".join(
        (
            '- <a class="file-path-link" data-file-path="'
            f'{escape(artifact.path, quote=True)}" href="#" title="Click to open">'
            f"{escape(artifact.name)}</a> — `{artifact.path}`"
        )
        for artifact in handoff.artifacts
    )


class TeamBoardApplicationService:
    _card_lock_pool = KeyedLockPool(max_size=1_000)
    _terminal_session_sync_grace = timedelta(minutes=2)

    def __init__(
        self,
        team_repo: TeamRepository,
        card_repo: WishCardRepository,
        execution_repo: CardExecutionRepository,
        handoff_repo: HandoffRepository,
        workspace_gateway: WorkspaceGateway,
        session_service: SessionApplicationService,
        context_collector: SessionContextCollector,
        session_service_factory: Callable[[], Awaitable[SessionApplicationService]],
        plugin_manager: PluginManager | None = None,
        connection_manager: ConnectionManager | None = None,
        session_repo: SessionRepository | None = None,
    ) -> None:
        self._team_repo = team_repo
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._handoff_repo = handoff_repo
        self._workspace = workspace_gateway
        self._session_service = session_service
        self._context_collector = context_collector
        self._session_service_factory = session_service_factory
        self._plugin_manager = plugin_manager
        self._connection_manager = connection_manager
        self._session_repo = session_repo

    async def create_team(self, cmd: CreateTeamCommand) -> Team:
        from domain.team.model.team import Team

        team = Team.create(project_id=cmd.project_id, name=cmd.name)
        workspace_refs: list[str] = []
        try:
            for index, slot_cfg in enumerate(cmd.slots, start=1):
                workspace_ref = self._workspace.create_independent_workspace(
                    team_root=cmd.root_path,
                    team_slug=cmd.name,
                    slot_slug=slot_cfg.slug or slot_cfg.display_name or f"agent-{index}",
                    project_root=cmd.root_path,
                    agent_profile_ref=slot_cfg.agent_profile_id,
                )
                workspace_refs.append(workspace_ref)
                await self._load_agent_profile(slot_cfg.agent_profile_id, workspace_ref)
                team.add_agent_slot(
                    name=slot_cfg.display_name,
                    role=slot_cfg.agent_profile_id,
                    workspace_ref=workspace_ref,
                )
            await self._team_repo.save(team)
        except Exception:
            logger.exception("workspace preparation failed for team %s", team.id)
            for workspace_ref in reversed(workspace_refs):
                self._workspace.remove_workspace(workspace_ref)
            raise
        return team

    async def _load_agent_profile(self, agent_profile_id: str, workspace_ref: str) -> None:
        """Install the selected profile's project-scoped plugins before use."""
        if self._plugin_manager is None:
            return
        from infr.agent.catalog import get_agent_by_id

        profile = get_agent_by_id(agent_profile_id)
        if profile is None:
            return
        marketplace_config = profile.get("marketplace_plugins", {})
        for marketplace in marketplace_config.get("marketplaces", []):
            name = marketplace.get("name", "")
            source = marketplace.get("source", "")
            if not name or not source:
                continue
            try:
                if not self._plugin_manager.is_marketplace_added(name):
                    await self._plugin_manager.add_marketplace(source)
                else:
                    await self._plugin_manager.update_marketplace(name)
            except Exception:
                logger.warning(
                    "failed to prepare agent marketplace %s for %s",
                    name,
                    agent_profile_id,
                    exc_info=True,
                )
        plugins = [
            *(plugin.get("path", "") for plugin in profile.get("plugins", []) if isinstance(plugin, dict)),
            *(plugin for plugin in marketplace_config.get("plugins", []) if isinstance(plugin, str)),
        ]
        for plugin in filter(None, plugins):
            try:
                await self._plugin_manager.install_plugin(plugin, workspace_ref)
            except Exception:
                logger.warning(
                    "failed to install agent plugin %s for %s",
                    plugin,
                    agent_profile_id,
                    exc_info=True,
                )

    async def list_teams(self, project_id: str) -> list[Team]:
        team = await self._team_repo.find_by_project_id(project_id)
        return [team] if team is not None else []

    async def get_execution(self, execution_id: str) -> CardExecution:
        execution = await self._execution_repo.find_by_id(execution_id)
        if execution is None:
            raise TeamDomainError("execution not found")
        return execution

    async def get_card_history(self, execution_id: str) -> list[dict[str, object]]:
        """Return the complete agent/session route for the card owning an execution."""
        execution = await self.get_execution(execution_id)
        card = await self._card_repo.find_by_id(execution.card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {execution.card_id} not found")
        team = await self._team_repo.find_by_id(card.team_id)
        if team is None:
            raise TeamDomainError(f"Team {card.team_id} not found")
        slot_names = {slot.id: slot.name for slot in team.agent_slots}

        handoffs = await self._handoff_repo.find_by_card_id(card.id)
        # A handoff with source_execution_id=X was received by the execution
        # immediately following X in the card's execution list.
        handoff_by_source = {h.source_execution_id: h for h in handoffs}

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
                    # A session may have been deleted independently; the card
                    # execution history remains useful with its Velpos ID.
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
            }
            # The handoff received by this execution was created with the
            # previous execution as source.
            previous_id = executions[idx - 1].id if idx > 0 else None
            handoff = handoff_by_source.get(previous_id) if previous_id else None
            if handoff is not None:
                entry["handoff"] = {
                    "id": handoff.id,
                    "summary": handoff.summary,
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

    async def execution_needs_user_action(self, execution: CardExecution | None) -> bool:
        if execution is None or execution.status is not CardExecutionStatus.RUNNING or not execution.session_id:
            return False
        session = await self._session_service.get_session(execution.session_id)
        return bool(session.pending_request_context)

    async def get_board(self, team_id: str) -> tuple[Team, list[WishCard]]:
        from domain.team.model.wish_card import WishCard

        team = await self._team_repo.find_by_id(team_id)
        if team is None:
            raise TeamDomainError(f"Team {team_id} not found")
        cards = await self._card_repo.find_by_team_id(team_id)
        return team, cards

    async def _broadcast_board_event(self, event: str, team_id: str, card_id: str | None = None) -> None:
        if self._connection_manager is None:
            return
        payload: dict[str, object] = {
            "event": event,
            "team_id": team_id,
        }
        if card_id is not None:
            payload["card_id"] = card_id
        await self._connection_manager.broadcast_global(payload)

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

        # Explicit dependency-ordered cleanup. The DB-level FK cascade cannot be
        # trusted: migration 0029 only creates the team tables when absent, so a
        # database provisioned before the current ondelete rules may still carry
        # RESTRICT/NO ACTION constraints that would make a bare card delete fail.
        # Detach sessions (history is preserved), drop handoffs + artifacts and
        # executions, then remove the card — all within the request's unit of
        # work, so a failure at any step rolls the whole delete back.
        executions = await self._execution_repo.find_by_card_id(card.id)
        if executions and self._session_repo is not None:
            await self._session_repo.clear_card_execution_references(
                [execution.id for execution in executions]
            )
        await self._handoff_repo.remove_by_card_id(card.id)
        await self._execution_repo.remove_by_card_id(card.id)
        await self._card_repo.remove(card)
        await self._broadcast_board_event("board_card_deleted", cmd.team_id, card.id)

    async def _require_team_card(self, team_id: str, card_id: str) -> WishCard:
        card = await self._card_repo.find_by_id(card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {card_id} not found")
        if card.team_id != team_id:
            raise TeamDomainError(f"Wish card {card_id} does not belong to team {team_id}")
        return card

    async def move_card(self, cmd: MoveWishCardCommand) -> CardExecution:
        card_lock = await self._card_lock_pool.acquire(cmd.card_id)
        try:
            async with card_lock:
                return await self._move_card_locked(cmd)
        finally:
            await self._card_lock_pool.unref(cmd.card_id)

    async def _move_card_locked(self, cmd: MoveWishCardCommand) -> CardExecution:
        from domain.team.model.card_execution import CardExecution
        from domain.team.model.team_domain_error import TeamDomainError

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

        previous_execution = await self._find_last_completed_execution(card)

        execution = card.assign_to(target_slot.id, idempotency_key)
        workspace_path = await self._prepare_execution_workspace(
            team,
            target_slot,
            execution.id,
        )

        if previous_execution is not None:
            handoff = await self._prepare_handoff(
                previous_execution,
                execution,
                target_slot,
                card,
            )
        else:
            handoff = None

        card.start_execution(execution.id)
        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        session, prompt = await self._create_execution_session(
            team=team,
            card=card,
            execution=execution,
            workspace_path=workspace_path,
            handoff=handoff,
        )
        execution.session_id = session.session_id

        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        safe_create_task(self._dispatch_execution_query_with_failsafe(
            session.session_id, prompt, card.id, execution.id
        ))
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return execution

    async def retry_execution(self, cmd: RetryExecutionCommand) -> CardExecution:
        from domain.team.model.team_domain_error import TeamDomainError

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

        new_execution = card.retry_on(target_slot.id)
        workspace_path = await self._prepare_execution_workspace(
            team,
            target_slot,
            new_execution.id,
        )

        card.start_execution(new_execution.id)
        await self._card_repo.save(card)
        await self._execution_repo.save(new_execution)
        session, prompt = await self._create_execution_session(
            team=team,
            card=card,
            execution=new_execution,
            workspace_path=workspace_path,
            handoff=None,
        )
        new_execution.session_id = session.session_id

        await self._card_repo.save(card)
        await self._execution_repo.save(new_execution)
        safe_create_task(self._dispatch_execution_query_with_failsafe(
            session.session_id, prompt, card.id, new_execution.id
        ))
        await self._broadcast_board_event("board_card_updated", card.team_id, card.id)
        return new_execution

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
        team = await self._team_repo.find_by_id(card.team_id)
        target_slot = team.find_agent_slot(execution.agent_slot_id)
        if target_slot is None:
            execution.fail("Target slot no longer exists")
            await self._execution_repo.save(execution)
            return

        try:
            workspace_path = await self._prepare_execution_workspace(
                team,
                target_slot,
                execution.id,
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
        session, prompt = await self._create_execution_session(
            team=team, card=card, execution=execution,
            workspace_path=workspace_path, handoff=None,
        )
        execution.session_id = session.session_id
        await self._card_repo.save(card)
        await self._execution_repo.save(execution)
        safe_create_task(self._dispatch_execution_query_with_failsafe(
            session.session_id, prompt, card.id, execution.id
        ))

    async def _prepare_execution_workspace(
        self,
        team: Team,
        target_slot: AgentSlot,
        execution_id: str,
    ) -> str:
        try:
            return self._workspace.create_execution_workspace(
                target_slot.workspace_ref,
                execution_id,
            )
        except WorkspaceUnavailableError as error:
            target_slot.mark_unstable()
            await self._team_repo.save(team)
            logger.warning(
                "agent workspace unavailable for team %s slot %s",
                team.id,
                target_slot.id,
            )
            raise TeamDomainError(
                "Target agent workspace is unavailable; restore its workspace "
                "directory or recreate the team"
            ) from error

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

    async def _prepare_handoff(
        self,
        source_execution: CardExecution,
        target_execution: CardExecution,
        target_slot,
        card: WishCard,
    ) -> Handoff:
        from domain.team.model.handoff import Handoff

        context = await self._context_collector.collect(
            session_id=source_execution.session_id or "",
        )
        handoff = Handoff.create(
            team_id=card.team_id,
            card_id=card.id,
            source_execution_id=source_execution.id,
            source_agent_slot_id=source_execution.agent_slot_id,
            target_agent_slot_id=target_slot.id,
            summary=self._format_handoff_summary(context),
        )
        for artifact in context.artifacts:
            handoff.add_artifact(
                name=artifact.path.rsplit("/", 1)[-1],
                path=artifact.path,
                media_type=artifact.artifact_type,
            )
        handoff.accept()
        await self._handoff_repo.save(handoff)
        return handoff

    @staticmethod
    def _format_handoff_summary(context: SessionContext) -> str:
        session_lines = [f"- Velpos 会话 ID: `{context.source_session_id}`"]
        if context.sdk_session_id:
            session_lines.append(f"- Claude Code 会话 ID: `{context.sdk_session_id}`")
        else:
            session_lines.append("- Claude Code 会话 ID: 未记录")
        conversation = context.summary or "前序会话没有可提取的文本内容。"
        return "## 前序会话\n" + "\n".join(session_lines) + f"\n\n## 执行记录\n{conversation}"

    async def _create_execution_session(
        self,
        team: Team,
        card: WishCard,
        execution: CardExecution,
        workspace_path: str,
        handoff: Handoff | None,
    ):
        prompt_parts: list[str] = []
        if handoff and handoff.status == HandoffStatus.ACCEPTED:
            prompt_parts.append(f"## 上一执行上下文\n{handoff.summary}")
            if handoff.artifacts:
                artifact_lines = format_handoff_artifact_links(handoff)
                prompt_parts.append(f"## 产物\n{artifact_lines}")
        prompt_parts.append(f"## 愿望卡\n标题: {card.title}\n描述: {card.description}")

        session_cmd = CreateSessionCommand(
            model=os.getenv("DEFAULT_MODEL", "default"),
            project_id=team.project_id,
            project_dir=workspace_path,
            name=f"[{team.name}] {card.title}",
            card_execution_id=execution.id,
            agent_slot_id=execution.agent_slot_id,
        )
        session = await self._session_service.create_session(session_cmd)
        return session, "\n\n".join(prompt_parts)

    async def _dispatch_execution_query(self, session_id: str, prompt: str) -> None:
        service = await self._session_service_factory()
        try:
            await service.submit_query(RunQueryCommand(session_id=session_id, prompt=prompt))
            await service.commit()
        finally:
            await service.close()

    async def _dispatch_execution_query_with_failsafe(
        self, session_id: str, prompt: str, card_id: str, execution_id: str
    ) -> None:
        try:
            await self._dispatch_execution_query(session_id, prompt)
        except Exception:
            logger.error(
                "[session=%s] dispatch failed for execution %s, marking FAILED",
                session_id,
                execution_id,
                exc_info=True,
            )
            await self._fail_execution_on_dispatch_error(card_id, execution_id, session_id)

    async def _fail_execution_on_dispatch_error(
        self, card_id: str, execution_id: str, session_id: str
    ) -> None:
        from infr.config.database import async_session_factory
        from infr.repository.wish_card_repository_impl import WishCardRepositoryImpl
        from infr.repository.card_execution_repository_impl import CardExecutionRepositoryImpl

        try:
            async with async_session_factory() as db_session:
                card_repo = WishCardRepositoryImpl(db_session)
                execution_repo = CardExecutionRepositoryImpl(db_session)
                card = await card_repo.find_by_id(card_id)
                execution = await execution_repo.find_by_id(execution_id)
                if card is None or execution is None:
                    logger.error(
                        "[session=%s] cannot fail execution %s: card or execution not found",
                        session_id, execution_id,
                    )
                    return
                if execution.is_terminal:
                    return
                card.fail_execution(execution_id, "Dispatch failed: could not start session query")
                await card_repo.save(card)
                await db_session.commit()
            if self._connection_manager is not None:
                latest = card.latest_execution
                await self._connection_manager.broadcast_global({
                    "event": "board_card_updated",
                    "team_id": card.team_id,
                    "card": {
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
                    },
                })
        except Exception:
            logger.error(
                "[session=%s] failed to mark execution %s as FAILED after dispatch error",
                session_id, execution_id,
                exc_info=True,
            )

    async def _find_last_completed_execution(self, card: WishCard) -> CardExecution | None:
        executions = await self._execution_repo.find_by_card_id(card.id)
        for ex in reversed(executions):
            if ex.status == CardExecutionStatus.COMPLETED:
                return ex
        return None
