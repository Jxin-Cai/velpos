from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from application.message.attachment_application_service import AttachmentApplicationService
from application.session.session_application_service import SessionApplicationService
from domain.shared.business_exception import BusinessException
from ohs.dependencies import (
    get_attachment_application_service,
    get_session_application_service,
)
from ohs.http.api_response import ApiResponse

router = APIRouter(tags=["Attachments"])

ServiceDep = Annotated[
    AttachmentApplicationService,
    Depends(get_attachment_application_service),
]
SessionServiceDep = Annotated[
    SessionApplicationService,
    Depends(get_session_application_service),
]


def _inline_image_response(path: str, mime_type: str) -> FileResponse:
    return FileResponse(
        path,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/sessions/{session_id}/attachments", summary="List session attachments")
async def list_session_attachments(session_id: str, service: ServiceDep) -> ApiResponse[dict]:
    return ApiResponse.success({"attachments": await service.list_session_attachments(session_id)})


@router.get(
    "/api/sessions/{session_id}/attachments/preview",
    summary="Preview a persisted session image",
)
async def preview_session_attachment(
    session_id: str,
    service: ServiceDep,
    session_service: SessionServiceDep,
    path: str = Query(..., min_length=1, max_length=1000),
) -> FileResponse:
    session = await session_service.get_session(session_id)
    attachment_ref = next(
        (
            attachment
            for message in session.messages
            for attachment in message.content.get("attachments", [])
            if isinstance(attachment, dict) and attachment.get("path") == path
        ),
        None,
    )
    if attachment_ref is None:
        raise BusinessException(
            "Attachment is not referenced by this session",
            "ATTACHMENT_REFERENCE_NOT_FOUND",
        )
    file_path, mime_type = service.get_workspace_preview_path(
        session.project_dir,
        path,
        str(attachment_ref.get("mime_type") or "application/octet-stream"),
    )
    return _inline_image_response(file_path, mime_type)


@router.get("/api/attachments/{attachment_id}/download", summary="Download attachment")
async def download_attachment(attachment_id: str, service: ServiceDep) -> FileResponse:
    path, filename, mime_type = await service.get_download_path(attachment_id)
    return FileResponse(path, media_type=mime_type, filename=filename)


@router.get("/api/attachments/{attachment_id}/preview", summary="Preview attachment")
async def preview_attachment(attachment_id: str, service: ServiceDep) -> FileResponse:
    path, _filename, mime_type = await service.get_download_path(attachment_id)
    if not mime_type.startswith("image/"):
        raise BusinessException(
            "Only image attachments support inline preview",
            "ATTACHMENT_PREVIEW_UNSUPPORTED",
        )
    return _inline_image_response(path, mime_type)
