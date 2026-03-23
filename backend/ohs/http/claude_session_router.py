from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.claude_session.claude_session_application_service import (
    ClaudeSessionApplicationService,
)
from ohs.dependencies import get_claude_session_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.claude_session_dto import (
    ClaudeSessionListResponse,
    RenameSessionRequest,
)

router = APIRouter(prefix="/api/claude-sessions", tags=["Claude Sessions"])

ServiceDep = Annotated[
    ClaudeSessionApplicationService,
    Depends(get_claude_session_application_service),
]


@router.get("", summary="List Claude Code sessions")
async def list_claude_sessions(
    service: ServiceDep,
    directory: str | None = Query(default=None, description="Project directory to filter by"),
    limit: int | None = Query(default=None, ge=1, description="Maximum sessions to return"),
) -> ApiResponse[ClaudeSessionListResponse]:
    sessions = service.list_claude_sessions(directory=directory, limit=limit)
    return ApiResponse.success(ClaudeSessionListResponse.from_dicts(sessions))


@router.post("/rename", summary="Rename a Claude Code session")
async def rename_claude_session(
    request: RenameSessionRequest,
    service: ServiceDep,
) -> ApiResponse[None]:
    service.rename_claude_session(
        session_id=request.session_id,
        title=request.title,
        directory=request.directory,
    )
    return ApiResponse.success()


@router.delete("/{session_id}", summary="Delete a Claude Code session")
async def delete_claude_session(
    session_id: str,
    service: ServiceDep,
    directory: str | None = Query(default=None, description="Project directory"),
) -> ApiResponse[None]:
    from domain.shared.business_exception import BusinessException

    success = service.delete_claude_session(
        session_id=session_id,
        directory=directory,
    )
    if not success:
        raise BusinessException("Claude session not found or delete failed")
    return ApiResponse.success()
