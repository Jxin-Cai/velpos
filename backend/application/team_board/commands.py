from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSlotConfig:
    display_name: str
    agent_profile_id: str
    slug: str = ""


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
