"""Flow Engine Service — orchestrates auto-delegation flow after sub-agent events.

Handles two modes:
- WORKFLOW: backend auto-advances cards through a predefined pipeline
- DECISION: notifies Leader session after each step for next-step decision
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.team_board.commands import (
    AdvanceFlowCommand,
    MoveWishCardCommand,
    RegisterFlowPlanCommand,
)
from domain.team.model.flow_plan import FlowPlan
from domain.team.model.status import (
    ExecutionFailureCategory,
    FlowMode,
    FlowPlanStatus,
    FlowStepStatus,
    ExecutionTrigger,
)
from domain.team.model.team_domain_error import TeamDomainError
from domain.shared.async_utils import safe_create_task

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from application.team_board.leader_session_manager import LeaderSessionManager
    from domain.session.acl.connection_manager import ConnectionManager
    from domain.session.model.session import Session
    from domain.team.model.card_execution import CardExecution
    from domain.team.model.flow_plan import FlowStep
    from domain.team.model.wish_card import WishCard
    from domain.team.repository.card_execution_repository import CardExecutionRepository
    from domain.team.repository.flow_plan_repository import FlowPlanRepository
    from domain.team.repository.team_repository import TeamRepository
    from domain.team.repository.wish_card_repository import WishCardRepository
    from domain.team.model.stage_output import StageOutput
    from domain.team.repository.stage_output_repository import StageOutputRepository

logger = logging.getLogger(__name__)


class FlowEngineService:
    """Orchestrates auto-delegation flow after sub-agent completion events."""

    def __init__(
        self,
        flow_plan_repo: FlowPlanRepository,
        team_repo: TeamRepository,
        card_repo: WishCardRepository,
        execution_repo: CardExecutionRepository,
        stage_output_repo: StageOutputRepository,
        leader_session_manager: LeaderSessionManager,
        move_card_fn: Callable[[MoveWishCardCommand], Awaitable[CardExecution]] | None = None,
        connection_manager: ConnectionManager | None = None,
        commit_fn: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._flow_plan_repo = flow_plan_repo
        self._team_repo = team_repo
        self._card_repo = card_repo
        self._execution_repo = execution_repo
        self._stage_output_repo = stage_output_repo
        self._leader_session_manager = leader_session_manager
        self._move_card_fn = move_card_fn
        self._connection_manager = connection_manager
        self._commit_fn = commit_fn

    # ── Public use cases ──────────────────────────────────────

    async def register_flow_plan(self, cmd: RegisterFlowPlanCommand) -> FlowPlan:
        """Register a flow plan created by the Leader and start the first step."""
        team = await self._team_repo.find_by_id(cmd.team_id)
        if team is None:
            raise TeamDomainError(f"Team {cmd.team_id} not found")

        leader_slot = team.find_leader_slot()
        if leader_slot is None:
            raise TeamDomainError(f"Team {cmd.team_id} has no leader slot")

        card = await self._card_repo.find_by_id(cmd.card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {cmd.card_id} not found")
        if card.team_id != cmd.team_id:
            raise TeamDomainError(f"Wish card does not belong to team {cmd.team_id}")

        existing_plan = await self._flow_plan_repo.find_active_by_card_id(cmd.card_id)
        if existing_plan is not None:
            raise TeamDomainError(
                f"Card {cmd.card_id} already has an active flow plan"
            )

        # Validate all target slots exist and are not leader slots
        for slot_id in cmd.step_slot_ids:
            slot = team.find_agent_slot(slot_id)
            if slot is None:
                raise TeamDomainError(f"Slot {slot_id} not found in team")
            if slot.is_leader:
                raise TeamDomainError(
                    f"Cannot assign work to leader slot {slot_id} in a flow plan"
                )

        mode = FlowMode(cmd.mode)
        plan = FlowPlan.create(
            team_id=cmd.team_id,
            card_id=cmd.card_id,
            leader_slot_id=leader_slot.id,
            mode=mode,
            step_slot_ids=list(cmd.step_slot_ids),
            leader_session_id=team.leader_session_id,
        )

        # Complete the Leader's current execution so card can be reassigned
        if card.active_execution is not None:
            card.complete_execution(card.active_execution.id)
            await self._card_repo.save(card)

        await self._flow_plan_repo.save(plan)
        await self._broadcast_flow_event("flow_plan_created", plan)

        # Start the first step
        first_step = plan.next_pending_step
        if first_step is not None:
            await self._execute_step(plan, first_step, card)

        return plan

    async def advance_flow(self, cmd: AdvanceFlowCommand) -> FlowPlan:
        """Manually advance a card to the next slot (Leader decision mode)."""
        team = await self._team_repo.find_by_id(cmd.team_id)
        if team is None:
            raise TeamDomainError(f"Team {cmd.team_id} not found")
        if team.find_agent_slot(cmd.target_slot_id) is None:
            raise TeamDomainError(f"Slot {cmd.target_slot_id} not found in team")

        plan = await self._flow_plan_repo.find_active_by_card_id(cmd.card_id)
        if plan is None:
            raise TeamDomainError(f"No active flow plan for card {cmd.card_id}")
        if plan.mode != FlowMode.DECISION:
            raise TeamDomainError("Manual advance is only allowed in decision mode")

        card = await self._card_repo.find_by_id(cmd.card_id)
        if card is None:
            raise TeamDomainError(f"Wish card {cmd.card_id} not found")

        # Add a new step dynamically
        new_step = plan.add_step(cmd.target_slot_id)
        await self._flow_plan_repo.save(plan)
        await self._execute_step(plan, new_step, card, context=cmd.context)
        return plan

    async def complete_plan(self, plan_id: str, team_id: str) -> FlowPlan:
        """Mark a flow plan as completed (typically by Leader in decision mode)."""
        plan = await self._flow_plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TeamDomainError(f"Flow plan {plan_id} not found")
        if plan.team_id != team_id:
            raise TeamDomainError("Flow plan does not belong to this team")

        plan.skip_remaining_steps()
        plan.complete()
        await self._flow_plan_repo.save(plan)

        # Mark the card as completed
        card = await self._card_repo.find_by_id(plan.card_id)
        if card is not None and card.active_execution is not None:
            card.complete_execution(card.active_execution.id)
            await self._card_repo.save(card)

        await self._broadcast_flow_event("flow_plan_completed", plan)
        return plan

    async def cancel_plan(self, plan_id: str, team_id: str, reason: str = "") -> FlowPlan:
        """Cancel an active flow plan."""
        plan = await self._flow_plan_repo.find_by_id(plan_id)
        if plan is None:
            raise TeamDomainError(f"Flow plan {plan_id} not found")
        if plan.team_id != team_id:
            raise TeamDomainError("Flow plan does not belong to this team")

        plan.cancel()
        await self._flow_plan_repo.save(plan)
        await self._broadcast_flow_event("flow_plan_cancelled", plan)
        return plan

    # ── Event callbacks (called by CardExecutionSyncService) ──

    async def on_execution_completed(
        self,
        card_id: str,
        execution_id: str,
        session: Session,
    ) -> None:
        """Handle a sub-agent execution completing successfully."""
        step = await self._flow_plan_repo.find_step_by_execution_id(execution_id)
        if step is None:
            return  # Not part of a flow plan

        plan = await self._flow_plan_repo.find_by_id(step.flow_plan_id)
        if plan is None or plan.status != FlowPlanStatus.ACTIVE:
            return
        plan_step = plan.find_step_by_execution_id(execution_id)
        if plan_step is None or plan_step.status == FlowStepStatus.COMPLETED:
            return

        next_step = plan.advance_step(plan_step.id)
        await self._flow_plan_repo.save(plan)
        await self._broadcast_flow_event("flow_step_advanced", plan)

        if plan.mode == FlowMode.WORKFLOW:
            await self._handle_workflow_advance(plan, card_id, next_step, session)
        else:
            await self._handle_decision_notify(plan, card_id, session)

    async def on_execution_failed(
        self,
        card_id: str,
        execution_id: str,
        reason: str,
        category: ExecutionFailureCategory,
    ) -> None:
        """Handle a sub-agent execution failing."""
        step = await self._flow_plan_repo.find_step_by_execution_id(execution_id)
        if step is None:
            return  # Not part of a flow plan

        plan = await self._flow_plan_repo.find_by_id(step.flow_plan_id)
        if plan is None or plan.status != FlowPlanStatus.ACTIVE:
            return
        plan_step = plan.find_step_by_execution_id(execution_id)
        if plan_step is None or plan_step.status == FlowStepStatus.FAILED:
            return

        plan.fail_step(plan_step.id, reason)
        await self._flow_plan_repo.save(plan)
        await self._broadcast_flow_event("flow_plan_failed", plan)

        # Always notify Leader on failure regardless of mode
        notified = await self._notify_leader_failure(
            plan, plan_step, reason, category
        )
        if notified:
            plan_step.mark_leader_notified()
            await self._flow_plan_repo.save(plan)

    async def reconcile_active_plans(self) -> list[str]:
        """Repair flow transitions missed after a crash or callback failure."""
        reconciled: list[str] = []
        for plan in await self._flow_plan_repo.find_all_active():
            unnotified = next(
                (
                    item
                    for item in reversed(plan.steps)
                    if item.is_terminal and item.leader_notified_at is None
                ),
                None,
            )
            if plan.mode == FlowMode.DECISION and unnotified is not None:
                if await self._notify_recovered_step(plan, unnotified):
                    unnotified.mark_leader_notified()
                    await self._flow_plan_repo.save(plan)
                    reconciled.append(plan.id)
            step = plan.current_step
            if step is None:
                if plan.mode == FlowMode.WORKFLOW:
                    plan.complete()
                    await self._flow_plan_repo.save(plan)
                    reconciled.append(plan.id)
                continue
            if step.status == FlowStepStatus.PENDING:
                card = await self._card_repo.find_by_id(plan.card_id)
                if card is not None and card.can_be_assigned:
                    await self._execute_step(plan, step, card)
                    reconciled.append(plan.id)
                continue
            if not step.execution_id:
                continue
            execution = await self._execution_repo.find_by_id(step.execution_id)
            if execution is None or not execution.is_terminal:
                continue
            if execution.status.value == "completed":
                await self._advance_recovered_completion(plan, step)
            elif execution.status.value == "failed":
                await self.on_execution_failed(
                    plan.card_id,
                    execution.id,
                    execution.failure_reason or "Recovered terminal failure",
                    execution.failure_category or ExecutionFailureCategory.UNKNOWN,
                )
            else:
                plan.fail_step(step.id, "Execution was cancelled")
                await self._flow_plan_repo.save(plan)
            reconciled.append(plan.id)
        return reconciled

    async def _advance_recovered_completion(
        self,
        plan: FlowPlan,
        step: FlowStep,
    ) -> None:
        next_step = plan.advance_step(step.id)
        await self._flow_plan_repo.save(plan)
        if plan.mode == FlowMode.WORKFLOW:
            if next_step is None:
                plan.complete()
                await self._flow_plan_repo.save(plan)
                await self._broadcast_flow_event("flow_plan_completed", plan)
                return
            card = await self._card_repo.find_by_id(plan.card_id)
            if card is not None:
                await self._execute_step(plan, next_step, card)
            return
        if plan.leader_session_id:
            output = await self._stage_output_repo.find_latest_by_execution_id(
                step.execution_id or ""
            )
            summary = output.rendered_markdown if output is not None else "阶段已完成。"
            await self._leader_session_manager.append_message(
                plan.leader_session_id,
                "## 子 Agent 执行完成（恢复通知）\n\n"
                f"{summary[:4000]}\n\n请决策下一步流转。",
            )
            step.mark_leader_notified()
            await self._flow_plan_repo.save(plan)

    async def _notify_recovered_step(self, plan: FlowPlan, step: FlowStep) -> bool:
        if not plan.leader_session_id:
            return False
        if step.status == FlowStepStatus.FAILED:
            return await self._notify_leader_failure(
                plan,
                step,
                "Recovered failed flow step",
                ExecutionFailureCategory.RECONCILIATION,
            )
        output = (
            await self._stage_output_repo.find_latest_by_execution_id(
                step.execution_id or ""
            )
            if step.execution_id
            else None
        )
        summary = output.rendered_markdown if output is not None else "阶段已结束。"
        await self._leader_session_manager.append_message(
            plan.leader_session_id,
            "## 流转恢复通知\n\n"
            f"步骤 {step.sequence} 状态：{step.status.value}\n\n"
            f"{summary[:4000]}\n\n请决策下一步。",
        )
        return True

    # ── Private orchestration ─────────────────────────────────

    async def _handle_workflow_advance(
        self,
        plan: FlowPlan,
        card_id: str,
        next_step: FlowStep | None,
        session: Session,
    ) -> None:
        """In workflow mode: auto-move card to next slot or mark plan complete."""
        if next_step is None:
            # All steps done
            plan.complete()
            await self._flow_plan_repo.save(plan)
            await self._broadcast_flow_event("flow_plan_completed", plan)
            # Notify Leader of completion
            if plan.leader_session_id:
                # Make the terminal state authoritative before the persistent
                # Leader starts a new turn that may query the plan.
                await self._commit_before_leader_turn()
                safe_create_task(self._notify_completed_plan(plan))
            return

        card = await self._card_repo.find_by_id(card_id)
        if card is None:
            logger.warning("[flow_engine] card %s not found for workflow advance", card_id)
            return
        await self._execute_step(plan, next_step, card)

    async def _handle_decision_notify(
        self,
        plan: FlowPlan,
        card_id: str,
        session: Session,
    ) -> None:
        """In decision mode: send completion context to Leader's session."""
        if not plan.leader_session_id:
            logger.warning("[flow_engine] plan %s has no leader_session_id", plan.id)
            return

        # Build context from the completed session's output
        context = self._build_step_complete_context(plan, session)
        completed_step = next(
            (item for item in reversed(plan.steps) if item.status == FlowStepStatus.COMPLETED),
            None,
        )
        if completed_step is not None:
            # Persist both the completed step and its notification claim before
            # waking Leader.  Otherwise Leader observes RUNNING and its next
            # write deadlocks behind this transaction.
            completed_step.mark_leader_notified()
            await self._flow_plan_repo.save(plan)
        await self._commit_before_leader_turn()

        try:
            await self._leader_session_manager.compact_if_needed(plan.leader_session_id)
            await self._leader_session_manager.append_message(
                plan.leader_session_id,
                context,
            )
        except Exception:
            # Restore the reconciliation signal when delivery fails normally.
            # A watchdog can then retry the terminal-step notification.
            if completed_step is not None:
                completed_step.leader_notified_at = None
                await self._flow_plan_repo.save(plan)
                await self._commit_before_leader_turn()
            raise

    async def _commit_before_leader_turn(self) -> None:
        """Expose orchestration state before Leader performs its next action."""
        if self._commit_fn is not None:
            await self._commit_fn()

    async def _notify_leader_failure(
        self,
        plan: FlowPlan,
        step: FlowStep,
        reason: str,
        category: ExecutionFailureCategory,
    ) -> bool:
        """Notify Leader about a step failure."""
        if not plan.leader_session_id:
            logger.warning("[flow_engine] plan %s has no leader_session_id for failure notification", plan.id)
            return False

        team = await self._team_repo.find_by_id(plan.team_id)
        slot_name = "unknown"
        if team is not None:
            slot = team.find_agent_slot(step.target_slot_id)
            if slot is not None:
                slot_name = slot.name

        message = (
            f"## 子 Agent 执行失败\n\n"
            f"- **Agent**: {slot_name}\n"
            f"- **失败类别**: {category.value}\n"
            f"- **原因**: {reason}\n"
            f"- **步骤**: 第 {step.sequence} 步\n\n"
            "请决策下一步操作：\n"
            "1. 使用 /advance-card 重试或分配给其他 Agent\n"
            "2. 使用 /complete-plan 标记计划完成（忽略此步骤）\n"
            "3. 使用其他方式处理"
        )
        try:
            await self._leader_session_manager.compact_if_needed(plan.leader_session_id)
            await self._leader_session_manager.append_message(
                plan.leader_session_id,
                message,
            )
            return True
        except Exception:
            logger.error(
                "[flow_engine] Failed to notify leader of step failure, plan=%s step=%s",
                plan.id,
                step.id,
                exc_info=True,
            )
            return False

    async def _execute_step(
        self,
        plan: FlowPlan,
        step: FlowStep,
        card: WishCard,
        context: str = "",
    ) -> None:
        """Move the card to the step's target slot and start execution."""
        if self._move_card_fn is None:
            raise TeamDomainError("FlowEngine has no move_card_fn configured")

        # Reload card to get latest version
        fresh_card = await self._card_repo.find_by_id(card.id)
        if fresh_card is None:
            raise TeamDomainError(f"Card {card.id} not found")

        idempotency_key = f"flow-{plan.id}-step-{step.id}"
        move_cmd = MoveWishCardCommand(
            team_id=plan.team_id,
            card_id=fresh_card.id,
            target_slot_id=step.target_slot_id,
            card_version=fresh_card.version,
            idempotency_key=idempotency_key,
            triggered_by=(
                ExecutionTrigger.WORKFLOW.value
                if plan.mode == FlowMode.WORKFLOW
                else ExecutionTrigger.DECISION.value
            ),
            delegated_by_slot_id=plan.leader_slot_id,
            flow_plan_id=plan.id,
            flow_step_id=step.id,
            delegation_context=context,
        )
        execution = await self._move_card_fn(move_cmd)
        step.mark_running(execution.id)
        await self._flow_plan_repo.save(plan)

    async def _broadcast_flow_event(self, event: str, plan: FlowPlan) -> None:
        """Broadcast a flow plan event via WebSocket."""
        if self._connection_manager is None:
            return
        payload: dict[str, object] = {
            "event": event,
            "team_id": plan.team_id,
            "plan_id": plan.id,
            "card_id": plan.card_id,
            "mode": plan.mode.value,
            "status": plan.status.value,
            "current_step": None,
        }
        current = plan.current_step
        if current is not None:
            payload["current_step"] = {
                "id": current.id,
                "sequence": current.sequence,
                "target_slot_id": current.target_slot_id,
                "status": current.status.value,
            }
        await self._connection_manager.broadcast_global(payload)

    async def _notify_completed_plan(self, plan: FlowPlan) -> None:
        if not plan.leader_session_id:
            return
        try:
            await self._leader_session_manager.compact_if_needed(
                plan.leader_session_id
            )
            await self._leader_session_manager.append_message(
                plan.leader_session_id,
                self._build_plan_complete_message(plan),
            )
        except Exception:
            logger.error(
                "[flow_engine] Failed to notify Leader of completed plan %s",
                plan.id,
                exc_info=True,
            )

    # ── Message builders ──────────────────────────────────────

    @staticmethod
    def _build_plan_complete_message(plan: FlowPlan) -> str:
        completed_steps = [s for s in plan.steps if s.status.value == "completed"]
        step_lines = "\n".join(
            f"- 步骤 {s.sequence}: slot={s.target_slot_id} ✓"
            for s in completed_steps
        )
        return (
            "## 流转计划已完成\n\n"
            f"计划 ID: {plan.id}\n"
            f"模式: {plan.mode.value}\n"
            f"已完成步骤:\n{step_lines}\n\n"
            "所有子 Agent 工作已按流水线顺序执行完毕。"
            "这是终态通知，无需查询额外接口或继续推进该计划。"
        )

    @staticmethod
    def _build_step_complete_context(plan: FlowPlan, session: Session) -> str:
        from domain.session.service.message_conversion_service import MessageConversionService

        final_output = MessageConversionService.extract_assistant_text(session.messages)
        # Truncate if too long
        if len(final_output) > 4000:
            final_output = final_output[:4000] + "\n\n...(已截断)"

        completed_step = next(
            (s for s in reversed(plan.steps) if s.status.value == "completed"),
            None,
        )
        step_info = f"步骤 {completed_step.sequence}" if completed_step else "未知步骤"

        return (
            f"## 子 Agent 执行完成 — {step_info}\n\n"
            f"### 执行结果摘要\n{final_output}\n\n"
            "请决策下一步：\n"
            "- 使用 /advance-card 将卡片推进到下一个 Agent\n"
            "- 使用 /complete-plan 标记整个计划完成\n"
            "- 使用 /get-board-status 查看当前看板状态"
        )
