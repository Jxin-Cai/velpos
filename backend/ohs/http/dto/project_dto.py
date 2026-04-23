from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from domain.project.model.project import Project
from ohs.assembler.project_assembler import ProjectAssembler


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Project name")
    github_url: str = Field(default="", max_length=500, description="Optional GitHub repository URL to clone")


class InitPluginRequest(BaseModel):
    plugin_type: str = Field(min_length=1, max_length=32, description="Plugin type, e.g. 'lark'")
    session_id: str = Field(min_length=1, description="Current session ID to run init in")


class CompletePluginInitRequest(BaseModel):
    plugin_type: str = Field(min_length=1, max_length=32, description="Plugin type to complete init for")


class ResetPluginRequest(BaseModel):
    plugin_type: str = Field(min_length=1, max_length=32, description="Plugin type to uninstall")


class ReorderProjectsRequest(BaseModel):
    ordered_ids: list[str] = Field(description="Project IDs in desired order")


class ProjectResponse(BaseModel):
    id: str
    name: str
    dir_path: str
    agents: dict[str, dict] = {}
    plugins: dict[str, dict] = {}
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_domain(cls, project: Project) -> ProjectResponse:
        d = ProjectAssembler.to_dict(project)
        return cls(**d)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]

    @classmethod
    def from_domain_list(cls, projects: list[Project]) -> ProjectListResponse:
        return cls(
            projects=[ProjectResponse.from_domain(p) for p in projects],
        )


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    dir_path: str
    agents: dict[str, dict] = {}
    plugins: dict[str, dict] = {}
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    sessions: list[dict[str, Any]] = []

    @classmethod
    def from_domain(
        cls, project: Project, sessions: list[dict[str, Any]]
    ) -> ProjectDetailResponse:
        d = ProjectAssembler.to_dict(project)
        return cls(**d, sessions=sessions)


class EnsureProjectsRequest(BaseModel):
    dir_paths: list[str] = Field(description="List of directory paths to ensure projects for")


class EnsureProjectsResponse(BaseModel):
    mappings: dict[str, str] = Field(description="Mapping of dir_path to project_id")


class PickDirectoryResponse(BaseModel):
    dir_path: str = Field(description="Selected directory path")


class GitBranchesResponse(BaseModel):
    current: str
    branches: list[str]


class GitCheckoutRequest(BaseModel):
    branch: str = Field(min_length=1, description="Branch name to checkout")


class GitCheckoutResponse(BaseModel):
    current: str
