from __future__ import annotations

from dataclasses import dataclass

from domain.session.model.trace_span import TraceSpan
from domain.session.repository.session_repository import SessionRepository
from domain.session.repository.session_run_step_repository import SessionRunStepRepository
from domain.session.repository.trace_span_repository import TraceSpanRepository


@dataclass(frozen=True)
class InterruptedRunRecoveryResult:
    session_count: int = 0
    step_count: int = 0
    span_count: int = 0


class InterruptedRunRecoveryService:
    """Close persisted work that cannot survive a backend process restart."""

    def __init__(
        self,
        session_repository: SessionRepository,
        run_step_repository: SessionRunStepRepository,
        trace_span_repository: TraceSpanRepository,
    ) -> None:
        self._session_repository = session_repository
        self._run_step_repository = run_step_repository
        self._trace_span_repository = trace_span_repository

    async def recover(self) -> InterruptedRunRecoveryResult:
        session_count = 0

        for session in await self._session_repository.find_all():
            if not session.is_running:
                continue

            session.fail_query()
            await self._session_repository.save(session)
            session_count += 1

        running_steps = await self._run_step_repository.find_running()
        for step in running_steps:
            step.fail({"error": "Backend process restarted during execution"})
            await self._run_step_repository.save(step)

        running_spans: list[TraceSpan] = (
            await self._trace_span_repository.find_running()
        )
        for span in running_spans:
            span.abandon("Backend process restarted during execution")
        if running_spans:
            await self._trace_span_repository.update_batch(running_spans)

        return InterruptedRunRecoveryResult(
            session_count=session_count,
            step_count=len(running_steps),
            span_count=len(running_spans),
        )
