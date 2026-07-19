from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from domain.team.model.status import HandoffStatus
from domain.team.model.team_domain_error import TeamDomainError


@dataclass(frozen=True)
class HandoffArtifact:
    id: str
    handoff_id: str
    name: str
    path: str
    media_type: str
    created_at: datetime


@dataclass
class Handoff:
    id: str
    team_id: str
    card_id: str
    source_execution_id: str
    source_agent_slot_id: str
    target_agent_slot_id: str
    summary: str
    status: HandoffStatus
    created_at: datetime
    resolved_at: datetime | None = None
    artifacts: list[HandoffArtifact] = field(default_factory=list)

    def add_artifact(
        self,
        name: str,
        path: str,
        media_type: str = "",
    ) -> HandoffArtifact:
        if not name.strip():
            raise TeamDomainError("artifact name must not be blank")
        if not path.strip():
            raise TeamDomainError("artifact path must not be blank")
        artifact = HandoffArtifact(
            id=str(uuid4()),
            handoff_id=self.id,
            name=name,
            path=path,
            media_type=media_type,
            created_at=datetime.now(timezone.utc),
        )
        self.artifacts.append(artifact)
        return artifact

    @classmethod
    def create(
        cls,
        team_id: str,
        card_id: str,
        source_execution_id: str,
        source_agent_slot_id: str,
        target_agent_slot_id: str,
        summary: str,
    ) -> "Handoff":
        required = {
            "team_id": team_id,
            "card_id": card_id,
            "source_execution_id": source_execution_id,
            "source_agent_slot_id": source_agent_slot_id,
            "target_agent_slot_id": target_agent_slot_id,
            "summary": summary,
        }
        blank_field = next((name for name, value in required.items() if not value.strip()), None)
        if blank_field is not None:
            raise TeamDomainError(f"{blank_field} must not be blank")
        if source_agent_slot_id == target_agent_slot_id:
            raise TeamDomainError("handoff target must differ from source agent slot")

        return cls(
            id=str(uuid4()),
            team_id=team_id,
            card_id=card_id,
            source_execution_id=source_execution_id,
            source_agent_slot_id=source_agent_slot_id,
            target_agent_slot_id=target_agent_slot_id,
            summary=summary,
            status=HandoffStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

    def accept(self) -> None:
        self._require_pending()
        self.status = HandoffStatus.ACCEPTED
        self.resolved_at = datetime.now(timezone.utc)

    def reject(self) -> None:
        self._require_pending()
        self.status = HandoffStatus.REJECTED
        self.resolved_at = datetime.now(timezone.utc)

    def _require_pending(self) -> None:
        if self.status is not HandoffStatus.PENDING:
            raise TeamDomainError(f"handoff is already {self.status.value}")
