from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.session.command.clear_context_command import ClearContextCommand
from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.import_claude_session_command import ImportClaudeSessionCommand
from application.session.session_application_service import SessionApplicationService
from application.im_binding.im_channel_application_service import ImChannelApplicationService
from ohs.dependencies import get_session_application_service, get_im_channel_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.session_dto import (
    BatchDeleteRequest,
    CreateSessionRequest,
    ImportClaudeSessionRequest,
    RenameSessionRequest,
    SessionArtifactListResponse,
    SessionAuditEventListResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["Session"])

ServiceDep = Annotated[
    SessionApplicationService,
    Depends(get_session_application_service),
]
ImServiceDep = Annotated[
    ImChannelApplicationService,
    Depends(get_im_channel_application_service),
]


@router.post("", summary="Create session")
async def create_session(
    request: CreateSessionRequest,
    service: ServiceDep,
) -> ApiResponse[SessionResponse]:
    command = CreateSessionCommand(
        model=request.model,
        project_id=request.project_id,
        project_dir=request.project_dir,
        name=request.name,
    )
    session = await service.create_session(command)
    return ApiResponse.success(SessionResponse.from_domain(session))


@router.post("/import-claude", summary="Import Claude Code session")
async def import_claude_session(
    request: ImportClaudeSessionRequest,
    service: ServiceDep,
) -> ApiResponse[SessionResponse]:
    command = ImportClaudeSessionCommand(
        claude_session_id=request.claude_session_id,
        cwd=request.cwd,
        name=request.name,
    )
    session = await service.import_claude_session(command)
    return ApiResponse.success(SessionResponse.from_domain(session))


@router.post("/batch-delete", summary="Batch delete sessions")
async def batch_delete_sessions(
    request: BatchDeleteRequest,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.batch_delete_sessions(request.session_ids)
    return ApiResponse.success()


@router.get("", summary="List sessions")
async def list_sessions(
    service: ServiceDep,
    im_service: ImServiceDep,
) -> ApiResponse[SessionListResponse]:
    sessions = await service.list_sessions()
    bindings = await im_service.list_all_bindings()
    binding_map = {b["session_id"]: b for b in bindings}
    return ApiResponse.success(SessionListResponse.from_domain_list(sessions, binding_map))


# Static paths MUST come before /{session_id} dynamic routes
@router.get("/meta/models", summary="List available models")
async def list_models(
    service: ServiceDep,
) -> ApiResponse[list]:
    models = await service.get_models()
    return ApiResponse.success(models)


@router.get("/{session_id}", summary="Get session detail")
async def get_session(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[SessionDetailResponse]:
    session = await service.get_session(session_id)
    return ApiResponse.success(SessionDetailResponse.from_domain(session))


@router.get("/{session_id}/artifacts", summary="List session artifacts")
async def list_session_artifacts(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[SessionArtifactListResponse]:
    artifacts = await service.list_artifacts(session_id)
    return ApiResponse.success(SessionArtifactListResponse.from_dict_list(artifacts))


@router.get("/{session_id}/audit-events", summary="List session audit events")
async def list_session_audit_events(
    session_id: str,
    service: ServiceDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> ApiResponse[SessionAuditEventListResponse]:
    events = await service.list_audit_events(session_id, limit=limit)
    return ApiResponse.success(SessionAuditEventListResponse.from_domain_list(events))


@router.delete("/{session_id}", summary="Delete session")
async def delete_session(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_session(session_id)
    return ApiResponse.success()


@router.patch("/{session_id}/name", summary="Rename session")
async def rename_session(
    session_id: str,
    request: RenameSessionRequest,
    service: ServiceDep,
) -> ApiResponse[SessionResponse]:
    session = await service.rename_session(session_id, request.name)
    return ApiResponse.success(SessionResponse.from_domain(session))


@router.post("/{session_id}/clear-context", summary="Clear session context")
async def clear_context(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    command = ClearContextCommand(session_id=session_id)
    await service.clear_context(command)
    return ApiResponse.success()


@router.post("/{session_id}/compact", summary="Compact session context")
async def compact_session(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.compact_session(session_id)
    return ApiResponse.success()

