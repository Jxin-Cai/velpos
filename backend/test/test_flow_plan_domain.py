"""Unit tests for FlowPlan domain model."""

import pytest

from domain.team.model.flow_plan import FlowPlan, FlowStep
from domain.team.model.status import (
    FlowMode,
    FlowPlanStatus,
    FlowStepStatus,
)
from domain.team.model.team_domain_error import TeamDomainError


class TestFlowPlanCreate:
    def test_create_workflow_plan_with_valid_steps(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.WORKFLOW,
            step_slot_ids=["slot-a", "slot-b", "slot-c"],
            leader_session_id="session-1",
        )

        assert plan.status == FlowPlanStatus.ACTIVE
        assert plan.mode == FlowMode.WORKFLOW
        assert len(plan.steps) == 3
        assert plan.steps[0].sequence == 1
        assert plan.steps[1].sequence == 2
        assert plan.steps[2].sequence == 3
        assert all(s.status == FlowStepStatus.PENDING for s in plan.steps)

    def test_create_decision_plan_with_single_step(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.DECISION,
            step_slot_ids=["slot-x"],
        )

        assert plan.mode == FlowMode.DECISION
        assert len(plan.steps) == 1

    def test_create_raises_when_no_steps(self):
        with pytest.raises(TeamDomainError, match="at least one step"):
            FlowPlan.create(
                team_id="team-1",
                card_id="card-1",
                leader_slot_id="leader-1",
                mode=FlowMode.WORKFLOW,
                step_slot_ids=[],
            )

    def test_create_raises_when_blank_team_id(self):
        with pytest.raises(TeamDomainError, match="team_id"):
            FlowPlan.create(
                team_id="  ",
                card_id="card-1",
                leader_slot_id="leader-1",
                mode=FlowMode.WORKFLOW,
                step_slot_ids=["slot-a"],
            )


class TestFlowPlanAdvance:
    def _make_active_plan(self) -> FlowPlan:
        return FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.WORKFLOW,
            step_slot_ids=["slot-a", "slot-b", "slot-c"],
        )

    def test_advance_step_returns_next_pending(self):
        plan = self._make_active_plan()
        plan.steps[0].mark_running("exec-1")

        next_step = plan.advance_step(plan.steps[0].id)

        assert plan.steps[0].status == FlowStepStatus.COMPLETED
        assert next_step is not None
        assert next_step.target_slot_id == "slot-b"

    def test_advance_last_step_returns_none(self):
        plan = self._make_active_plan()
        # Complete first two steps
        plan.steps[0].mark_running("exec-1")
        plan.advance_step(plan.steps[0].id)
        plan.steps[1].mark_running("exec-2")
        plan.advance_step(plan.steps[1].id)
        plan.steps[2].mark_running("exec-3")

        next_step = plan.advance_step(plan.steps[2].id)

        assert next_step is None
        assert plan.is_all_steps_terminal

    def test_advance_raises_when_plan_not_active(self):
        plan = self._make_active_plan()
        plan.status = FlowPlanStatus.CANCELLED

        with pytest.raises(TeamDomainError, match="cannot advance"):
            plan.advance_step(plan.steps[0].id)


class TestFlowPlanFail:
    def test_fail_step_in_workflow_mode_fails_plan(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.WORKFLOW,
            step_slot_ids=["slot-a", "slot-b"],
        )
        plan.steps[0].mark_running("exec-1")

        plan.fail_step(plan.steps[0].id, "agent crashed")

        assert plan.steps[0].status == FlowStepStatus.FAILED
        assert plan.status == FlowPlanStatus.FAILED

    def test_fail_step_in_decision_mode_keeps_plan_active(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.DECISION,
            step_slot_ids=["slot-a"],
        )
        plan.steps[0].mark_running("exec-1")

        plan.fail_step(plan.steps[0].id, "agent crashed")

        assert plan.steps[0].status == FlowStepStatus.FAILED
        assert plan.status == FlowPlanStatus.ACTIVE


class TestFlowPlanComplete:
    def test_complete_when_all_steps_terminal(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.WORKFLOW,
            step_slot_ids=["slot-a"],
        )
        plan.steps[0].mark_running("exec-1")
        plan.advance_step(plan.steps[0].id)

        plan.complete()

        assert plan.status == FlowPlanStatus.COMPLETED

    def test_complete_raises_when_non_terminal_steps_exist(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.WORKFLOW,
            step_slot_ids=["slot-a", "slot-b"],
        )
        plan.steps[0].mark_running("exec-1")
        plan.advance_step(plan.steps[0].id)

        with pytest.raises(TeamDomainError, match="non-terminal"):
            plan.complete()


class TestFlowPlanCancel:
    def test_cancel_skips_pending_steps(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.WORKFLOW,
            step_slot_ids=["slot-a", "slot-b", "slot-c"],
        )
        plan.steps[0].mark_running("exec-1")
        plan.advance_step(plan.steps[0].id)

        plan.cancel()

        assert plan.status == FlowPlanStatus.CANCELLED
        assert plan.steps[0].status == FlowStepStatus.COMPLETED
        assert plan.steps[1].status == FlowStepStatus.SKIPPED
        assert plan.steps[2].status == FlowStepStatus.SKIPPED


class TestFlowPlanAddStep:
    def test_add_step_in_decision_mode(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.DECISION,
            step_slot_ids=["slot-a"],
        )

        new_step = plan.add_step("slot-b")

        assert len(plan.steps) == 2
        assert new_step.sequence == 2
        assert new_step.target_slot_id == "slot-b"
        assert new_step.status == FlowStepStatus.PENDING

    def test_add_step_raises_when_plan_not_active(self):
        plan = FlowPlan.create(
            team_id="team-1",
            card_id="card-1",
            leader_slot_id="leader-1",
            mode=FlowMode.DECISION,
            step_slot_ids=["slot-a"],
        )
        plan.cancel()

        with pytest.raises(TeamDomainError, match="cannot add step"):
            plan.add_step("slot-b")


class TestFlowStepStateMachine:
    def test_mark_running_from_pending(self):
        step = FlowStep.create("plan-1", 1, "slot-a")

        step.mark_running("exec-1")

        assert step.status == FlowStepStatus.RUNNING
        assert step.execution_id == "exec-1"
        assert step.started_at is not None

    def test_mark_running_raises_when_not_pending(self):
        step = FlowStep.create("plan-1", 1, "slot-a")
        step.mark_running("exec-1")

        with pytest.raises(TeamDomainError, match="only start from pending"):
            step.mark_running("exec-2")

    def test_mark_completed_from_running(self):
        step = FlowStep.create("plan-1", 1, "slot-a")
        step.mark_running("exec-1")

        step.mark_completed()

        assert step.status == FlowStepStatus.COMPLETED
        assert step.ended_at is not None

    def test_mark_failed_from_running(self):
        step = FlowStep.create("plan-1", 1, "slot-a")
        step.mark_running("exec-1")

        step.mark_failed()

        assert step.status == FlowStepStatus.FAILED

    def test_mark_skipped_from_pending(self):
        step = FlowStep.create("plan-1", 1, "slot-a")

        step.mark_skipped()

        assert step.status == FlowStepStatus.SKIPPED

    def test_mark_skipped_raises_when_not_pending(self):
        step = FlowStep.create("plan-1", 1, "slot-a")
        step.mark_running("exec-1")

        with pytest.raises(TeamDomainError, match="only pending"):
            step.mark_skipped()
