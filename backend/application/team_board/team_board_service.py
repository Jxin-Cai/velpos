"""Thin facade that delegates to focused services.

All callers (routers, schedulers, tests) can continue using this class
unchanged. Future work will migrate callers to the specific services directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.team_board.card_execution_service import (
    _format_handoff_artifact_links as format_handoff_artifact_links,
)

__all__ = ["TeamBoardApplicationService", "format_handoff_artifact_links"]

if TYPE_CHECKING:
    from application.team_board.board_query_service import BoardQueryService
    from application.team_board.card_execution_service import CardExecutionService
    from application.team_board.commands import (
        ArchiveWishCardCommand,
        CreateTeamCommand,
        CreateWishCardCommand,
        DeleteWishCardCommand,
        MoveWishCardCommand,
        RetryExecutionCommand,
    )
    from application.team_board.execution_reconciliation_service import ExecutionReconciliationService
    from application.team_board.team_lifecycle_service import TeamLifecycleService
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.team import Team
    from domain.team.model.wish_card import WishCard


class TeamBoardApplicationService:
    """Facade: delegates to focused services."""

    def __init__(
        self,
        lifecycle: TeamLifecycleService,
        card_execution: CardExecutionService,
        query: BoardQueryService,
        reconciliation: ExecutionReconciliationService,
    ) -> None:
        self._lifecycle = lifecycle
        self._card_execution = card_execution
        self._query = query
        self._reconciliation = reconciliation

    # ── Team Lifecycle ────────────────────────────────────────

    async def create_team(self, cmd: CreateTeamCommand) -> Team:
        return await self._lifecycle.create_team(cmd)

    async def list_teams(self, project_id: str) -> list[Team]:
        return await self._lifecycle.list_teams(project_id)

    # ── Card & Execution ──────────────────────────────────────

    async def create_card(self, cmd: CreateWishCardCommand) -> WishCard:
        return await self._card_execution.create_card(cmd)

    async def archive_card(self, cmd: ArchiveWishCardCommand) -> WishCard:
        return await self._card_execution.archive_card(cmd)

    async def delete_archived_card(self, cmd: DeleteWishCardCommand) -> None:
        return await self._card_execution.delete_archived_card(cmd)

    async def move_card(self, cmd: MoveWishCardCommand) -> CardExecution:
        return await self._card_execution.move_card(cmd)

    async def retry_execution(self, cmd: RetryExecutionCommand) -> CardExecution:
        return await self._card_execution.retry_execution(cmd)

    # ── Board Queries ─────────────────────────────────────────

    async def get_board(self, team_id: str) -> tuple[Team, list[WishCard]]:
        return await self._query.get_board(team_id)

    async def get_execution(self, execution_id: str) -> CardExecution:
        return await self._query.get_execution(execution_id)

    async def get_card_history(self, execution_id: str) -> list[dict[str, object]]:
        return await self._query.get_card_history(execution_id)

    async def get_latest_stage_summary(self, card_id: str) -> str:
        return await self._query.get_latest_stage_summary(card_id)

    async def get_handoff_readiness(self, execution: CardExecution | None) -> str:
        return await self._query.get_handoff_readiness(execution)

    async def execution_needs_user_action(self, execution: CardExecution | None) -> bool:
        return await self._query.execution_needs_user_action(execution)

    # ── Reconciliation ────────────────────────────────────────

    async def reconcile_non_terminal_executions(self) -> list[str]:
        return await self._reconciliation.reconcile_non_terminal_executions()
