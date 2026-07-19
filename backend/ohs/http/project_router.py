from __future__ import annotations

import io
import mimetypes
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse

from application.project.command.create_project_command import CreateProjectCommand
from application.project.command.init_plugin_command import InitPluginCommand
from application.project.command.reorder_projects_command import ReorderProjectsCommand
from application.project.plugin_init_application_service import PluginInitApplicationService
from application.project.project_application_service import ProjectApplicationService
from application.project.workspace_application_service import WorkspaceApplicationService
from ohs.assembler.session_assembler import SessionAssembler
from ohs.dependencies import get_plugin_init_application_service, get_project_application_service, get_workspace_application_service
from ohs.dependencies import get_project_repository, get_team_board_service
from domain.project.model.project import Project
from application.team_board.commands import AgentSlotConfig, CreateTeamCommand
from application.team_board.team_board_service import TeamBoardApplicationService
from infr.repository.project_repository_impl import ProjectRepositoryImpl
from ohs.http.api_response import ApiResponse
from ohs.http.dto.project_dto import (
    CompletePluginInitRequest,
    CreateProjectRequest,
    EnsureProjectsRequest,
    EnsureProjectsResponse,
    GitBranchesResponse,
    GitCheckoutRequest,
    GitCheckoutResponse,
    InitPluginRequest,
    PickDirectoryResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectResponse,
    ReorderProjectsRequest,
    ResetPluginRequest,
    WorkspaceFileContentResponse,
    WorkspaceFileDiffResponse,
    WorkspaceExportRequest,
    WorkspaceFileAtRefResponse,
    WorkspaceFileHistoryItemResponse,
    WorkspaceFileHistoryResponse,
    WorkspaceFileItemResponse,
    WorkspaceFileListResponse,
)

router = APIRouter(prefix="/api/projects", tags=["Project"])

ServiceDep = Annotated[
    ProjectApplicationService,
    Depends(get_project_application_service),
]

WorkspaceDep = Annotated[
    WorkspaceApplicationService,
    Depends(get_workspace_application_service),
]

PluginInitDep = Annotated[
    PluginInitApplicationService,
    Depends(get_plugin_init_application_service),
]

ProjectRepoDep = Annotated[ProjectRepositoryImpl, Depends(get_project_repository)]
TeamBoardDep = Annotated[TeamBoardApplicationService, Depends(get_team_board_service)]


class CreateTeamProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dir_path: str = Field(default="", max_length=512)
    team_config: dict[str, Any] = Field(default_factory=dict)


@router.post("/teams", summary="Create a team project and its board")
async def create_team_project(
    request: CreateTeamProjectRequest,
    project_repo: ProjectRepoDep,
    team_service: TeamBoardDep,
) -> ApiResponse[ProjectResponse]:
    dir_path = request.dir_path.strip() if request.dir_path else ""
    if not dir_path:
        teams_root = os.path.expanduser("~/.velpos/teams")
        dir_path = os.path.join(teams_root, request.name.strip())
    os.makedirs(dir_path, exist_ok=True)

    config = dict(request.team_config)
    items = config.get("pipeline") or config.get("members") or config.get("slots") or []
    slots = []
    for index, item in enumerate(items, start=1):
        profile = item.get("agent_profile_id") or item.get("agent_id") or item.get("role") or item.get("project_id")
        if not profile:
            continue
        slots.append(AgentSlotConfig(
            display_name=item.get("role_label") or item.get("display_name") or item.get("role") or f"Agent {index}",
            agent_profile_id=profile,
            slug=item.get("slug") or f"agent-{index}",
        ))
    if not slots:
        raise HTTPException(status_code=422, detail="Team must have at least one agent slot")
    project = Project.create(request.name.strip(), dir_path, project_type="team")
    await project_repo.save(project)
    try:
        team = await team_service.create_team(CreateTeamCommand(
            name=project.name, project_id=project.id, root_path=project.dir_path, slots=tuple(slots)
        ))
    except Exception:
        await project_repo.remove(project.id)
        raise
    config["team_id"] = team.id
    config["slots"] = [
        {"display_name": slot.display_name, "agent_profile_id": slot.agent_profile_id, "slug": slot.slug}
        for slot in slots
    ]
    project.update_team_config(config)
    await project_repo.save(project)
    # The frontend opens the board as soon as this response arrives. Commit
    # before returning so that request cannot race the dependency finalizer.
    await project_repo.commit()
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.post("", summary="Create project")
async def create_project(
    request: CreateProjectRequest,
    service: ServiceDep,
) -> ApiResponse[ProjectResponse]:
    command = CreateProjectCommand(name=request.name, github_url=request.github_url)
    project = await service.create_project(command)
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.get("", summary="List projects")
async def list_projects(
    service: ServiceDep,
) -> ApiResponse[ProjectListResponse]:
    projects = await service.list_projects()
    return ApiResponse.success(ProjectListResponse.from_domain_list(projects))


@router.get("/{project_id}", summary="Get project detail")
async def get_project(
    project_id: str,
    service: ServiceDep,
) -> ApiResponse[ProjectDetailResponse]:
    project = await service.get_project(project_id)
    # Get sessions for this project
    sessions = await service.get_sessions_by_project(project_id)
    session_dicts = [SessionAssembler.to_summary(s) for s in sessions]
    return ApiResponse.success(
        ProjectDetailResponse.from_domain(project, session_dicts)
    )


@router.delete("/{project_id}", summary="Delete project")
async def delete_project(
    project_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_project(project_id)
    return ApiResponse.success()


@router.patch("/reorder", summary="Reorder projects")
async def reorder_projects(
    request: ReorderProjectsRequest,
    service: ServiceDep,
) -> ApiResponse[None]:
    command = ReorderProjectsCommand(ordered_ids=request.ordered_ids)
    await service.reorder_projects(command)
    return ApiResponse.success()


@router.post("/ensure-by-dirs", summary="Ensure projects exist for given directories")
async def ensure_projects_by_dirs(
    request: EnsureProjectsRequest,
    service: ServiceDep,
) -> ApiResponse[EnsureProjectsResponse]:
    mappings = await service.ensure_projects_for_dirs(request.dir_paths)
    return ApiResponse.success(EnsureProjectsResponse(mappings=mappings))


@router.post("/pick-directory", summary="Pick a local directory")
async def pick_directory(
    service: ServiceDep,
) -> ApiResponse[PickDirectoryResponse]:
    dir_path = await service.pick_directory()
    return ApiResponse.success(PickDirectoryResponse(dir_path=dir_path))


@router.post("/{project_id}/init-plugin", summary="Initialize plugin for project")
async def init_plugin(
    project_id: str,
    request: InitPluginRequest,
    service: PluginInitDep,
) -> ApiResponse[ProjectResponse]:
    command = InitPluginCommand(
        project_id=project_id,
        plugin_type=request.plugin_type,
        session_id=request.session_id,
    )
    project = await service.init_plugin(command)
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.post("/{project_id}/complete-plugin-init", summary="Complete plugin init")
async def complete_plugin_init(
    project_id: str,
    request: CompletePluginInitRequest,
    service: PluginInitDep,
) -> ApiResponse[ProjectResponse]:
    project = await service.complete_plugin_init(project_id, request.plugin_type)
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.post("/{project_id}/reset-plugin", summary="Uninstall plugin")
async def reset_plugin(
    project_id: str,
    request: ResetPluginRequest,
    service: PluginInitDep,
) -> ApiResponse[ProjectResponse]:
    project = await service.reset_plugin(project_id, request.plugin_type)
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.get("/{project_id}/workspace/files", summary="List project workspace files")
async def list_workspace_files(
    project_id: str,
    service: WorkspaceDep,
    changed_only: bool = Query(default=False),
    keyword: str = Query(default="", max_length=200),
) -> ApiResponse[WorkspaceFileListResponse]:
    files = await service.list_workspace_files(project_id, changed_only, keyword)
    return ApiResponse.success(WorkspaceFileListResponse(
        files=[WorkspaceFileItemResponse(**item) for item in files],
    ))


@router.get("/{project_id}/workspace/file", summary="Read project workspace file")
async def read_workspace_file(
    project_id: str,
    service: WorkspaceDep,
    path: str = Query(..., min_length=1, max_length=1000),
) -> ApiResponse[WorkspaceFileContentResponse]:
    data = await service.read_workspace_file(project_id, path)
    return ApiResponse.success(WorkspaceFileContentResponse(**data))


@router.get("/{project_id}/workspace/file-raw", summary="Serve raw workspace file")
async def read_workspace_file_raw(
    project_id: str,
    service: WorkspaceDep,
    path: str = Query(..., min_length=1, max_length=1000),
):
    file_path = await service.read_workspace_file_raw(project_id, path)
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=file_path.name,
    )


@router.get("/{project_id}/workspace/diff", summary="Get project workspace file diff")
async def get_workspace_diff(
    project_id: str,
    service: WorkspaceDep,
    path: str = Query(..., min_length=1, max_length=1000),
) -> ApiResponse[WorkspaceFileDiffResponse]:
    data = await service.get_workspace_diff(project_id, path)
    return ApiResponse.success(WorkspaceFileDiffResponse(**data))


@router.get("/{project_id}/workspace/file-history", summary="List project workspace file history")
async def list_workspace_file_history(
    project_id: str,
    service: WorkspaceDep,
    path: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[WorkspaceFileHistoryResponse]:
    commits = await service.list_workspace_file_history(project_id, path, limit)
    return ApiResponse.success(WorkspaceFileHistoryResponse(
        commits=[WorkspaceFileHistoryItemResponse(**item) for item in commits],
    ))


@router.get("/{project_id}/workspace/file-at-ref", summary="Read project workspace file at git ref")
async def read_workspace_file_at_ref(
    project_id: str,
    service: WorkspaceDep,
    path: str = Query(..., min_length=1, max_length=1000),
    ref: str = Query(..., min_length=1, max_length=80),
) -> ApiResponse[WorkspaceFileAtRefResponse]:
    data = await service.read_workspace_file_at_ref(project_id, path, ref)
    return ApiResponse.success(WorkspaceFileAtRefResponse(**data))


@router.post("/{project_id}/workspace/export", summary="Export selected workspace files")
async def export_workspace_selection(
    project_id: str,
    request: WorkspaceExportRequest,
    service: WorkspaceDep,
) -> StreamingResponse:
    filename, content = await service.export_workspace_selection(project_id, request.paths)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/git/branches", summary="List git branches")
async def list_git_branches(
    project_id: str,
    service: ServiceDep,
) -> ApiResponse[GitBranchesResponse]:
    result = await service.list_git_branches(project_id)
    return ApiResponse.success(GitBranchesResponse(**result))


@router.post("/{project_id}/git/checkout", summary="Checkout git branch")
async def checkout_git_branch(
    project_id: str,
    request: GitCheckoutRequest,
    service: ServiceDep,
) -> ApiResponse[GitCheckoutResponse]:
    current = await service.checkout_git_branch(project_id, request.branch)
    return ApiResponse.success(GitCheckoutResponse(current=current))
