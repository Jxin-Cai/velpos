from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.session.session_run_timeline_service import SessionRunTimelineService
from ohs.dependencies import get_session_run_timeline_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/sessions", tags=["Session Timeline"])

TimelineServiceDep = Annotated[
    SessionRunTimelineService,
    Depends(get_session_run_timeline_service),
]


@router.get("/{session_id}/runs/{run_id}/steps", summary="List session run steps")
async def list_session_run_steps(
    session_id: str,
    run_id: str,
    service: TimelineServiceDep,
) -> ApiResponse[dict]:
    steps = await service.list_steps(session_id, run_id)
    resolved_run_id = steps[0].run_id if steps else ""
    return ApiResponse.success({
        "session_id": session_id,
        "run_id": resolved_run_id,
        "steps": [service.step_to_dict(step) for step in steps],
    })
