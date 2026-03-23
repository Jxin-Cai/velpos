from __future__ import annotations

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


class LoadAgentRequest(BaseModel):
    agent_id: str = Field(min_length=1, description="Agent ID to load")
    language: str = Field(
        default="en",
        pattern="^(en|zh)$",
        description="Language for agent prompt: en or zh",
    )


class UnloadAgentRequest(BaseModel):
    pass
