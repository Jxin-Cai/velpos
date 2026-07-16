from __future__ import annotations

from pydantic import BaseModel, Field


class PluginActionRequest(BaseModel):
    plugin: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Plugin identifier (e.g. 'tw-all@thoughtworks')",
    )
    project_dir: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Project directory path for scope=project",
    )


class PluginInfo(BaseModel):
    name: str
    marketplace: str
    key: str
    description: str
    version: str
    scope: str
    enabled: bool
    installed: bool
    updated_at: str = ""


class PluginListResponse(BaseModel):
    plugins: list[PluginInfo]


class PluginActionResponse(BaseModel):
    message: str


class PluginUpgradeAllRequest(BaseModel):
    project_dir: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Project directory path for scope=project",
    )
