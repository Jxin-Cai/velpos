from __future__ import annotations

import asyncio

import pytest

from ohs.scheduler_runner import ExecutionWatchdogRunner


@pytest.mark.asyncio
async def test_runs_initial_recovery_in_background_with_terminal_grace_disabled() -> None:
    # Arrange
    runner = ExecutionWatchdogRunner(interval_seconds=3600)
    called = asyncio.Event()
    release = asyncio.Event()
    received_flags: list[bool] = []

    async def fake_run_once(
        *,
        ignore_terminal_session_grace: bool = False,
    ) -> list[str]:
        received_flags.append(ignore_terminal_session_grace)
        called.set()
        await release.wait()
        return []

    runner.run_once = fake_run_once  # type: ignore[method-assign]

    # Act
    runner.start(ignore_terminal_session_grace_on_first_run=True)
    await asyncio.wait_for(called.wait(), timeout=1)
    startup_was_not_blocked = runner._task is not None and not runner._task.done()
    release.set()
    await runner.stop()

    # Assert
    assert startup_was_not_blocked is True
    assert received_flags == [True]
