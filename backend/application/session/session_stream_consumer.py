from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from application.session.session_observability_recorder import SessionObservabilityRecorder
from application.session.session_presenter import SessionPresenter
from domain.session.acl.claude_agent_gateway import ClaudeAgentGateway
from domain.session.acl.connection_manager import ConnectionManager
from domain.session.model.session import Session
from domain.session.service.message_conversion_service import MessageConversionService

logger = logging.getLogger(__name__)


class SessionStreamConsumer:

    _STREAM_MSG_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        recorder: SessionObservabilityRecorder,
        claude_agent_gateway: ClaudeAgentGateway,
        connection_manager: ConnectionManager,
        save_session_fn: Callable[..., Awaitable[None]],
        accept_sdk_session_id_fn: Callable[..., Awaitable[bool]],
        cancelled_sessions: set[str],
    ) -> None:
        self._recorder = recorder
        self._claude_agent_gateway = claude_agent_gateway
        self._connection_manager = connection_manager
        self._save_session = save_session_fn
        self._accept_or_reject_sdk_session_id = accept_sdk_session_id_fn
        self._cancelled_sessions = cancelled_sessions

    @staticmethod
    def _tool_names_from_content(content: dict[str, Any]) -> list[str]:
        names: list[str] = []
        if isinstance(content, dict):
            for block in content.get("blocks", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = str(block.get("name") or "")
                    if name:
                        names.append(name)
        return names

    async def consume(
        self,
        session: Session,
        msg_stream: AsyncIterator[dict],
        run_id: str,
    ) -> bool:
        loop = asyncio.get_event_loop()
        last_save_time = loop.time()
        save_interval = 2.0

        saw_context_input_usage = False
        got_result = False
        stream_step = await self._recorder.start_run_step(
            session.session_id,
            run_id,
            "stream",
            "接收 Claude 消息流",
        )
        message_count = 0
        tool_count = 0
        waiting_count = 0
        aiter = msg_stream.__aiter__()
        next_msg_task: asyncio.Task | None = None
        try:
            while True:
                if next_msg_task is None:
                    next_msg_task = asyncio.create_task(aiter.__anext__())
                try:
                    msg_dict = await asyncio.wait_for(
                        asyncio.shield(next_msg_task), timeout=self._STREAM_MSG_TIMEOUT,
                    )
                    next_msg_task = None
                except StopAsyncIteration:
                    next_msg_task = None
                    break
                except asyncio.TimeoutError:
                    if not self._claude_agent_gateway.is_process_alive(session.session_id):
                        logger.error(
                            "[session=%s] CLI 进程已退出且消息流超时, 终止消费",
                            session.session_id,
                        )
                        next_msg_task.cancel()
                        raise RuntimeError("Claude CLI process exited unexpectedly")
                    logger.info(
                        "[session=%s] 消息流等待超时但进程仍存活, 继续等待",
                        session.session_id,
                    )
                    waiting_count += 1
                    await self._recorder.record_audit_event(
                        session.session_id,
                        "stream_waiting",
                        payload={"run_id": run_id, "waiting_count": waiting_count},
                    )
                    await self._recorder.record_timeline_event(
                        session.session_id,
                        run_id,
                        "stream_waiting",
                        "等待 Claude 输出",
                        {"waiting_count": waiting_count},
                    )
                    await self._connection_manager.broadcast(
                        session.session_id,
                        {"event": "stream_waiting", "status": "waiting_output", "waiting_count": waiting_count},
                    )
                    continue
                msg_type_str = msg_dict["message_type"]

                if msg_type_str == "_meta":
                    if msg_dict.get("resume_failed"):
                        session.update_sdk_session_id("")
                        await self._save_session(session, commit=True)
                        await self._recorder.record_audit_event(
                            session.session_id,
                            "sdk_resume_failed",
                            payload={"run_id": run_id},
                        )
                        await self._connection_manager.broadcast(
                            session.session_id,
                            {"event": "status_change", "data": SessionPresenter.session_to_dict(session)},
                        )
                    continue

                message = MessageConversionService.convert_stream_message(msg_dict)
                if message is None:
                    logger.warning(
                        "[session=%s] 未知消息类型: %s, 跳过",
                        session.session_id,
                        msg_type_str,
                    )
                    continue

                session.add_message(message)
                message_count += 1

                sdk_uuid = msg_dict.get("sdk_user_message_uuid")
                if sdk_uuid:
                    session.set_sdk_uuid_for_last_user_message(sdk_uuid)

                tool_names = self._tool_names_from_content(message.content)
                tool_count += len(tool_names)

                logger.info(
                    "[session=%s] Claude回复 [%s]",
                    session.session_id,
                    msg_type_str,
                )

                await self._connection_manager.broadcast(
                    session.session_id,
                    {"event": "message", "data": {"type": message.message_type.value, "content": message.content}},
                )
                for event_type, title, payload in self._recorder.timeline_events_for_message(
                    msg_type_str,
                    message.content,
                    msg_dict,
                ):
                    await self._recorder.record_timeline_event(
                        session.session_id,
                        run_id,
                        event_type,
                        title,
                        payload,
                        status="failed" if payload.get("is_error") else "completed",
                    )
                await self._recorder.progress_run_step(
                    stream_step,
                    {
                        "message_count": message_count,
                        "last_message_type": msg_type_str,
                        "last_tool_names": tool_names,
                        "tool_count": tool_count,
                    },
                    commit=False,
                )

                if "context_input_tokens" in msg_dict:
                    session.update_last_input_tokens(msg_dict["context_input_tokens"])
                    saw_context_input_usage = True

                if "input_tokens" in msg_dict and "output_tokens" in msg_dict:
                    if not saw_context_input_usage:
                        content = msg_dict.get("content", {})
                        num_turns = max(
                            msg_dict.get("num_turns")
                            or content.get("num_turns")
                            or 1,
                            1,
                        )
                        if num_turns == 1:
                            session.update_last_input_tokens(msg_dict["input_tokens"])
                        else:
                            estimated = int(msg_dict["input_tokens"] * 2 / (num_turns + 1))
                            session.update_last_input_tokens(estimated)

                    if (
                        session.sdk_session_id
                        and session.usage.input_tokens == 0
                        and session.usage.output_tokens == 0
                    ):
                        session.initialize_usage(
                            input_tokens=msg_dict["input_tokens"],
                            output_tokens=msg_dict["output_tokens"],
                        )
                        logger.info(
                            "[session=%s] resume 首次 usage 设定: in=%d, out=%d",
                            session.session_id,
                            msg_dict["input_tokens"],
                            msg_dict["output_tokens"],
                        )
                    else:
                        session.update_usage(
                            input_tokens=msg_dict["input_tokens"],
                            output_tokens=msg_dict["output_tokens"],
                        )

                if "sdk_session_id" in msg_dict:
                    new_sid = msg_dict["sdk_session_id"]
                    if new_sid:
                        await self._accept_or_reject_sdk_session_id(session, new_sid, "query", run_id)

                now = loop.time()
                is_result = msg_type_str == "result"
                if is_result:
                    got_result = True
                if is_result or (now - last_save_time >= save_interval):
                    if session.session_id not in self._cancelled_sessions:
                        try:
                            await self._save_session(session, commit=True)
                            last_save_time = now
                        except Exception:
                            logger.warning(
                                "[session=%s] periodic save failed",
                                session.session_id, exc_info=True,
                            )
            await self._recorder.complete_run_step(
                stream_step,
                {"message_count": message_count, "tool_count": tool_count, "got_result": got_result},
            )
            return got_result
        except Exception as exc:
            await self._recorder.fail_run_step(stream_step, {"error": str(exc)[:500]})
            raise
        finally:
            if next_msg_task is not None and not next_msg_task.done():
                next_msg_task.cancel()
