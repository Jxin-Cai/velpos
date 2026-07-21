from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from domain.shared.async_utils import KeyedLockPool, safe_create_task
from application.session.command.run_query_command import RunQueryCommand
from application.session.session_observability_recorder import SessionObservabilityRecorder
from application.session.session_presenter import SessionPresenter
from application.session.session_stream_consumer import SessionStreamConsumer
from domain.session.acl.claude_agent_gateway import ClaudeAgentGateway
from domain.session.acl.connection_manager import ConnectionManager
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from domain.session.service.message_conversion_service import MessageConversionService
from domain.session.repository.session_repository import SessionRepository
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


@dataclass
class _QueryContext:
    """Internal state passed between query phases."""

    session: Session
    command: RunQueryCommand
    run_id: str
    run_step: Any
    actual_prompt: str
    message_id: str
    cancelled_during_stream: bool = False
    card_sync_succeeded: bool | None = None
    card_sync_reason: str = ""


class SessionQueryEngine:
    _TRANSIENT_RESULT_ERROR_MARKERS = (
        "channel_unavailable",
        "service temporarily unavailable",
        "service_unavailable",
        "upstream returned http 502",
        "upstream returned http 503",
        "upstream returned http 504",
    )
    _session_lock_pool = KeyedLockPool(max_size=500)
    _cancelled_sessions: set[str] = set()
    _queued_messages: dict[str, RunQueryCommand] = {}
    _active_contexts: dict[str, _QueryContext] = {}
    _waiting_for_slot: set[str] = set()
    _slot_wait_started_at: dict[str, float] = {}
    _queue_guard = asyncio.Lock()
    _query_semaphore: asyncio.Semaphore | None = None
    _query_semaphore_guard = asyncio.Lock()

    @classmethod
    async def _lock_for_session(cls, session_id: str) -> asyncio.Lock:
        return await cls._session_lock_pool.acquire(session_id)

    @classmethod
    async def _get_query_semaphore(cls) -> asyncio.Semaphore:
        if cls._query_semaphore is None:
            async with cls._query_semaphore_guard:
                if cls._query_semaphore is None:
                    cls._query_semaphore = asyncio.Semaphore(cls._configured_query_capacity())
        return cls._query_semaphore

    def __init__(
        self,
        session_repository: SessionRepository,
        claude_agent_gateway: ClaudeAgentGateway,
        connection_manager: ConnectionManager,
        recorder: SessionObservabilityRecorder,
        stream_consumer: SessionStreamConsumer,
        save_session_fn: Callable[..., Awaitable[None]],
        reconnect_db_session_fn: Callable[..., Awaitable[None]],
        accept_or_reject_sdk_session_id_fn: Callable[..., Awaitable[bool]],
        resolve_resume_sdk_session_id_fn: Callable[..., Awaitable[str]],
        refresh_context_usage_fn: Callable[..., Awaitable[bool]],
        on_assistant_response: Callable[[str, str], Awaitable[None]] | None = None,
        on_user_message: Callable[[str, str], Awaitable[None]] | None = None,
        session_service_factory: Callable | None = None,
    ) -> None:
        self._session_repository = session_repository
        self._claude_agent_gateway = claude_agent_gateway
        self._connection_manager = connection_manager
        self._recorder = recorder
        self._stream_consumer = stream_consumer
        self._save_session = save_session_fn
        self._reconnect_db_session = reconnect_db_session_fn
        self._accept_or_reject_sdk_session_id = accept_or_reject_sdk_session_id_fn
        self._resolve_resume_sdk_session_id = resolve_resume_sdk_session_id_fn
        self._refresh_context_usage = refresh_context_usage_fn
        self._on_assistant_response = on_assistant_response
        self._on_user_message = on_user_message
        self._session_service_factory = session_service_factory

    async def cleanup_session_state(self, session_id: str) -> None:
        async with self._queue_guard:
            self._cancelled_sessions.discard(session_id)
            self._queued_messages.pop(session_id, None)
            self._active_contexts.pop(session_id, None)
            self._waiting_for_slot.discard(session_id)
            self._slot_wait_started_at.pop(session_id, None)
        await self._session_lock_pool.release(session_id)

    async def is_waiting_for_slot(self, session_id: str) -> bool:
        async with self._queue_guard:
            return session_id in self._waiting_for_slot

    async def submit_query(self, command: RunQueryCommand) -> None:
        self._claude_agent_gateway.mark_active(command.session_id)
        session_lock = await self._lock_for_session(command.session_id)
        query_semaphore = await self._get_query_semaphore()
        try:
            if session_lock.locked():
                await self._connection_manager.broadcast(
                    command.session_id,
                    {"event": "resource_waiting", "status": "waiting_session_runner"},
                )
                await self._recorder.record_audit_event(
                    command.session_id,
                    "resource_waiting",
                    payload={"reason": "session_runner_busy"},
                )
            async with session_lock:
                if query_semaphore.locked():
                    async with self._queue_guard:
                        self._waiting_for_slot.add(command.session_id)
                        self._slot_wait_started_at[command.session_id] = time.monotonic()
                        queue_position = len(self._waiting_for_slot)
                    await self._connection_manager.broadcast(
                        command.session_id,
                        {
                            "event": "resource_waiting",
                            "status": "waiting_slot",
                            "queue_position": queue_position,
                            "capacity": self._configured_query_capacity(),
                        },
                    )
                    await self._recorder.record_audit_event(
                        command.session_id,
                        "resource_waiting",
                        payload={"reason": "concurrency_limit"},
                    )
                async with query_semaphore:
                    async with self._queue_guard:
                        wait_started_at = self._slot_wait_started_at.pop(command.session_id, None)
                        self._waiting_for_slot.discard(command.session_id)
                    if wait_started_at is not None:
                        await self._connection_manager.broadcast(
                            command.session_id,
                            {
                                "event": "resource_acquired",
                                "status": "slot_acquired",
                                "waited_ms": int((time.monotonic() - wait_started_at) * 1000),
                                "capacity": self._configured_query_capacity(),
                            },
                        )
                    await self.run_claude_query(command)
        except asyncio.CancelledError:
            async with self._queue_guard:
                self._waiting_for_slot.discard(command.session_id)
                self._slot_wait_started_at.pop(command.session_id, None)
            self._claude_agent_gateway.mark_idle(command.session_id)
            raise
        except Exception:
            async with self._queue_guard:
                self._waiting_for_slot.discard(command.session_id)
                self._slot_wait_started_at.pop(command.session_id, None)
            self._claude_agent_gateway.mark_idle(command.session_id)
            raise
        finally:
            await self._session_lock_pool.unref(command.session_id)

    @staticmethod
    def _configured_query_capacity() -> int:
        raw_capacity = os.getenv("SESSION_MAX_CONCURRENT_QUERIES", "8")
        try:
            return min(64, max(1, int(raw_capacity)))
        except ValueError:
            logger.warning(
                "Invalid SESSION_MAX_CONCURRENT_QUERIES=%r; using 8",
                raw_capacity,
            )
            return 8

    async def run_claude_query(self, command: RunQueryCommand) -> None:
        ctx = await self._prepare_query(command)
        async with self._queue_guard:
            self._active_contexts[command.session_id] = ctx
        self._stream_consumer.start_trace_run(
            command.session_id,
            ctx.run_id,
            source_message_id=ctx.message_id,
        )
        try:
            await self._connection_manager.broadcast(
                command.session_id,
                {
                    "event": "trace_run_started",
                    "run_id": ctx.run_id,
                    "message_id": ctx.message_id,
                },
            )
        except Exception:
            logger.debug(
                "[session=%s] trace run link broadcast failed",
                command.session_id,
                exc_info=True,
            )
        trace_error: str | None = None
        try:
            await self._execute_streaming(ctx)
            if not ctx.cancelled_during_stream:
                await self._handle_result(ctx)
        except Exception as e:
            trace_error = str(e)
            await self._handle_error(ctx, e)
        finally:
            self._stream_consumer.finish_trace_run(
                command.session_id,
                ctx.run_id,
                error=trace_error,
                cancelled=(
                    ctx.cancelled_during_stream
                    or command.session_id in self._cancelled_sessions
                ),
            )
            async with self._queue_guard:
                if self._active_contexts.get(command.session_id) is ctx:
                    self._active_contexts.pop(command.session_id, None)
            await self._finalize_query(ctx)

    # ------------------------------------------------------------------
    # Phase 1: Prepare query context
    # ------------------------------------------------------------------

    async def _prepare_query(self, command: RunQueryCommand) -> _QueryContext:
        session = await self._session_repository.find_by_id(command.session_id)
        if session is None:
            raise BusinessException("Session not found")

        if session.cancel_requested:
            session.clear_cancel_requested()

        run_id = uuid.uuid4().hex[:8]
        run_step = await self._recorder.start_run_step(
            command.session_id,
            run_id,
            "run",
            "执行用户请求",
            {
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
                "prompt_length": len(command.prompt),
            },
        )

        logger.info(
            "[session=%s] 收到用户请求",
            command.session_id,
        )

        await self._recorder.record_audit_event(
            command.session_id,
            "query_started",
            actor="user",
            payload={
                "run_id": run_id,
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
                "prompt_length": len(command.prompt),
            },
        )
        await self._recorder.record_timeline_event(
            command.session_id,
            run_id,
            "user_input",
            "用户输入",
            {
                "prompt": command.prompt[:1200],
                "prompt_length": len(command.prompt),
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
            },
        )

        attachment_refs = []
        image_paths = set(command.image_paths)
        for attachment in command.attachments:
            path = attachment.get("path", "")
            filename = attachment.get("filename", "attachment")
            mime_type = attachment.get("mime_type", "")
            if not path:
                continue
            if mime_type.startswith("image/") or path in image_paths:
                attachment_refs.append(f"[Image: {path}]")
            else:
                attachment_refs.append(f"[Attachment: {filename} path={path}]")

        actual_prompt = command.prompt
        if attachment_refs:
            actual_prompt = f"{command.prompt}\n\n" + "\n".join(attachment_refs)
            logger.info(
                "[session=%s] 附加 %d 个附件到 prompt",
                command.session_id,
                len(attachment_refs),
            )

        session.start_query()
        self._claude_agent_gateway.mark_active(command.session_id)

        message_id = command.client_message_id or uuid.uuid4().hex[:12]
        user_message = Message.create(
            message_type=MessageType.USER,
            content={
                "message_id": message_id,
                "run_id": run_id,
                "text": actual_prompt,
                "attachments": command.attachments,
            },
        )
        session.add_message(user_message)

        return _QueryContext(
            session=session,
            command=command,
            run_id=run_id,
            run_step=run_step,
            actual_prompt=actual_prompt,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Phase 2: Execute streaming SDK interaction
    # ------------------------------------------------------------------

    async def _execute_streaming(self, ctx: _QueryContext) -> None:
        session = ctx.session
        command = ctx.command
        run_id = ctx.run_id
        run_step = ctx.run_step
        actual_prompt = ctx.actual_prompt

        if session.project_dir and not Path(session.project_dir).expanduser().is_dir():
            raise BusinessException(
                f"Project directory no longer exists: {session.project_dir}. "
                "Please recreate or remove this session."
            )

        async def _save_and_broadcast():
            await self._save_session(session, commit=True)
            await self._connection_manager.broadcast(
                session.session_id,
                {
                    "event": "status_change",
                    "status": "running",
                    "prompt": actual_prompt,
                    "message_id": ctx.message_id,
                    "run_id": run_id,
                    "attachments": command.attachments,
                },
            )
            if self._on_user_message:
                safe_create_task(
                    self._fire_user_outbound(session.session_id, actual_prompt),
                )

        async def _prepare_sdk_connection():
            is_connected = self._claude_agent_gateway.is_connected(command.session_id)
            connected_model = self._claude_agent_gateway.get_connected_model(command.session_id)
            if is_connected and connected_model != session.model:
                logger.info(
                    "[session=%s] 模型已变更 (%s -> %s), 断开重连",
                    command.session_id, connected_model, session.model,
                )
                await self._claude_agent_gateway.disconnect(command.session_id)
                return False
            return is_connected

        _, is_connected = await asyncio.gather(
            _save_and_broadcast(),
            _prepare_sdk_connection(),
        )

        msg_stream = None
        if is_connected:
            try:
                msg_stream = self._claude_agent_gateway.send_query(
                    session_id=command.session_id,
                    prompt=actual_prompt,
                )
            except Exception as send_err:
                logger.warning(
                    "[session=%s] send_query 失败 (%s), 回退到 connect",
                    command.session_id,
                    send_err,
                )
                await self._claude_agent_gateway.disconnect(command.session_id)
                msg_stream = None

        if msg_stream is None:
            resume_sdk_session_id = await self._resolve_resume_sdk_session_id(session)
            msg_stream = self._claude_agent_gateway.connect(
                session_id=command.session_id,
                model=session.model,
                prompt=actual_prompt,
                cwd=session.project_dir,
                sdk_session_id=resume_sdk_session_id,
                enable_file_checkpointing=True,
            )

        max_auto_continues = int(os.getenv("CLAUDE_MAX_AUTO_CONTINUES", "10"))

        try:
            got_result = await self._stream_consumer.consume(session, msg_stream, run_id)
        except Exception as stream_err:
            if command.session_id in self._cancelled_sessions:
                logger.info(
                    "[session=%s] 消息流因取消而中断, 跳过重试",
                    command.session_id,
                )
                await self._recorder.fail_run_step(run_step, {"cancelled": True, "stage": "stream"})
                ctx.cancelled_during_stream = True
                return
            if is_connected:
                await self._recorder.record_audit_event(
                    command.session_id,
                    "query_retrying",
                    payload={"run_id": run_id, "error": str(stream_err)[:500]},
                )
                await self._recorder.record_timeline_event(
                    command.session_id,
                    run_id,
                    "retry",
                    "消息流中断，重新连接",
                    {"error": str(stream_err)[:500]},
                )
                logger.warning(
                    "[session=%s] 消息流中断 (%s), 重新 connect",
                    command.session_id,
                    stream_err,
                )
                await self._claude_agent_gateway.disconnect(command.session_id)
                resume_sdk_session_id = await self._resolve_resume_sdk_session_id(session)
                msg_stream = self._claude_agent_gateway.connect(
                    session_id=command.session_id,
                    model=session.model,
                    prompt=actual_prompt,
                    cwd=session.project_dir,
                    sdk_session_id=resume_sdk_session_id,
                )
                got_result = await self._stream_consumer.consume(session, msg_stream, run_id)
            else:
                raise

        got_result = await self._retry_transient_result(ctx, got_result)

        auto_continue_count = 0
        while not got_result and auto_continue_count < max_auto_continues:
            if command.session_id in self._cancelled_sessions:
                break
            if not self._claude_agent_gateway.is_connected(command.session_id):
                break

            auto_continue_count += 1
            logger.info(
                "[session=%s] 未收到 ResultMessage, 自动继续 (%d/%d)",
                command.session_id,
                auto_continue_count,
                max_auto_continues,
            )
            await self._recorder.record_audit_event(
                command.session_id,
                "auto_continue",
                payload={
                    "run_id": run_id,
                    "attempt": auto_continue_count,
                    "max": max_auto_continues,
                },
            )
            await self._recorder.record_timeline_event(
                command.session_id,
                run_id,
                "auto_continue",
                f"自动继续执行 ({auto_continue_count}/{max_auto_continues})",
                {"attempt": auto_continue_count, "max": max_auto_continues},
            )
            await self._connection_manager.broadcast(
                session.session_id,
                {
                    "event": "auto_continue",
                    "attempt": auto_continue_count,
                    "max": max_auto_continues,
                },
            )

            try:
                continue_stream = self._claude_agent_gateway.send_query(
                    session_id=command.session_id,
                    prompt="Continue where you left off.",
                )
                got_result = await self._stream_consumer.consume(session, continue_stream, run_id)
            except Exception as cont_err:
                logger.warning(
                    "[session=%s] 自动继续失败: %s",
                    command.session_id,
                    cont_err,
                )
                break

        if not got_result:
            synthetic_result = self._build_stream_end_result(session, auto_continue_count)
            log_message = "消息流结束但未收到 ResultMessage"
            if synthetic_result.content["is_error"]:
                logger.warning("[session=%s] %s，且未收到 Agent 输出", command.session_id, log_message)
            else:
                logger.info("[session=%s] %s，使用已收到的 Agent 输出完成", command.session_id, log_message)
            session.add_message(synthetic_result)
            await self._connection_manager.broadcast(
                session.session_id,
                {"event": "message", "data": {"type": "result", "content": synthetic_result.content}},
            )

        await self._refresh_context_usage(session)

    async def _retry_transient_result(
        self,
        ctx: _QueryContext,
        got_result: bool,
    ) -> bool:
        """Retry terminal upstream availability errors returned as ResultMessage."""
        if not got_result:
            return False

        max_retries = self._configured_transient_result_retries()
        base_delay = self._configured_transient_retry_delay()
        for attempt in range(1, max_retries + 1):
            failure_reason = self._result_failure_reason(ctx.session)
            if not self._is_transient_result_error(failure_reason):
                break
            if ctx.command.session_id in self._cancelled_sessions:
                break

            delay_seconds = min(30.0, base_delay * (2 ** (attempt - 1)))
            retry_payload = {
                "run_id": ctx.run_id,
                "attempt": attempt,
                "max": max_retries,
                "delay_seconds": delay_seconds,
                "error": failure_reason[:500],
            }
            logger.warning(
                "[session=%s] 上游服务暂时不可用，%.1f 秒后重试 (%d/%d)",
                ctx.command.session_id,
                delay_seconds,
                attempt,
                max_retries,
            )
            await self._recorder.record_audit_event(
                ctx.command.session_id,
                "query_retrying",
                payload=retry_payload,
            )
            await self._recorder.record_timeline_event(
                ctx.command.session_id,
                ctx.run_id,
                "retry",
                f"上游服务暂时不可用，自动重试 ({attempt}/{max_retries})",
                retry_payload,
            )
            await self._connection_manager.broadcast(
                ctx.command.session_id,
                {
                    "event": "query_retrying",
                    "attempt": attempt,
                    "max": max_retries,
                    "delay_seconds": delay_seconds,
                },
            )
            await asyncio.sleep(delay_seconds)
            if ctx.command.session_id in self._cancelled_sessions:
                break

            retry_stream = self._claude_agent_gateway.send_query(
                session_id=ctx.command.session_id,
                prompt=ctx.actual_prompt,
            )
            got_result = await self._stream_consumer.consume(
                ctx.session,
                retry_stream,
                ctx.run_id,
            )
            if not got_result:
                break

        return got_result

    @classmethod
    def _is_transient_result_error(cls, reason: str) -> bool:
        normalized_reason = reason.casefold()
        return any(
            marker in normalized_reason
            for marker in cls._TRANSIENT_RESULT_ERROR_MARKERS
        )

    @staticmethod
    def _configured_transient_result_retries() -> int:
        raw_retries = os.getenv("CLAUDE_TRANSIENT_RESULT_RETRIES", "2")
        try:
            return min(5, max(0, int(raw_retries)))
        except ValueError:
            logger.warning(
                "Invalid CLAUDE_TRANSIENT_RESULT_RETRIES=%r; using 2",
                raw_retries,
            )
            return 2

    @staticmethod
    def _configured_transient_retry_delay() -> float:
        raw_delay = os.getenv("CLAUDE_TRANSIENT_RETRY_BASE_DELAY_SECONDS", "1")
        try:
            return min(30.0, max(0.0, float(raw_delay)))
        except ValueError:
            logger.warning(
                "Invalid CLAUDE_TRANSIENT_RETRY_BASE_DELAY_SECONDS=%r; using 1",
                raw_delay,
            )
            return 1.0

    @staticmethod
    def _build_stream_end_result(session: Session, auto_continue_count: int) -> Message:
        return Message.create(
            message_type=MessageType.RESULT,
            content={
                "text": "Agent stream ended without a successful result.",
                "duration_ms": 0,
                "duration_api_ms": 0,
                "num_turns": 0,
                "is_error": True,
                "total_cost_usd": 0,
                "stop_reason": "auto_continue_exhausted" if auto_continue_count > 0 else "stream_ended",
                "usage": {
                    "input_tokens": session.usage.input_tokens,
                    "output_tokens": session.usage.output_tokens,
                },
            },
        )

    async def _sync_team_card_execution(
        self,
        session: Session,
        *,
        succeeded: bool,
        reason: str = "",
    ) -> None:
        if not session.card_execution_id:
            return

        from infr.config.database import async_session_factory
        from infr.repository.wish_card_repository_impl import WishCardRepositoryImpl
        from infr.repository.card_execution_repository_impl import CardExecutionRepositoryImpl
        from infr.repository.team_repository_impl import TeamRepositoryImpl

        slot_availability: str | None = None

        async with async_session_factory() as db_session:
            execution_repo = CardExecutionRepositoryImpl(db_session)
            execution = await execution_repo.find_by_id(session.card_execution_id)
            if execution is None:
                logger.error(
                    "[session=%s] team execution not found: %s",
                    session.session_id,
                    session.card_execution_id,
                )
                return
            card_repo = WishCardRepositoryImpl(db_session)
            card = await card_repo.find_by_id(execution.card_id)
            if card is None:
                logger.error(
                    "[session=%s] wish card not found for execution: %s",
                    session.session_id,
                    execution.id,
                )
                return
            if succeeded:
                card.complete_execution(execution.id)
                if execution.agent_slot_id:
                    team_repo = TeamRepositoryImpl(db_session)
                    team = await team_repo.find_by_id(card.team_id)
                    if team is not None:
                        slot = team.find_agent_slot(execution.agent_slot_id)
                        if slot is not None and not slot.is_available:
                            slot.mark_available()
                            await team_repo.save(team)
            else:
                card.fail_execution(execution.id, reason.strip() or "Agent execution failed")
                # Mark the executing slot as unstable on failure so the board
                # can surface a health warning and prompt the user to retry.
                if execution.agent_slot_id:
                    team_repo = TeamRepositoryImpl(db_session)
                    team = await team_repo.find_by_id(card.team_id)
                    if team is not None:
                        slot = team.find_agent_slot(execution.agent_slot_id)
                        if slot is not None:
                            slot.mark_unstable()
                            await team_repo.save(team)
                            slot_availability = slot.availability.value
            await card_repo.save(card)
            await db_session.commit()

        latest = card.latest_execution
        await self._connection_manager.broadcast_global({
            "event": "board_card_updated",
            "team_id": card.team_id,
            "card": {
                "id": card.id,
                "title": card.title,
                "description": card.description,
                "status": card.status.value,
                "current_slot_id": card.current_slot_id,
                "version": card.version,
                "updated_at": card.updated_at.isoformat(),
                "session_id": latest.session_id if latest else None,
                "execution_id": latest.id if latest else None,
                "failure_reason": latest.failure_reason if latest else None,
                **({"slot_availability": slot_availability, "slot_id": execution.agent_slot_id}
                   if slot_availability is not None else {}),
            },
        })

    # ------------------------------------------------------------------
    # Phase 3: Handle successful result
    # ------------------------------------------------------------------

    async def _handle_result(self, ctx: _QueryContext) -> None:
        session = ctx.session
        command = ctx.command
        run_id = ctx.run_id
        run_step = ctx.run_step

        if command.session_id in self._cancelled_sessions:
            session.clear_cancel_requested()
            await self._recorder.fail_run_step(run_step, {"cancelled": True, "stage": "completion"})
            logger.info("[session=%s] 查询被取消, 跳过正常完成流程", command.session_id)
            return

        result_error = self._result_failure_reason(session)
        if result_error:
            raise BusinessException(result_error)

        session.complete_query()
        ctx.card_sync_succeeded = True

        if self._on_assistant_response:
            text = MessageConversionService.extract_assistant_text(session.messages)
            if text:
                safe_create_task(
                    self._fire_outbound(session.session_id, text),
                )

        logger.info(
            "[session=%s] 查询完成, usage=%s",
            command.session_id,
            {"input_tokens": session.usage.input_tokens, "output_tokens": session.usage.output_tokens},
        )
        await self._recorder.record_usage_ledger(session)
        await self._recorder.complete_run_step(
            run_step,
            {
                "input_tokens": session.usage.input_tokens,
                "output_tokens": session.usage.output_tokens,
                "message_count": session.message_count,
            },
        )
        await self._recorder.record_audit_event(
            command.session_id,
            "query_finished",
            payload={
                "run_id": run_id,
                "input_tokens": session.usage.input_tokens,
                "output_tokens": session.usage.output_tokens,
                "message_count": session.message_count,
            },
        )

    @staticmethod
    def _result_failure_reason(session: Session) -> str:
        for message in reversed(session.messages):
            if message.message_type is not MessageType.RESULT:
                continue
            if message.content.get("is_error") is not True:
                return ""
            text = message.content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            return "Agent returned an unsuccessful result"
        return "Agent stream ended without a result"

    # ------------------------------------------------------------------
    # Phase 4: Handle error
    # ------------------------------------------------------------------

    async def _handle_error(self, ctx: _QueryContext, e: Exception) -> None:
        session = ctx.session
        command = ctx.command
        run_id = ctx.run_id
        run_step = ctx.run_step

        if command.session_id in self._cancelled_sessions:
            session.clear_cancel_requested()
            await self._recorder.fail_run_step(run_step, {"cancelled": True, "stage": "error"})
            logger.info("[session=%s] 查询异常但已取消, 跳过错误处理", command.session_id)
            return
        logger.error(
            "[session=%s] Claude查询失败: %s",
            command.session_id,
            str(e),
            exc_info=True,
        )
        session.fail_query()
        ctx.card_sync_succeeded = False
        ctx.card_sync_reason = str(e)

        await self._recorder.fail_run_step(run_step, {"error": str(e)[:500]})
        await self._recorder.record_audit_event(
            command.session_id,
            "query_failed",
            payload={"run_id": run_id, "error": str(e)[:500]},
        )
        await self._recorder.record_timeline_event(
            command.session_id,
            run_id,
            "error",
            "执行失败",
            {"error": str(e)[:1000]},
            status="failed",
        )
        await self._connection_manager.broadcast(
            session.session_id,
            {"event": "error", "message": str(e)},
        )

    # ------------------------------------------------------------------
    # Phase 5: Finalize (always runs)
    # ------------------------------------------------------------------

    async def _finalize_query(self, ctx: _QueryContext) -> None:
        session = ctx.session
        command = ctx.command
        run_id = ctx.run_id

        self._claude_agent_gateway.mark_idle(command.session_id)
        if command.session_id in self._cancelled_sessions:
            async with self._queue_guard:
                self._cancelled_sessions.discard(command.session_id)
            return
        final_save_succeeded = False
        try:
            await self._save_session(session, commit=True)
            final_save_succeeded = True
        except Exception:
            logger.error(
                "[session=%s] final save failed, retrying with fresh DB session",
                command.session_id,
                exc_info=True,
                extra={"session_id": command.session_id, "run_id": run_id},
            )
            try:
                from infr.config.database import async_session_factory
                from infr.repository.session_repository_impl import SessionRepositoryImpl

                async with async_session_factory() as fresh_db:
                    fresh_repo = SessionRepositoryImpl(fresh_db)
                    await fresh_repo.save(session)
                    await fresh_db.commit()
                    final_save_succeeded = True
                    logger.warning(
                        "[session=%s] final save recovered with fresh DB session",
                        command.session_id,
                        extra={"session_id": command.session_id, "run_id": run_id},
                    )
            except Exception:
                logger.error(
                    "[session=%s] retry save also failed",
                    command.session_id,
                    exc_info=True,
                    extra={"session_id": command.session_id, "run_id": run_id},
                )
        if not final_save_succeeded:
            session.fail_query()
            ctx.card_sync_succeeded = False
            ctx.card_sync_reason = "session final save failed"
        await self._connection_manager.broadcast(
            session.session_id,
            {
                "event": "status",
                "session": SessionPresenter.session_to_dict(session),
            },
        )
        if ctx.card_sync_succeeded is not None:
            try:
                await self._sync_team_card_execution(
                    session,
                    succeeded=ctx.card_sync_succeeded,
                    reason=ctx.card_sync_reason,
                )
            except Exception:
                logger.error(
                    "[session=%s] card execution sync failed",
                    command.session_id,
                    exc_info=True,
                )

        async with self._queue_guard:
            queued = self._queued_messages.pop(command.session_id, None)
        if queued:
            await self._set_queued_command(command.session_id, None)
            await self._connection_manager.broadcast(
                command.session_id,
                {
                    "event": "queue_started",
                    "message_id": queued.client_message_id,
                    "prompt": queued.prompt,
                    "image_count": len(queued.image_paths),
                    "attachments": [
                        {
                            "filename": item.get("filename", "attachment"),
                            "mime_type": item.get("mime_type", "application/octet-stream"),
                            "size_bytes": item.get("size_bytes", 0),
                        }
                        for item in queued.attachments
                    ],
                },
            )
            await self._recorder.record_audit_event(
                command.session_id,
                "queue_started",
                payload={"prompt_length": len(queued.prompt), "attachment_count": len(queued.attachments)},
            )
            logger.info("[session=%s] 执行排队的后续消息", command.session_id)
            if self._session_service_factory is not None:
                async def _run_queued_message(command: RunQueryCommand) -> None:
                    queued_service = await self._session_service_factory()
                    try:
                        await queued_service.submit_query(command)
                    finally:
                        await queued_service.close()

                safe_create_task(_run_queued_message(queued))
            else:
                safe_create_task(self.submit_query(queued))

    async def _fire_outbound(self, session_id: str, text: str) -> None:
        try:
            await self._on_assistant_response(session_id, text)
        except Exception:
            logger.warning(
                "[session=%s] outbound IM sync failed", session_id, exc_info=True,
            )

    async def _fire_user_outbound(self, session_id: str, text: str) -> None:
        try:
            await self._on_user_message(session_id, text)
        except Exception:
            logger.warning(
                "[session=%s] user message IM sync failed", session_id, exc_info=True,
            )

    async def cancel_query(self, session_id: str) -> None:
        async with self._queue_guard:
            self._cancelled_sessions.add(session_id)
            self._waiting_for_slot.discard(session_id)
            self._slot_wait_started_at.pop(session_id, None)
        await self._recorder.record_audit_event(session_id, "cancel_requested", actor="user")
        await self._recorder.record_timeline_event(
            session_id,
            "external",
            "cancel",
            "用户请求取消",
            {},
            status="cancelled",
        )
        await self._set_cancel_requested(session_id, True)
        await self.clear_queued_message(session_id)

        await self._claude_agent_gateway.cancel_pending_response(session_id)

        try:
            await asyncio.wait_for(
                self._claude_agent_gateway.interrupt(session_id),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[session=%s] interrupt timed out after 3s, falling back to disconnect",
                session_id,
            )
            await self._claude_agent_gateway.disconnect(session_id)
        except RuntimeError:
            logger.info("[session=%s] cancel_query: no active connection", session_id)

        for _ in range(20):
            if not self._claude_agent_gateway.is_active(session_id):
                break
            await asyncio.sleep(0.1)

        rewind_sdk_sid = ""
        if self._claude_agent_gateway.is_connected(session_id):
            try:
                async for msg_dict in self._claude_agent_gateway.send_query(session_id, "/rewind"):
                    sdk_sid = msg_dict.get("sdk_session_id")
                    if sdk_sid:
                        rewind_sdk_sid = sdk_sid
                logger.info("[session=%s] /rewind sent successfully", session_id)
            except Exception as e:
                logger.warning("[session=%s] /rewind failed: %s", session_id, e)

        session = await self._session_repository.find_by_id(session_id)
        prompt = ""
        if session is not None:
            try:
                prompt = session.cancel_query()
                await self._save_session(session, commit=True)
            except ValueError:
                for msg in reversed(session.messages):
                    if msg.message_type.value == "user":
                        prompt = msg.content.get("text", "")
                        break

            if rewind_sdk_sid:
                try:
                    await self._accept_or_reject_sdk_session_id(session, rewind_sdk_sid, "rewind")
                except Exception:
                    logger.error("[session=%s] /rewind SDK session_id rejected", session_id, exc_info=True)
                finally:
                    try:
                        await self._save_session(session, commit=True)
                    except Exception:
                        logger.warning(
                            "[session=%s] failed to persist /rewind sdk_session_id update",
                            session_id,
                            exc_info=True,
                        )

            if self._claude_agent_gateway.is_connected(session_id):
                target_uuid = ""
                for msg in reversed(session.messages):
                    if msg.message_type == MessageType.USER:
                        target_uuid = msg.content.get("sdk_user_message_uuid", "")
                        break
                if target_uuid:
                    try:
                        await self._claude_agent_gateway.rewind_files(session_id, target_uuid)
                        logger.info("[session=%s] rewind_files completed: target=%s", session_id, target_uuid)
                    except Exception as e:
                        logger.warning("[session=%s] rewind_files failed: %s", session_id, e)

            await self._broadcast_rewind_state(session_id, session, prompt)
        else:
            await self._connection_manager.broadcast(
                session_id,
                {"event": "status_change", "status": "idle"},
            )

        await self._set_cancel_requested(session_id, False)
        await self._recorder.record_audit_event(
            session_id,
            "cancel_completed",
            payload={"restored_prompt_length": len(prompt)},
        )

    async def rewind_to_message_id(self, session_id: str, message_id: str) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException(f"Session not found: {session_id}")

        for index, msg in enumerate(session.messages):
            if msg.message_type == MessageType.USER and msg.content.get("message_id") == message_id:
                await self.rewind_to_message(session_id, index)
                return

        raise BusinessException(f"User message not found: {message_id}")

    async def rewind_to_message(self, session_id: str, message_index: int) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException(f"Session not found: {session_id}")

        rewind_count = sum(
            1 for msg in session.messages[message_index:]
            if msg.message_type == MessageType.USER
        )

        prompt = session.rewind_to(message_index)
        await self._save_session(session, commit=True)

        if self._claude_agent_gateway.is_connected(session_id):
            rewind_sdk_sid = ""
            for _ in range(rewind_count):
                try:
                    async for msg_dict in self._claude_agent_gateway.send_query(session_id, "/rewind"):
                        sdk_sid = msg_dict.get("sdk_session_id")
                        if sdk_sid:
                            rewind_sdk_sid = sdk_sid
                except Exception as e:
                    logger.warning("[session=%s] /rewind failed: %s", session_id, e)
                    break

            if rewind_sdk_sid:
                try:
                    await self._accept_or_reject_sdk_session_id(session, rewind_sdk_sid, "rewind")
                    await self._save_session(session, commit=True)
                except Exception:
                    logger.error("[session=%s] rewind_to SDK session_id rejected", session_id, exc_info=True)

            target_uuid = ""
            for msg in reversed(session.messages):
                if msg.message_type == MessageType.USER:
                    target_uuid = msg.content.get("sdk_user_message_uuid", "")
                    break
            if target_uuid:
                try:
                    await self._claude_agent_gateway.rewind_files(session_id, target_uuid)
                    logger.info("[session=%s] rewind_files to index %d: uuid=%s", session_id, message_index, target_uuid)
                except Exception as e:
                    logger.warning("[session=%s] rewind_files failed: %s", session_id, e)

        await self._broadcast_rewind_state(session_id, session, prompt)

    async def _broadcast_rewind_state(self, session_id: str, session: Session, prompt: str) -> None:
        all_messages = [
            {"type": msg.message_type.value, "content": msg.content}
            for msg in session.messages
        ]
        await self._connection_manager.broadcast(
            session_id,
            {
                "event": "cancel_rewind",
                "prompt": prompt,
                "session": SessionPresenter.session_to_dict(session),
                "messages": all_messages,
            },
        )

    async def queue_message(self, session_id: str, command: RunQueryCommand) -> None:
        async with self._queue_guard:
            previous = self._queued_messages.get(session_id)
            self._queued_messages[session_id] = command
        await self._set_queued_command(session_id, command)
        if previous is not None:
            await self._recorder.record_audit_event(
                session_id,
                "queue_dropped",
                payload={"prompt_length": len(previous.prompt)},
            )
        await self._recorder.record_audit_event(
            session_id,
            "queue_enqueued",
            actor="user",
            payload={
                "prompt_length": len(command.prompt),
                "image_count": len(command.image_paths),
                "attachment_count": len(command.attachments),
            },
        )
        logger.info("[session=%s] 消息已排队 (latest-wins)", session_id)

    async def clear_queued_message(self, session_id: str) -> None:
        async with self._queue_guard:
            removed = self._queued_messages.pop(session_id, None)
        await self._set_queued_command(session_id, None)
        if removed:
            logger.info("[session=%s] 已清除排队消息", session_id)

    async def steer_queued_message(self, session_id: str) -> dict[str, Any]:
        async with self._queue_guard:
            queued = self._queued_messages.get(session_id)
            ctx = self._active_contexts.get(session_id)
            if queued is None:
                raise BusinessException("No queued message to steer")
            if (
                ctx is None
                or not self._claude_agent_gateway.is_active(session_id)
                or self._claude_agent_gateway.get_state(session_id) != "streaming"
            ):
                raise BusinessException(
                    "The current run has already finished; the message remains queued"
                )

            actual_prompt = self._compose_prompt(queued)
            try:
                await self._claude_agent_gateway.steer(session_id, actual_prompt)
            except RuntimeError as exc:
                raise BusinessException(
                    "The current run has already finished; the message remains queued"
                ) from exc

            if self._queued_messages.get(session_id) is not queued:
                raise BusinessException("The queued message changed; please try again")
            self._queued_messages.pop(session_id, None)

            message_id = queued.client_message_id or uuid.uuid4().hex[:12]
            ctx.session.add_message(Message.create(
                message_type=MessageType.USER,
                content={
                    "message_id": message_id,
                    "run_id": ctx.run_id,
                    "text": actual_prompt,
                    "attachments": queued.attachments,
                    "steered": True,
                },
            ))

        try:
            await self._set_queued_command(session_id, None)
        except Exception:
            # The active context already carries queued_command=None and will be
            # persisted when the run completes. Do not report a failed steer
            # after the SDK has already accepted the message.
            logger.warning(
                "[session=%s] 引导成功，但持久化队列清理失败，等待运行结束时重试",
                session_id,
                exc_info=True,
            )
        try:
            await self._recorder.record_audit_event(
                session_id,
                "queue_steered",
                actor="user",
                payload={
                    "run_id": ctx.run_id,
                    "prompt_length": len(queued.prompt),
                    "attachment_count": len(queued.attachments),
                },
            )
            await self._recorder.record_timeline_event(
                session_id,
                ctx.run_id,
                "user_input",
                "用户引导",
                {
                    "prompt": queued.prompt[:1200],
                    "prompt_length": len(queued.prompt),
                    "steered": True,
                },
            )
        except Exception:
            logger.warning(
                "[session=%s] 引导成功，但审计事件记录失败",
                session_id,
                exc_info=True,
            )
        logger.info("[session=%s] 排队消息已引导到当前执行", session_id)
        return {
            "message_id": message_id,
            "run_id": ctx.run_id,
            "prompt": actual_prompt,
            "image_count": len(queued.image_paths),
            "attachments": [
                {
                    "filename": item.get("filename", "attachment"),
                    "mime_type": item.get("mime_type", "application/octet-stream"),
                    "size_bytes": item.get("size_bytes", 0),
                }
                for item in queued.attachments
            ],
        }

    @staticmethod
    def _compose_prompt(command: RunQueryCommand) -> str:
        attachment_refs = []
        image_paths = set(command.image_paths)
        for attachment in command.attachments:
            path = attachment.get("path", "")
            filename = attachment.get("filename", "attachment")
            mime_type = attachment.get("mime_type", "")
            if not path:
                continue
            if mime_type.startswith("image/") or path in image_paths:
                attachment_refs.append(f"[Image: {path}]")
            else:
                attachment_refs.append(f"[Attachment: {filename} path={path}]")
        if not attachment_refs:
            return command.prompt
        return f"{command.prompt}\n\n" + "\n".join(attachment_refs)

    async def _set_cancel_requested(self, session_id: str, requested: bool) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if requested:
            session.mark_cancel_requested()
        else:
            session.clear_cancel_requested()
        await self._save_session(session, commit=True)

    async def _set_queued_command(
        self,
        session_id: str,
        command: RunQueryCommand | None,
    ) -> None:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            return
        if command is None:
            session.clear_queued_command()
        else:
            session.update_queued_command(
                command.prompt,
                command.image_paths,
                command.attachments,
                command.client_message_id,
            )
        await self._save_session(session, commit=True)
