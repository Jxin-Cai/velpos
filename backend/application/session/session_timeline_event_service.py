from __future__ import annotations

from typing import Any

from domain.session.acl.connection_manager import ConnectionManager
from domain.session.model.session_timeline_event import SessionTimelineEvent
from domain.session.repository.session_timeline_event_repository import SessionTimelineEventRepository


class SessionTimelineEventService:

    def __init__(
        self,
        repository: SessionTimelineEventRepository,
        connection_manager: ConnectionManager | None = None,
    ) -> None:
        self._repository = repository
        self._connection_manager = connection_manager

    async def record_event(
        self,
        session_id: str,
        run_id: str,
        event_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        status: str = "completed",
        *,
        commit: bool = False,
        emit: bool = True,
    ) -> SessionTimelineEvent:
        seq = await self._repository.next_seq(session_id, run_id)
        event = SessionTimelineEvent.create(
            session_id=session_id,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            title=title,
            payload=payload,
            status=status,
        )
        await self._repository.save(event)
        if commit:
            await self._repository.commit()
        if emit and self._connection_manager is not None:
            await self._connection_manager.broadcast(
                session_id,
                {"event": "timeline_event", "timeline_event": self.event_to_dict(event)},
            )
        return event

    async def list_events(
        self,
        session_id: str,
        limit: int = 500,
        event_types: list[str] | None = None,
    ) -> list[SessionTimelineEvent]:
        return await self._repository.find_by_session_id(session_id, limit, event_types)

    async def list_run_events(self, session_id: str, run_id: str) -> list[SessionTimelineEvent]:
        return await self._repository.find_by_run_id(session_id, run_id)

    @staticmethod
    def event_to_dict(event: SessionTimelineEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "session_id": event.session_id,
            "run_id": event.run_id,
            "seq": event.seq,
            "event_type": event.event_type,
            "status": event.status,
            "title": event.title,
            "payload": event.payload,
            "started_time": event.started_time.isoformat(),
            "ended_time": event.ended_time.isoformat() if event.ended_time else None,
            "duration_ms": event.duration_ms,
            "created_time": event.created_time.isoformat(),
        }
