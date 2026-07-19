from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from domain.team.model.agent_slot import AgentSlot
from domain.team.model.team_domain_error import TeamDomainError


@dataclass
class Team:
    id: str
    project_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    agent_slots: list[AgentSlot] = field(default_factory=list)

    @classmethod
    def create(cls, project_id: str, name: str) -> "Team":
        if not project_id.strip():
            raise TeamDomainError("project_id must not be blank")
        if not name.strip():
            raise TeamDomainError("team name must not be blank")

        now = datetime.now(timezone.utc)
        return cls(
            id=str(uuid4()),
            project_id=project_id,
            name=name,
            created_at=now,
            updated_at=now,
        )

    def add_agent_slot(
        self,
        name: str,
        role: str,
        workspace_ref: str,
    ) -> AgentSlot:
        if any(slot.name == name for slot in self.agent_slots):
            raise TeamDomainError(f"agent slot name already exists: {name}")
        if any(slot.workspace_ref == workspace_ref for slot in self.agent_slots):
            raise TeamDomainError(
                f"workspace must be independent for each agent slot: {workspace_ref}"
            )

        slot = AgentSlot.create(
            team_id=self.id,
            name=name,
            role=role,
            workspace_ref=workspace_ref,
        )
        self.agent_slots.append(slot)
        self.updated_at = datetime.now(timezone.utc)
        return slot

    def find_agent_slot(self, slot_id: str) -> AgentSlot | None:
        return next((slot for slot in self.agent_slots if slot.id == slot_id), None)
