from __future__ import annotations

import asyncio
import logging
import os
import uuid

from collections.abc import Awaitable, Callable
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
from domain.project.repository.project_repository import ProjectRepository
from domain.session.repository.session_repository import SessionRepository
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


class SessionQueryEngine:
    _session_lock_pool = KeyedLockPool(max_size=500)
    _cancelled_sessions: set[str] = set()
    _queued_messages: dict[str, RunQueryCommand] = {}
    _waiting_for_slot: set[str] = set()
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
                    max_concurrent = int(os.getenv("SESSION_MAX_CONCURRENT_QUERIES", "2"))
                    cls._query_semaphore = asyncio.Semaphore(max(1, max_concurrent))
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
        project_repository: ProjectRepository | None = None,
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
        self._project_repository = project_repository
        self._session_service_factory = session_service_factory

    async def cleanup_session_state(self, session_id: str) -> None:
        async with self._queue_guard:
            self._cancelled_sessions.discard(session_id)
            self._queued_messages.pop(session_id, None)
            self._waiting_for_slot.discard(session_id)
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
                    await self._connection_manager.broadcast(
                        command.session_id,
                        {"event": "resource_waiting", "status": "waiting_slot"},
                    )
                    await self._recorder.record_audit_event(
                        command.session_id,
                        "resource_waiting",
                        payload={"reason": "concurrency_limit"},
                    )
                async with query_semaphore:
                    async with self._queue_guard:
                        self._waiting_for_slot.discard(command.session_id)
                    await self.run_claude_query(command)
        except asyncio.CancelledError:
            async with self._queue_guard:
                self._waiting_for_slot.discard(command.session_id)
            self._claude_agent_gateway.mark_idle(command.session_id)
            raise
        except Exception:
            async with self._queue_guard:
                self._waiting_for_slot.discard(command.session_id)
            self._claude_agent_gateway.mark_idle(command.session_id)
            raise
        finally:
            await self._session_lock_pool.unref(command.session_id)

    async def _resolve_team_connect_config(self, session: Session) -> dict[str, Any]:
        if not self._project_repository:
            return {}
        if session.team_task_id:
            return {}

        project = await self._project_repository.find_by_id(session.project_id)
        if not project or project.project_type != "team":
            return {}

        from application.team_task.prompt_builder import build_coordinator_system_prompt
        from application.team_task.team_coordinator_service import TeamCoordinatorService
        from infr.client.team_mcp_server import create_team_coordinator_mcp
        from infr.repository.team_task_repository_impl import TeamTaskRepositoryImpl

        agent_service = None
        try:
            from application.agent.agent_application_service import AgentApplicationService
            from application.memory.claude_md_revision_application_service import ClaudeMdRevisionApplicationService
            from infr.client.claude_plugin_manager import ClaudePluginManager
            from infr.repository.claude_md_revision_repository_impl import ClaudeMdRevisionRepositoryImpl
            from infr.repository.project_repository_impl import ProjectRepositoryImpl as ProjRepoImpl

            db_session = self._session_repository._session
            revision_service = ClaudeMdRevisionApplicationService(
                revision_repository=ClaudeMdRevisionRepositoryImpl(db_session),
                project_repository=ProjRepoImpl(db_session),
            )
            agent_service = AgentApplicationService(
                plugin_manager=ClaudePluginManager(),
                claude_md_revision_service=revision_service,
            )
        except Exception:
            logger.warning("Failed to create AgentApplicationService for team coordinator", exc_info=True)

        coordinator_service = TeamCoordinatorService(
            project_repository=self._project_repository,
            session_repository=self._session_repository,
            team_task_repository=TeamTaskRepositoryImpl(self._session_repository._session),
            claude_agent_gateway=self._claude_agent_gateway,
            connection_manager=self._connection_manager,
            agent_application_service=agent_service,
            notify_im_fn=self._on_assistant_response,
        )

        trace_id = uuid.uuid4().hex[:8]

        mcp_server = create_team_coordinator_mcp(
            coordinator_service=coordinator_service,
            project_id=project.id,
            coordinator_session_id=session.session_id,
            trace_id=trace_id,
        )

        return {
            "system_prompt": build_coordinator_system_prompt(project),
            "mcp_servers": {"team_coordinator": mcp_server},
            "trace_id": trace_id,
        }

    async def run_claude_query(self, command: RunQueryCommand) -> None:
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

        message_id = uuid.uuid4().hex[:12]
        user_message = Message.create(
            message_type=MessageType.USER,
            content={
                "message_id": message_id,
                "text": actual_prompt,
                "attachments": command.attachments,
            },
        )
        session.add_message(user_message)

        async def _save_and_broadcast():
            await self._save_session(session, commit=True)
            await self._connection_manager.broadcast(
                session.session_id,
                {
                    "event": "status_change",
                    "status": "running",
                    "prompt": actual_prompt,
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

        try:
            _, is_connected = await asyncio.gather(
                _save_and_broadcast(),
                _prepare_sdk_connection(),
            )

            team_config = await self._resolve_team_connect_config(session)

            trace_id = team_config.get("trace_id", "")
            if trace_id:
                from application.team_task.trace_file_manager import TraceFileManager
                await TraceFileManager.create_trace(
                    project_dir=session.project_dir,
                    trace_id=trace_id,
                    requirement=actual_prompt,
                    coordinator_session_id=session.session_id,
                    project_id=session.project_id,
                )
                session.update_trace_id(trace_id)
                await self._save_session(session, commit=True)

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
                    system_prompt=team_config.get("system_prompt"),
                    mcp_servers=team_config.get("mcp_servers"),
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
                        system_prompt=team_config.get("system_prompt"),
                        mcp_servers=team_config.get("mcp_servers"),
                    )
                    got_result = await self._stream_consumer.consume(session, msg_stream, run_id)
                else:
                    raise

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
                logger.warning(
                    "[session=%s] 消息流结束但未收到 ResultMessage, 合成完成事件",
                    command.session_id,
                )
                synthetic_result = Message.create(
                    message_type=MessageType.RESULT,
                    content={
                        "text": "",
                        "duration_ms": 0,
                        "duration_api_ms": 0,
                        "num_turns": 0,
                        "is_error": False,
                        "total_cost_usd": 0,
                        "stop_reason": "auto_continue_exhausted" if auto_continue_count > 0 else "stream_ended",
                        "usage": {
                            "input_tokens": session.usage.input_tokens,
                            "output_tokens": session.usage.output_tokens,
                        },
                    },
                )
                session.add_message(synthetic_result)
                await self._connection_manager.broadcast(
                    session.session_id,
                    {"event": "message", "data": {"type": "result", "content": synthetic_result.content}},
                )

            await self._refresh_context_usage(session)

            if command.session_id in self._cancelled_sessions:
                session.clear_cancel_requested()
                await self._recorder.fail_run_step(run_step, {"cancelled": True, "stage": "completion"})
                logger.info("[session=%s] 查询被取消, 跳过正常完成流程", command.session_id)
                return

            session.complete_query()

            if session.trace_id:
                from application.team_task.trace_file_manager import TraceFileManager
                await TraceFileManager.complete_trace(
                    project_dir=session.project_dir,
                    trace_id=session.trace_id,
                )

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

        except Exception as e:
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

            if session.trace_id:
                from application.team_task.trace_file_manager import TraceFileManager
                await TraceFileManager.fail_trace(
                    project_dir=session.project_dir,
                    trace_id=session.trace_id,
                )

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

        finally:
            self._claude_agent_gateway.mark_idle(command.session_id)
            if command.session_id in self._cancelled_sessions:
                async with self._queue_guard:
                    self._cancelled_sessions.discard(command.session_id)
                return
            try:
                await self._save_session(session, commit=True)
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
            await self._connection_manager.broadcast(
                session.session_id,
                {
                    "event": "status",
                    "session": SessionPresenter.session_to_dict(session),
                },
            )

            async with self._queue_guard:
                queued = self._queued_messages.pop(command.session_id, None)
            if queued:
                await self._set_queued_command(command.session_id, None)
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
            session.update_queued_command(command.prompt, command.image_paths, command.attachments)
        await self._save_session(session, commit=True)
