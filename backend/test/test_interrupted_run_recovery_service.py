from unittest.mock import AsyncMock

import pytest

from application.session.interrupted_run_recovery_service import (
    InterruptedRunRecoveryService,
)
from domain.session.model.session import Session
from domain.session.model.session_run_step import SessionRunStep
from domain.session.model.trace_span import TraceSpan


@pytest.mark.asyncio
async def test_marks_persisted_work_terminal_when_backend_restarted() -> None:
    # Arrange
    session = Session.create(model="default")
    session.start_query()
    run_step = SessionRunStep.start(
        session_id=session.session_id,
        run_id="run-1",
        step_type="run",
        title="Agent run",
    )
    trace_span = TraceSpan.create(
        session_id=session.session_id,
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_RUN,
        name="Agent run",
    )
    session_repository = AsyncMock()
    session_repository.find_all.return_value = [session]
    run_step_repository = AsyncMock()
    run_step_repository.find_running.return_value = [run_step]
    trace_span_repository = AsyncMock()
    trace_span_repository.find_running.return_value = [trace_span]
    service = InterruptedRunRecoveryService(
        session_repository=session_repository,
        run_step_repository=run_step_repository,
        trace_span_repository=trace_span_repository,
    )

    # Act
    result = await service.recover()

    # Assert
    assert session.status.value == "error"
    assert run_step.status == "failed"
    assert trace_span.status == TraceSpan.STATUS_ABANDONED
    assert result.session_count == 1
    assert result.step_count == 1
    assert result.span_count == 1
