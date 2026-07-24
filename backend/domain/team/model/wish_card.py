from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from domain.team.model.card_execution import CardExecution
from domain.team.model.status import WishCardStatus
from domain.team.model.team_domain_error import TeamDomainError


@dataclass
class WishCard:
    id: str
    team_id: str
    title: str
    description: str
    status: WishCardStatus
    created_at: datetime
    updated_at: datetime
    assigned_agent_slot_id: str | None = None
    executions: list[CardExecution] = field(default_factory=list)

    @classmethod
    def create(cls, team_id: str, title: str, description: str = "") -> "WishCard":
        if not team_id.strip():
            raise TeamDomainError("team_id must not be blank")
        if not title.strip():
            raise TeamDomainError("wish card title must not be blank")

        now = datetime.now(timezone.utc)
        return cls(
            id=str(uuid4()),
            team_id=team_id,
            title=title,
            description=description,
            status=WishCardStatus.BACKLOG,
            created_at=now,
            updated_at=now,
        )

    @property
    def can_be_assigned(self) -> bool:
        return self.status in {
            WishCardStatus.BACKLOG,
            WishCardStatus.COMPLETED,
            WishCardStatus.FAILED,
            WishCardStatus.CANCELLED,
        }

    @property
    def can_be_archived(self) -> bool:
        return self.status in {
            WishCardStatus.BACKLOG,
            WishCardStatus.COMPLETED,
            WishCardStatus.FAILED,
            WishCardStatus.CANCELLED,
        }

    @property
    def active_execution(self) -> CardExecution | None:
        active = [execution for execution in self.executions if not execution.is_terminal]
        if len(active) > 1:
            raise TeamDomainError("wish card has more than one active execution")
        return active[0] if active else None

    @property
    def current_slot_id(self) -> str | None:
        """The slot that owns the latest execution (used by the board)."""
        return self.assigned_agent_slot_id

    @property
    def version(self) -> int:
        return len(self.executions)

    @property
    def latest_execution(self) -> CardExecution | None:
        return self.executions[-1] if self.executions else None

    def assign_to(
        self,
        agent_slot_id: str,
        idempotency_key: str | None = None,
    ) -> CardExecution:
        if not self.can_be_assigned:
            raise TeamDomainError(f"wish card cannot be assigned in status {self.status.value}")
        if self.active_execution is not None:
            raise TeamDomainError("wish card already has an active execution")

        execution = CardExecution.create(self.id, agent_slot_id, idempotency_key)
        self.executions.append(execution)
        self.assigned_agent_slot_id = agent_slot_id
        self.status = WishCardStatus.PREPARING
        self.updated_at = datetime.now(timezone.utc)
        return execution

    def retry_on(self, agent_slot_id: str) -> CardExecution:
        """Create a fresh execution after a failed or cancelled run."""
        if self.status not in {WishCardStatus.FAILED, WishCardStatus.CANCELLED}:
            raise TeamDomainError(
                f"wish card can only be retried after failure, current status is {self.status.value}"
            )
        if self.active_execution is not None:
            raise TeamDomainError("wish card already has an active execution")
        execution = CardExecution.create(self.id, agent_slot_id)
        self.executions.append(execution)
        self.assigned_agent_slot_id = agent_slot_id
        self.status = WishCardStatus.PREPARING
        self.updated_at = datetime.now(timezone.utc)
        return execution

    def start_execution(self, execution_id: str) -> None:
        execution = self._require_active_execution(execution_id)
        execution.start()
        self.status = WishCardStatus.RUNNING
        self.updated_at = datetime.now(timezone.utc)

    def complete_execution(self, execution_id: str) -> None:
        execution = self._require_active_execution(execution_id)
        execution.complete()
        self.status = WishCardStatus.COMPLETED
        self.updated_at = datetime.now(timezone.utc)

    def fail_execution(self, execution_id: str, reason: str) -> None:
        execution = self._require_active_execution(execution_id)
        execution.fail(reason)
        self.status = WishCardStatus.FAILED
        self.updated_at = datetime.now(timezone.utc)

    def cancel_execution(self, execution_id: str) -> None:
        execution = self._require_active_execution(execution_id)
        execution.cancel()
        self.status = WishCardStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)

    def archive(self) -> None:
        if not self.can_be_archived:
            raise TeamDomainError(
                f"wish card cannot be archived in status {self.status.value}"
            )
        if self.active_execution is not None:
            raise TeamDomainError("wish card with an active execution cannot be archived")
        self.status = WishCardStatus.ARCHIVED
        self.assigned_agent_slot_id = None
        self.updated_at = datetime.now(timezone.utc)

    def _require_active_execution(self, execution_id: str) -> CardExecution:
        execution = self.active_execution
        if execution is None or execution.id != execution_id:
            raise TeamDomainError(f"active execution not found: {execution_id}")
        return execution
