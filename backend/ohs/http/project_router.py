from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.project.command.create_project_command import CreateProjectCommand
from application.project.command.init_plugin_command import InitPluginCommand
from application.project.command.reorder_projects_command import ReorderProjectsCommand
from application.project.project_application_service import ProjectApplicationService
from ohs.assembler.session_assembler import SessionAssembler
from ohs.dependencies import get_project_application_service
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
)

router = APIRouter(prefix="/api/projects", tags=["Project"])

ServiceDep = Annotated[
    ProjectApplicationService,
    Depends(get_project_application_service),
]


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
    service: ServiceDep,
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
    service: ServiceDep,
) -> ApiResponse[ProjectResponse]:
    project = await service.complete_plugin_init(project_id, request.plugin_type)
    return ApiResponse.success(ProjectResponse.from_domain(project))


@router.post("/{project_id}/reset-plugin", summary="Uninstall plugin")
async def reset_plugin(
    project_id: str,
    request: ResetPluginRequest,
    service: ServiceDep,
) -> ApiResponse[ProjectResponse]:
    project = await service.reset_plugin(project_id, request.plugin_type)
    return ApiResponse.success(ProjectResponse.from_domain(project))


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
