from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSlotConfig:
    display_name: str
    agent_profile_id: str
    slug: str = ""
    is_leader: bool = False


@dataclass(frozen=True)
class CreateTeamCommand:
    name: str
    project_id: str
    root_path: str
    slots: tuple[AgentSlotConfig, ...]


@dataclass(frozen=True)
class CreateWishCardCommand:
    team_id: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class MoveWishCardCommand:
    team_id: str
    card_id: str
    target_slot_id: str
    card_version: int
    idempotency_key: str
    triggered_by: str = "user"
    delegated_by_slot_id: str | None = None
    flow_plan_id: str | None = None
    flow_step_id: str | None = None
    delegation_context: str = ""


@dataclass(frozen=True)
class RetryExecutionCommand:
    execution_id: str


@dataclass(frozen=True)
class ArchiveWishCardCommand:
    team_id: str
    card_id: str
    card_version: int


@dataclass(frozen=True)
class DeleteWishCardCommand:
    team_id: str
    card_id: str


@dataclass(frozen=True)
class RegisterFlowPlanCommand:
    team_id: str
    card_id: str
    mode: str
    step_slot_ids: tuple[str, ...]


@dataclass(frozen=True)
class AdvanceFlowCommand:
    team_id: str
    card_id: str
    target_slot_id: str
    context: str = ""


@dataclass(frozen=True)
class CompleteFlowPlanCommand:
    team_id: str
    plan_id: str
    summary: str = ""


@dataclass(frozen=True)
class CancelFlowPlanCommand:
    team_id: str
    plan_id: str
    reason: str = ""
