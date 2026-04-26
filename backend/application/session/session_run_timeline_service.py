from __future__ import annotations

from typing import Any

from domain.session.model.session_run_step import SessionRunStep
from domain.session.repository.session_run_step_repository import SessionRunStepRepository
from domain.session.acl.connection_manager import ConnectionManager


class SessionRunTimelineService:

    def __init__(
        self,
        repository: SessionRunStepRepository,
        connection_manager: ConnectionManager | None = None,
    ) -> None:
        self._repository = repository
        self._connection_manager = connection_manager

    async def start_step(
        self,
        session_id: str,
        run_id: str,
        step_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = False,
    ) -> SessionRunStep:
        step = SessionRunStep.start(session_id, run_id, step_type, title, payload)
        await self._save_and_emit("run_step_started", step, commit=commit)
        return step

    async def progress_step(
        self,
        step: SessionRunStep,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = False,
    ) -> SessionRunStep:
        step.progress(payload)
        await self._save_and_emit("run_step_progress", step, commit=commit)
        return step

    async def complete_step(
        self,
        step: SessionRunStep,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = False,
    ) -> SessionRunStep:
        step.complete(payload)
        await self._save_and_emit("run_step_completed", step, commit=commit)
        return step

    async def fail_step(
        self,
        step: SessionRunStep,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = False,
    ) -> SessionRunStep:
        step.fail(payload)
        await self._save_and_emit("run_step_failed", step, commit=commit)
        return step

    async def list_steps(self, session_id: str, run_id: str) -> list[SessionRunStep]:
        resolved_run_id = run_id
        if run_id == "latest":
            resolved_run_id = await self._repository.find_latest_run_id(session_id)
        if not resolved_run_id:
            return []
        return await self._repository.find_by_run_id(session_id, resolved_run_id)

    async def _save_and_emit(self, event: str, step: SessionRunStep, *, commit: bool) -> None:
        await self._repository.save(step)
        if commit:
            await self._repository.commit()
        if self._connection_manager is not None:
            await self._connection_manager.broadcast(
                step.session_id,
                {"event": event, "step": self.step_to_dict(step)},
            )

    @staticmethod
    def step_to_dict(step: SessionRunStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "session_id": step.session_id,
            "run_id": step.run_id,
            "step_type": step.step_type,
            "status": step.status,
            "title": step.title,
            "payload": step.payload,
            "started_time": step.started_time.isoformat(),
            "ended_time": step.ended_time.isoformat() if step.ended_time else None,
            "duration_ms": step.duration_ms,
        }
