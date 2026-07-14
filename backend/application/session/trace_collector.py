from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from domain.session.model.trace_span import TraceSpan
from domain.session.repository.trace_span_repository import TraceSpanRepository

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL = float(os.getenv("VELPOS_TRACE_FLUSH_INTERVAL", "1.0"))
_TRACE_ENABLED = os.getenv("VELPOS_TRACE_ENABLED", "true").lower() in ("1", "true", "yes")


class TraceCollector:

    def __init__(
        self,
        repository: TraceSpanRepository | None = None,
        repository_factory: Callable[[], AbstractAsyncContextManager[TraceSpanRepository]] | None = None,
        broadcast_fn: Any = None,
        flush_interval: float = _FLUSH_INTERVAL,
    ) -> None:
        if repository is None and repository_factory is None:
            raise ValueError("repository or repository_factory is required")
        self._repository = repository
        self._repository_factory = repository_factory
        self._broadcast_fn = broadcast_fn
        self._flush_interval = flush_interval
        self._enabled = _TRACE_ENABLED

        self._buffer: dict[str, TraceSpan] = {}
        self._dirty_new: set[str] = set()
        self._dirty_update: set[str] = set()
        self._pending_broadcasts: list[tuple[str, str, dict[str, Any]]] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = loop.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()

    def _ensure_started(self) -> None:
        if self._flush_task is None or self._flush_task.done():
            self.start()

    def create_span(
        self,
        session_id: str,
        run_id: str,
        span_type: str,
        name: str,
        parent_span_id: str | None = None,
        agent_id: str | None = None,
        tool_use_id: str | None = None,
        input_preview: str | None = None,
        output_preview: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self._enabled:
            return None
        self._ensure_started()
        span = TraceSpan.create(
            session_id=session_id,
            run_id=run_id,
            span_type=span_type,
            name=name,
            parent_span_id=parent_span_id,
            agent_id=agent_id,
            tool_use_id=tool_use_id,
            input_preview=input_preview,
            output_preview=output_preview,
            metadata=metadata,
        )
        self._buffer[span.id] = span
        self._dirty_new.add(span.id)
        self._pending_broadcasts.append((session_id, "created", span.to_dict()))
        return span.id

    def complete_span(
        self,
        span_id: str,
        output_preview: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from application.session.trace_redaction import sanitize_and_truncate

        span = self._buffer.get(span_id)
        if span is None:
            return
        span.complete(output_preview=output_preview, metadata=metadata)
        self._dirty_update.add(span_id)
        self._pending_broadcasts.append((span.session_id, "completed", span.to_dict()))

    def fail_span(
        self,
        span_id: str,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        span = self._buffer.get(span_id)
        if span is None:
            return
        span.fail(error=sanitize_and_truncate(error, max_chars=500), metadata=metadata)
        self._dirty_update.add(span_id)
        self._pending_broadcasts.append((span.session_id, "failed", span.to_dict()))

    def deny_span(self, span_id: str, reason: str | None = None) -> None:
        from application.session.trace_redaction import sanitize_and_truncate

        span = self._buffer.get(span_id)
        if span is None:
            return
        span.deny(reason=sanitize_and_truncate(reason, max_chars=500))
        self._dirty_update.add(span_id)
        self._pending_broadcasts.append((span.session_id, "denied", span.to_dict()))

    def cancel_span(self, span_id: str, reason: str | None = None) -> None:
        from application.session.trace_redaction import sanitize_and_truncate

        span = self._buffer.get(span_id)
        if span is None:
            return
        span.cancel(reason=sanitize_and_truncate(reason, max_chars=500))
        self._dirty_update.add(span_id)
        self._pending_broadcasts.append((span.session_id, "cancelled", span.to_dict()))

    def ensure_run_span(
        self,
        session_id: str,
        run_id: str,
        source_message_id: str | None = None,
    ) -> str | None:
        """Create one stable root node for a run before SDK hooks can fire."""
        existing = self.find_run_span(session_id, run_id)
        if existing:
            return existing.id
        return self.create_span(
            session_id=session_id,
            run_id=run_id,
            span_type=TraceSpan.SPAN_TYPE_RUN,
            name="Agent run",
            metadata={"source_message_id": source_message_id} if source_message_id else None,
        )

    def find_run_span(self, session_id: str, run_id: str) -> TraceSpan | None:
        return next((
            span for span in self._buffer.values()
            if span.session_id == session_id
            and span.run_id == run_id
            and span.span_type == TraceSpan.SPAN_TYPE_RUN
        ), None)

    def finish_run(
        self,
        session_id: str,
        run_id: str,
        error: str | None = None,
        cancelled: bool = False,
    ) -> None:
        """Close every unfinished node so historical trees never remain spinning."""
        spans = [
            span for span in self._buffer.values()
            if span.session_id == session_id
            and span.run_id == run_id
            and span.status == TraceSpan.STATUS_RUNNING
        ]
        # Complete children before their run root.
        spans.sort(key=lambda span: span.span_type == TraceSpan.SPAN_TYPE_RUN)
        for span in spans:
            if cancelled:
                self.cancel_span(span.id, reason="Query cancelled")
            elif error:
                self.fail_span(span.id, error=error[:500])
            else:
                self.complete_span(span.id)

    def find_span_by_id(self, span_id: str) -> TraceSpan | None:
        return self._buffer.get(span_id)

    def find_running_by_tool_use_id(self, session_id: str, tool_use_id: str) -> TraceSpan | None:
        for span in self._buffer.values():
            if (
                span.session_id == session_id
                and span.tool_use_id == tool_use_id
                and span.status == TraceSpan.STATUS_RUNNING
            ):
                return span
        return None

    def find_running_by_agent_id(self, session_id: str, agent_id: str) -> TraceSpan | None:
        for span in self._buffer.values():
            if (
                span.session_id == session_id
                and span.agent_id == agent_id
                and span.span_type == TraceSpan.SPAN_TYPE_SUBAGENT
                and span.status == TraceSpan.STATUS_RUNNING
            ):
                return span
        return None

    def find_running_subagent_by_tool_use_id(
        self,
        session_id: str,
        tool_use_id: str | None,
    ) -> TraceSpan | None:
        if not tool_use_id:
            return None
        return next((
            span for span in reversed(list(self._buffer.values()))
            if span.session_id == session_id
            and span.tool_use_id == tool_use_id
            and span.span_type == TraceSpan.SPAN_TYPE_SUBAGENT
            and span.status == TraceSpan.STATUS_RUNNING
        ), None)

    def find_latest_running_llm_turn(self, session_id: str, run_id: str) -> TraceSpan | None:
        candidates = [
            s for s in self._buffer.values()
            if s.session_id == session_id
            and s.run_id == run_id
            and s.span_type == TraceSpan.SPAN_TYPE_LLM_TURN
            and s.status == TraceSpan.STATUS_RUNNING
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.started_time)

    def find_latest_running_tool(self, session_id: str, run_id: str) -> TraceSpan | None:
        candidates = [
            s for s in self._buffer.values()
            if s.session_id == session_id
            and s.run_id == run_id
            and s.span_type == TraceSpan.SPAN_TYPE_TOOL_CALL
            and s.status == TraceSpan.STATUS_RUNNING
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.started_time)

    def find_running_tool_by_id(self, session_id: str, tool_use_id: str | None) -> TraceSpan | None:
        if not tool_use_id:
            return None
        span = self.find_running_by_tool_use_id(session_id, tool_use_id)
        if span and span.span_type == TraceSpan.SPAN_TYPE_TOOL_CALL:
            return span
        return None

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("TraceCollector flush error", exc_info=True)

    async def _flush(self) -> None:
        if not self._dirty_new and not self._dirty_update and not self._pending_broadcasts:
            return

        async with self._lock:
            new_ids = list(self._dirty_new)
            update_ids = list(self._dirty_update - self._dirty_new)
            broadcasts = list(self._pending_broadcasts)
            self._dirty_new.clear()
            self._dirty_update.clear()
            self._pending_broadcasts.clear()

        new_spans = [self._buffer[sid] for sid in new_ids if sid in self._buffer]
        update_spans = [self._buffer[sid] for sid in update_ids if sid in self._buffer]

        try:
            if self._repository_factory is not None:
                async with self._repository_factory() as repository:
                    await self._persist(repository, new_spans, update_spans)
            elif self._repository is not None:
                await self._persist(self._repository, new_spans, update_spans)
        except Exception:
            # A transient DB failure must not silently erase trace history.
            async with self._lock:
                self._dirty_new.update(sid for sid in new_ids if sid in self._buffer)
                self._dirty_update.update(sid for sid in update_ids if sid in self._buffer)
            logger.warning(
                "TraceCollector: failed to persist %d new and %d updated spans",
                len(new_spans),
                len(update_spans),
                exc_info=True,
            )

        if broadcasts and self._broadcast_fn:
            for session_id, action, span_dict in broadcasts:
                try:
                    await self._broadcast_fn(session_id, {
                        "event": "trace_span",
                        "action": action,
                        "span": span_dict,
                    })
                except Exception:
                    logger.debug(
                        "TraceCollector: broadcast failed for span %s",
                        span_dict.get("id", "?"),
                        exc_info=True,
                    )

        completed_ids = [
            sid for sid, s in self._buffer.items()
            if s.status in (
                TraceSpan.STATUS_COMPLETED,
                TraceSpan.STATUS_FAILED,
                TraceSpan.STATUS_DENIED,
                TraceSpan.STATUS_CANCELLED,
            )
        ]
        if len(completed_ids) > 500:
            for sid in completed_ids[:len(completed_ids) - 200]:
                self._buffer.pop(sid, None)

    def discard_session(self, session_id: str) -> None:
        """Forget buffered data before a session is permanently deleted."""
        span_ids = {
            span_id for span_id, span in self._buffer.items()
            if span.session_id == session_id
        }
        for span_id in span_ids:
            self._buffer.pop(span_id, None)
        self._dirty_new.difference_update(span_ids)
        self._dirty_update.difference_update(span_ids)
        self._pending_broadcasts = [
            item for item in self._pending_broadcasts if item[0] != session_id
        ]

    @staticmethod
    async def _persist(
        repository: TraceSpanRepository,
        new_spans: list[TraceSpan],
        update_spans: list[TraceSpan],
    ) -> None:
        if new_spans:
            await repository.save_batch(new_spans)
        if update_spans:
            await repository.update_batch(update_spans)
        if new_spans or update_spans:
            await repository.commit()
