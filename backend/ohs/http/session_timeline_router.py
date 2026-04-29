from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.session.session_application_service import SessionApplicationService
from application.session.session_run_timeline_service import SessionRunTimelineService
from ohs.dependencies import get_session_application_service, get_session_run_timeline_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/sessions", tags=["Session Timeline"])

TimelineServiceDep = Annotated[
    SessionRunTimelineService,
    Depends(get_session_run_timeline_service),
]
SessionServiceDep = Annotated[
    SessionApplicationService,
    Depends(get_session_application_service),
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


@router.get("/{session_id}/timeline-events", summary="List session timeline events")
async def list_session_timeline_events(
    session_id: str,
    service: SessionServiceDep,
    limit: int = 500,
    event_types: str = "",
) -> ApiResponse[dict]:
    filters = [item.strip() for item in event_types.split(",") if item.strip()]
    events = await service.list_timeline_events(session_id, limit=limit, event_types=filters or None)
    return ApiResponse.success({
        "session_id": session_id,
        "events": events,
    })


@router.get("/{session_id}/runs/{run_id}/timeline-events", summary="List session run timeline events")
async def list_session_run_timeline_events(
    session_id: str,
    run_id: str,
    service: SessionServiceDep,
) -> ApiResponse[dict]:
    events = await service.list_run_timeline_events(session_id, run_id)
    return ApiResponse.success({
        "session_id": session_id,
        "run_id": run_id,
        "events": events,
    })
