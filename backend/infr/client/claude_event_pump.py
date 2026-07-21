from __future__ import annotations

import asyncio
import collections
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator, Callable

from claude_agent_sdk.types import (
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
)

logger = logging.getLogger(__name__)


class TurnPhase(StrEnum):
    STREAMING = "streaming"
    SETTLING_RESULT = "settling_result"
    WAITING_BACKGROUND = "waiting_background"
    AWAITING_FINAL_RESULT = "awaiting_final_result"
    INTERRUPTED = "interrupted"
    TERMINAL = "terminal"


class BackgroundTaskState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class BackgroundTask:
    task_id: str
    state: BackgroundTaskState = BackgroundTaskState.RUNNING
    description: str = ""
    summary: str = ""


@dataclass(frozen=True)
class _TurnEnvelope:
    message: Any | None = None
    error: BaseException | None = None
    terminal: bool = False


@dataclass
class ResponseTurn:
    turn_id: int
    phase: TurnPhase = TurnPhase.STREAMING
    tasks: dict[str, BackgroundTask] = field(default_factory=dict)
    deferred_result: Any | None = None
    had_background_tasks: bool = False
    interrupted: bool = False
    _queue: asyncio.Queue[_TurnEnvelope] = field(default_factory=asyncio.Queue)
    _settle_timer: asyncio.Task[None] | None = None
    _completion_timer: asyncio.Task[None] | None = None
    _background_timer: asyncio.Task[None] | None = None

    @property
    def active_task_ids(self) -> tuple[str, ...]:
        return tuple(
            task_id
            for task_id, task in self.tasks.items()
            if task.state is BackgroundTaskState.RUNNING
        )

    async def messages(self) -> AsyncIterator[Any]:
        while True:
            envelope = await self._queue.get()
            if envelope.error is not None:
                raise envelope.error
            if envelope.terminal:
                return
            yield envelope.message


class ClaudeConnectionEventPump:
    """The single SDK message reader for one persistent Claude connection."""

    def __init__(
        self,
        session_id: str,
        client: Any,
        *,
        phase_changed: Callable[[TurnPhase], None] | None = None,
        result_settle_seconds: float = 0.1,
        final_result_timeout_seconds: float = 300.0,
        background_task_timeout_seconds: float = 3600.0,
    ) -> None:
        self._session_id = session_id
        self._client = client
        self._phase_changed = phase_changed
        self._result_settle_seconds = max(0.0, result_settle_seconds)
        self._final_result_timeout_seconds = max(0.001, final_result_timeout_seconds)
        self._background_task_timeout_seconds = max(0.001, background_task_timeout_seconds)
        self._lock = asyncio.Lock()
        self._active_turn: ResponseTurn | None = None
        self._next_turn_id = 1
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self._retired_task_ids: set[str] = set()
        self._retired_task_order: collections.deque[str] = collections.deque()
        self._max_retired_task_ids = 1000

    def start(self) -> None:
        if self._reader_task is not None:
            return
        self._reader_task = asyncio.create_task(
            self._run(),
            name=f"claude_event_pump_{self._session_id}",
        )

    async def begin_turn(self) -> ResponseTurn:
        async with self._lock:
            if self._closed:
                raise RuntimeError(f"Event pump is closed for session {self._session_id}")
            if self._active_turn is not None:
                raise RuntimeError(f"A Claude response is already active for session {self._session_id}")
            turn = ResponseTurn(turn_id=self._next_turn_id)
            self._next_turn_id += 1
            self._active_turn = turn
            self._change_phase_locked(turn, TurnPhase.STREAMING)
            return turn

    async def fail_turn(self, turn: ResponseTurn, error: BaseException) -> None:
        async with self._lock:
            if self._active_turn is not turn:
                return
            self._fail_turn_locked(turn, error)

    async def interrupt_turn(self) -> None:
        async with self._lock:
            turn = self._active_turn
            if turn is None:
                return
            turn.interrupted = True
            self._change_phase_locked(turn, TurnPhase.INTERRUPTED)

    async def abandon_turn(self, turn: ResponseTurn) -> None:
        async with self._lock:
            if self._active_turn is not turn:
                return
            self._fail_turn_locked(turn, asyncio.CancelledError())

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            turn = self._active_turn
            if turn is not None:
                self._fail_turn_locked(
                    turn,
                    ConnectionError(f"Claude connection closed for session {self._session_id}"),
                )
            reader_task = self._reader_task
            self._reader_task = None

        if reader_task is not None and reader_task is not asyncio.current_task():
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)

    async def _run(self) -> None:
        try:
            async for message in self._client.receive_messages():
                await self._route_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Claude event pump failed: session=%s",
                self._session_id,
                exc_info=True,
            )
            await self._fail_active_turn(exc)
        else:
            if not self._closed:
                await self._fail_active_turn(
                    ConnectionError(f"Claude message stream ended for session {self._session_id}"),
                )

    async def _fail_active_turn(self, error: BaseException) -> None:
        async with self._lock:
            if self._active_turn is not None:
                self._fail_turn_locked(self._active_turn, error)

    async def _route_message(self, message: Any) -> None:
        async with self._lock:
            turn = self._active_turn
            if turn is None:
                self._log_orphan_message(message)
                return

            if self._is_post_result_state_marker(message) and turn.phase is TurnPhase.SETTLING_RESULT:
                return

            if isinstance(message, TaskStartedMessage):
                if message.task_id in self._retired_task_ids:
                    self._log_stale_task_message(message)
                    return
                self._record_task_started_locked(turn, message)
                self._emit_locked(turn, message)
                return

            if isinstance(message, TaskProgressMessage):
                if message.task_id not in turn.tasks:
                    self._log_stale_task_message(message)
                    return
                self._record_task_progress_locked(turn, message)
                self._emit_locked(turn, message)
                return

            if isinstance(message, TaskNotificationMessage):
                if message.task_id not in turn.tasks:
                    self._log_stale_task_message(message)
                    return
                self._record_task_notification_locked(turn, message)
                self._emit_locked(turn, message)
                if not turn.active_task_ids and turn.deferred_result is not None:
                    self._change_phase_locked(turn, TurnPhase.AWAITING_FINAL_RESULT)
                    self._arm_completion_timer_locked(turn)
                return

            if self._is_result_message(message):
                self._record_result_locked(turn, message)
                return

            if turn.phase is TurnPhase.SETTLING_RESULT:
                self._cancel_timer(turn._settle_timer)
                turn._settle_timer = None
                self._change_phase_locked(turn, TurnPhase.AWAITING_FINAL_RESULT)
                self._arm_completion_timer_locked(turn)
            elif turn.phase is TurnPhase.AWAITING_FINAL_RESULT:
                self._arm_completion_timer_locked(turn)

            self._emit_locked(turn, message)

    def _record_task_started_locked(
        self,
        turn: ResponseTurn,
        message: TaskStartedMessage,
    ) -> None:
        if not message.task_id:
            return
        turn.had_background_tasks = True
        self._cancel_result_timers_locked(turn)
        turn.tasks[message.task_id] = BackgroundTask(
            task_id=message.task_id,
            description=message.description,
        )
        if turn.deferred_result is not None:
            self._change_phase_locked(turn, TurnPhase.WAITING_BACKGROUND)
        self._arm_background_timer_locked(turn)

    def _record_task_progress_locked(
        self,
        turn: ResponseTurn,
        message: TaskProgressMessage,
    ) -> None:
        if not message.task_id:
            return
        turn.had_background_tasks = True
        self._cancel_result_timers_locked(turn)
        task = turn.tasks.setdefault(
            message.task_id,
            BackgroundTask(task_id=message.task_id),
        )
        task.state = BackgroundTaskState.RUNNING
        if message.description:
            task.description = message.description
        if turn.deferred_result is not None:
            self._change_phase_locked(turn, TurnPhase.WAITING_BACKGROUND)
        self._arm_background_timer_locked(turn)

    def _record_task_notification_locked(
        self,
        turn: ResponseTurn,
        message: TaskNotificationMessage,
    ) -> None:
        if not message.task_id:
            return
        turn.had_background_tasks = True
        self._cancel_result_timers_locked(turn)
        task = turn.tasks.setdefault(
            message.task_id,
            BackgroundTask(task_id=message.task_id),
        )
        try:
            task.state = BackgroundTaskState(message.status)
        except ValueError:
            task.state = BackgroundTaskState.FAILED
        task.summary = message.summary
        if not turn.active_task_ids:
            self._cancel_timer(turn._background_timer)
            turn._background_timer = None

    def _record_result_locked(self, turn: ResponseTurn, message: Any) -> None:
        if getattr(message, "is_error", False) or turn.interrupted:
            self._finalize_with_result_locked(turn, message)
            return

        if turn.active_task_ids:
            turn.deferred_result = message
            self._change_phase_locked(turn, TurnPhase.WAITING_BACKGROUND)
            self._arm_background_timer_locked(turn)
            return

        if turn.had_background_tasks:
            self._finalize_with_result_locked(turn, message)
            return

        turn.deferred_result = message
        self._change_phase_locked(turn, TurnPhase.SETTLING_RESULT)
        self._arm_settle_timer_locked(turn)

    def _arm_settle_timer_locked(self, turn: ResponseTurn) -> None:
        self._cancel_timer(turn._settle_timer)
        turn._settle_timer = asyncio.create_task(
            self._finalize_deferred_after(
                turn,
                self._result_settle_seconds,
                expected_phase=TurnPhase.SETTLING_RESULT,
            ),
            name=f"claude_result_settle_{self._session_id}_{turn.turn_id}",
        )

    def _arm_completion_timer_locked(self, turn: ResponseTurn) -> None:
        self._cancel_timer(turn._completion_timer)
        turn._completion_timer = asyncio.create_task(
            self._finalize_deferred_after(
                turn,
                self._final_result_timeout_seconds,
                expected_phase=TurnPhase.AWAITING_FINAL_RESULT,
            ),
            name=f"claude_final_result_timeout_{self._session_id}_{turn.turn_id}",
        )

    def _arm_background_timer_locked(self, turn: ResponseTurn) -> None:
        if turn._background_timer is not None:
            return
        turn._background_timer = asyncio.create_task(
            self._fail_background_tasks_after(turn),
            name=f"claude_background_timeout_{self._session_id}_{turn.turn_id}",
        )

    async def _finalize_deferred_after(
        self,
        turn: ResponseTurn,
        delay: float,
        *,
        expected_phase: TurnPhase,
    ) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            async with self._lock:
                if self._active_turn is not turn or turn.phase is not expected_phase:
                    return
                if turn.deferred_result is None or turn.active_task_ids:
                    return
                logger.info(
                    "Finalizing Claude turn with deferred result: session=%s turn=%d phase=%s",
                    self._session_id,
                    turn.turn_id,
                    turn.phase.value,
                )
                self._finalize_with_result_locked(turn, turn.deferred_result)
        except asyncio.CancelledError:
            raise

    async def _fail_background_tasks_after(self, turn: ResponseTurn) -> None:
        try:
            await asyncio.sleep(self._background_task_timeout_seconds)
            async with self._lock:
                if self._active_turn is not turn or not turn.active_task_ids:
                    return
                task_ids = list(turn.active_task_ids)
                logger.error(
                    "Claude background tasks timed out: session=%s turn=%d tasks=%s",
                    self._session_id,
                    turn.turn_id,
                    task_ids,
                )
                for task_id in task_ids:
                    task = turn.tasks[task_id]
                    task.state = BackgroundTaskState.FAILED
                    task.summary = "Background task timed out before reporting completion."
                    self._emit_locked(turn, {
                        "type": "system",
                        "subtype": "task_notification",
                        "task_id": task_id,
                        "status": "failed",
                        "summary": task.summary,
                        "session_id": self._session_id,
                    })
                self._finalize_with_result_locked(turn, {
                    "type": "result",
                    "is_error": True,
                    "result": "Claude background task timed out.",
                    "stop_reason": "background_task_timeout",
                    "usage": {},
                    "session_id": self._session_id,
                })
        except asyncio.CancelledError:
            raise

    def _finalize_with_result_locked(self, turn: ResponseTurn, result: Any) -> None:
        self._cancel_all_timers_locked(turn)
        self._retire_tasks_locked(turn)
        self._emit_locked(turn, result)
        turn._queue.put_nowait(_TurnEnvelope(terminal=True))
        self._change_phase_locked(turn, TurnPhase.TERMINAL)
        if self._active_turn is turn:
            self._active_turn = None

    def _fail_turn_locked(self, turn: ResponseTurn, error: BaseException) -> None:
        self._cancel_all_timers_locked(turn)
        self._retire_tasks_locked(turn)
        turn._queue.put_nowait(_TurnEnvelope(error=error))
        self._change_phase_locked(turn, TurnPhase.TERMINAL)
        if self._active_turn is turn:
            self._active_turn = None

    def _emit_locked(self, turn: ResponseTurn, message: Any) -> None:
        turn._queue.put_nowait(_TurnEnvelope(message=message))

    def _change_phase_locked(self, turn: ResponseTurn, phase: TurnPhase) -> None:
        if turn.phase is phase and phase is not TurnPhase.STREAMING:
            return
        turn.phase = phase
        if self._phase_changed is not None:
            self._phase_changed(phase)

    def _cancel_result_timers_locked(self, turn: ResponseTurn) -> None:
        self._cancel_timer(turn._settle_timer)
        self._cancel_timer(turn._completion_timer)
        turn._settle_timer = None
        turn._completion_timer = None

    def _cancel_all_timers_locked(self, turn: ResponseTurn) -> None:
        self._cancel_result_timers_locked(turn)
        self._cancel_timer(turn._background_timer)
        turn._background_timer = None

    def _retire_tasks_locked(self, turn: ResponseTurn) -> None:
        for task_id in turn.tasks:
            if task_id in self._retired_task_ids:
                continue
            self._retired_task_ids.add(task_id)
            self._retired_task_order.append(task_id)
        while len(self._retired_task_order) > self._max_retired_task_ids:
            expired_task_id = self._retired_task_order.popleft()
            self._retired_task_ids.discard(expired_task_id)

    @staticmethod
    def _cancel_timer(timer: asyncio.Task[None] | None) -> None:
        if timer is not None and timer is not asyncio.current_task() and not timer.done():
            timer.cancel()

    @staticmethod
    def _is_result_message(message: Any) -> bool:
        if isinstance(message, dict):
            return (message.get("message_type") or message.get("type")) in {
                "result",
                "ResultMessage",
            }
        return isinstance(message, ResultMessage) or message.__class__.__name__ == "ResultMessage"

    @staticmethod
    def _is_post_result_state_marker(message: Any) -> bool:
        return (
            isinstance(message, SystemMessage)
            and getattr(message, "subtype", "") == "session_state_changed"
        )

    def _log_orphan_message(self, message: Any) -> None:
        message_type = message.__class__.__name__
        subtype = getattr(message, "subtype", "")
        if isinstance(message, dict):
            message_type = str(message.get("type") or message.get("message_type") or "dict")
            subtype = str(message.get("subtype") or "")
        logger.info(
            "Dropped SDK message without an active turn: session=%s type=%s subtype=%s",
            self._session_id,
            message_type,
            subtype,
        )

    def _log_stale_task_message(self, message: Any) -> None:
        logger.info(
            "Dropped stale or unowned Claude task event: session=%s type=%s task_id=%s",
            self._session_id,
            message.__class__.__name__,
            getattr(message, "task_id", ""),
        )
