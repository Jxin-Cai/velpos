from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from domain.team.model.status import CardExecutionStatus
from domain.team.model.team_domain_error import TeamDomainError


@dataclass
class CardExecution:
    id: str
    card_id: str
    agent_slot_id: str
    status: CardExecutionStatus
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failure_reason: str | None = None
    session_id: str | None = None
    idempotency_key: str | None = None

    @classmethod
    def create(
        cls,
        card_id: str,
        agent_slot_id: str,
        idempotency_key: str | None = None,
    ) -> "CardExecution":
        if not card_id.strip():
            raise TeamDomainError("card_id must not be blank")
        if not agent_slot_id.strip():
            raise TeamDomainError("agent_slot_id must not be blank")

        return cls(
            id=str(uuid4()),
            card_id=card_id,
            agent_slot_id=agent_slot_id,
            status=CardExecutionStatus.PREPARING,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    def start(self) -> None:
        self._require_status(CardExecutionStatus.PREPARING)
        self.status = CardExecutionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def complete(self) -> None:
        self._require_status(CardExecutionStatus.RUNNING)
        self.status = CardExecutionStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc)

    def fail(self, reason: str) -> None:
        if self.status not in {
            CardExecutionStatus.PREPARING,
            CardExecutionStatus.RUNNING,
        }:
            raise TeamDomainError(f"cannot fail execution in status {self.status.value}")
        if not reason.strip():
            raise TeamDomainError("failure reason must not be blank")
        self.status = CardExecutionStatus.FAILED
        self.failure_reason = reason
        self.ended_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        if self.status not in {
            CardExecutionStatus.PREPARING,
            CardExecutionStatus.RUNNING,
        }:
            raise TeamDomainError(f"cannot cancel execution in status {self.status.value}")
        self.status = CardExecutionStatus.CANCELLED
        self.ended_at = datetime.now(timezone.utc)

    def _require_status(self, expected: CardExecutionStatus) -> None:
        if self.status is not expected:
            raise TeamDomainError(
                f"execution must be {expected.value}, current status is {self.status.value}"
            )
