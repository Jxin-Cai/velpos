from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from application.message.attachment_application_service import AttachmentApplicationService
from ohs.dependencies import get_attachment_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(tags=["Attachments"])

ServiceDep = Annotated[
    AttachmentApplicationService,
    Depends(get_attachment_application_service),
]


@router.get("/api/sessions/{session_id}/attachments", summary="List session attachments")
async def list_session_attachments(session_id: str, service: ServiceDep) -> ApiResponse[dict]:
    return ApiResponse.success({"attachments": await service.list_session_attachments(session_id)})


@router.get("/api/attachments/{attachment_id}/download", summary="Download attachment")
async def download_attachment(attachment_id: str, service: ServiceDep) -> FileResponse:
    path, filename, mime_type = await service.get_download_path(attachment_id)
    return FileResponse(path, media_type=mime_type, filename=filename)
