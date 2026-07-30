from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from domain.team.model.status import FlowMode, FlowPlanStatus, FlowStepStatus
from domain.team.model.team_domain_error import TeamDomainError


@dataclass
class FlowStep:
    id: str
    flow_plan_id: str
    sequence: int
    target_slot_id: str
    status: FlowStepStatus
    execution_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    leader_notified_at: datetime | None = None

    @classmethod
    def create(
        cls,
        flow_plan_id: str,
        sequence: int,
        target_slot_id: str,
    ) -> FlowStep:
        if not flow_plan_id.strip():
            raise TeamDomainError("flow_plan_id must not be blank")
        if sequence < 1:
            raise TeamDomainError("flow step sequence must be positive")
        if not target_slot_id.strip():
            raise TeamDomainError("target_slot_id must not be blank")

        return cls(
            id=str(uuid4()),
            flow_plan_id=flow_plan_id,
            sequence=sequence,
            target_slot_id=target_slot_id,
            status=FlowStepStatus.PENDING,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    def mark_running(self, execution_id: str) -> None:
        if self.status != FlowStepStatus.PENDING:
            raise TeamDomainError(
                f"flow step can only start from pending, current: {self.status.value}"
            )
        self.status = FlowStepStatus.RUNNING
        self.execution_id = execution_id
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        if self.status != FlowStepStatus.RUNNING:
            raise TeamDomainError(
                f"flow step can only complete from running, current: {self.status.value}"
            )
        self.status = FlowStepStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc)

    def mark_failed(self) -> None:
        if self.status not in {FlowStepStatus.PENDING, FlowStepStatus.RUNNING}:
            raise TeamDomainError(
                f"flow step cannot be failed in status {self.status.value}"
            )
        self.status = FlowStepStatus.FAILED
        self.ended_at = datetime.now(timezone.utc)

    def mark_skipped(self) -> None:
        if self.status != FlowStepStatus.PENDING:
            raise TeamDomainError(
                f"only pending steps can be skipped, current: {self.status.value}"
            )
        self.status = FlowStepStatus.SKIPPED
        self.ended_at = datetime.now(timezone.utc)

    def mark_leader_notified(self) -> None:
        if not self.is_terminal:
            raise TeamDomainError("leader can only be notified for a terminal flow step")
        self.leader_notified_at = datetime.now(timezone.utc)


@dataclass
class FlowPlan:
    id: str
    team_id: str
    card_id: str
    leader_slot_id: str
    mode: FlowMode
    status: FlowPlanStatus
    steps: list[FlowStep] = field(default_factory=list)
    leader_session_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        *,
        team_id: str,
        card_id: str,
        leader_slot_id: str,
        mode: FlowMode,
        step_slot_ids: list[str],
        leader_session_id: str | None = None,
    ) -> FlowPlan:
        required = {
            "team_id": team_id,
            "card_id": card_id,
            "leader_slot_id": leader_slot_id,
        }
        blank = next((name for name, value in required.items() if not value.strip()), None)
        if blank is not None:
            raise TeamDomainError(f"{blank} must not be blank")
        if not step_slot_ids:
            raise TeamDomainError("flow plan must have at least one step")

        plan_id = str(uuid4())
        now = datetime.now(timezone.utc)
        plan = cls(
            id=plan_id,
            team_id=team_id,
            card_id=card_id,
            leader_slot_id=leader_slot_id,
            mode=mode,
            status=FlowPlanStatus.ACTIVE,
            leader_session_id=leader_session_id,
            created_at=now,
            updated_at=now,
        )
        for sequence, slot_id in enumerate(step_slot_ids, start=1):
            step = FlowStep.create(
                flow_plan_id=plan_id,
                sequence=sequence,
                target_slot_id=slot_id,
            )
            plan.steps.append(step)
        return plan

    @property
    def current_step(self) -> FlowStep | None:
        """The first non-terminal step (PENDING or RUNNING)."""
        for step in self.steps:
            if not step.is_terminal:
                return step
        return None

    @property
    def next_pending_step(self) -> FlowStep | None:
        """The first step still in PENDING status."""
        for step in self.steps:
            if step.status == FlowStepStatus.PENDING:
                return step
        return None

    @property
    def is_all_steps_terminal(self) -> bool:
        return all(step.is_terminal for step in self.steps)

    def advance_step(self, step_id: str) -> FlowStep | None:
        """Mark the given step as COMPLETED and return the next PENDING step (or None)."""
        if self.status != FlowPlanStatus.ACTIVE:
            raise TeamDomainError(
                f"cannot advance step on plan in status {self.status.value}"
            )
        step = self._find_step(step_id)
        step.mark_completed()
        self.updated_at = datetime.now(timezone.utc)
        return self.next_pending_step

    def fail_step(self, step_id: str, reason: str) -> None:
        """Mark the given step as FAILED. In workflow mode, also fail the plan."""
        if self.status != FlowPlanStatus.ACTIVE:
            raise TeamDomainError(
                f"cannot fail step on plan in status {self.status.value}"
            )
        step = self._find_step(step_id)
        step.mark_failed()
        self.updated_at = datetime.now(timezone.utc)
        if self.mode == FlowMode.WORKFLOW:
            self.status = FlowPlanStatus.FAILED

    def skip_remaining_steps(self) -> None:
        """Skip all remaining PENDING steps (used when plan is cancelled)."""
        for step in self.steps:
            if step.status == FlowStepStatus.PENDING:
                step.mark_skipped()
        self.updated_at = datetime.now(timezone.utc)

    def complete(self) -> None:
        """Mark the plan as COMPLETED. All steps must be terminal."""
        if self.status != FlowPlanStatus.ACTIVE:
            raise TeamDomainError(
                f"cannot complete plan in status {self.status.value}"
            )
        if not self.is_all_steps_terminal:
            raise TeamDomainError("cannot complete plan with non-terminal steps")
        self.status = FlowPlanStatus.COMPLETED
        self.updated_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        """Cancel the plan and skip all pending steps."""
        if self.status != FlowPlanStatus.ACTIVE:
            raise TeamDomainError(
                f"cannot cancel plan in status {self.status.value}"
            )
        self.skip_remaining_steps()
        self.status = FlowPlanStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)

    def add_step(self, target_slot_id: str) -> FlowStep:
        """Dynamically add a step at the end (used in decision mode)."""
        if self.status != FlowPlanStatus.ACTIVE:
            raise TeamDomainError(
                f"cannot add step to plan in status {self.status.value}"
            )
        next_sequence = max((s.sequence for s in self.steps), default=0) + 1
        step = FlowStep.create(
            flow_plan_id=self.id,
            sequence=next_sequence,
            target_slot_id=target_slot_id,
        )
        self.steps.append(step)
        self.updated_at = datetime.now(timezone.utc)
        return step

    def find_step_by_execution_id(self, execution_id: str) -> FlowStep | None:
        return next(
            (step for step in self.steps if step.execution_id == execution_id),
            None,
        )

    def _find_step(self, step_id: str) -> FlowStep:
        step = next((s for s in self.steps if s.id == step_id), None)
        if step is None:
            raise TeamDomainError(f"flow step not found: {step_id}")
        return step
