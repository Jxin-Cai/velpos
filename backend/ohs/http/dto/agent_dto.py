from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    emoji: str
    color: str
    has_plugin: bool = False


class AgentCategoryInfo(BaseModel):
    id: str
    name: str
    agents: list[AgentInfo]


class AgentListResponse(BaseModel):
    categories: list[AgentCategoryInfo]


class TeamTemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    mode: str
    pipeline: list[dict[str, Any]] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    default_config: dict[str, Any] = Field(default_factory=dict)


class TeamTemplateListResponse(BaseModel):
    templates: list[TeamTemplateInfo]


class LoadAgentRequest(BaseModel):
    agent_id: str = Field(min_length=1, description="Agent ID to load")
    language: str = Field(
        default="en",
        pattern="^(en|zh)$",
        description="Language for agent prompt: en or zh",
    )
