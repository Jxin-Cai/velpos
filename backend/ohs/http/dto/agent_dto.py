from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    emoji: str
    color: str
    has_plugin: bool = False
    source: Literal["system", "custom"] = "system"


class AgentCategoryInfo(BaseModel):
    id: str
    name: str
    agents: list[AgentInfo]


class AgentListResponse(BaseModel):
    categories: list[AgentCategoryInfo]


class LoadAgentRequest(BaseModel):
    agent_id: str = Field(min_length=1, description="Agent ID to load")
    language: str = Field(
        default="en",
        pattern="^(en|zh)$",
        description="Language for agent prompt: en or zh",
    )
