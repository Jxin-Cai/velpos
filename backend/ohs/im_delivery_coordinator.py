from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from application.im_binding.im_channel_application_service import (
    ImChannelApplicationService,
    RetryableInboundError,
)
from application.im_binding.im_channel_facade import ImChannelFacade
from domain.im_binding.acl.channel_errors import (
    ChannelAuthError,
    ChannelPermanentError,
)
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.im_delivery import (
    ImDeliveryKind,
    ImInboxEvent,
    ImInboxStatus,
    ImOutboxMessage,
    ImOutboxStatus,
)
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import InboundMessage, OutboundMessage
from infr.config.database import async_session_factory
from infr.config.im_delivery_config import ImDeliveryPolicy
from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl
from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
from infr.repository.im_delivery_repository_impl import (
    ImDeliveryLeaseLostError,
    ImInboxRepositoryImpl,
    ImOutboxRepositoryImpl,
)
from infr.repository.session_repository_impl import SessionRepositoryImpl

logger = logging.getLogger(__name__)

#: WebSocket 事件名 — 队列条目进入终态失败时通知 Web 客户端刷新投递视图.
IM_DELIVERY_UPDATE_EVENT = "im_delivery_update"

#: 广播回调签名: (session_id, payload) -> None.
BroadcastFn = Callable[[str, dict[str, Any]], Awaitable[None]]


class _InboxOutcome(str, Enum):
    PROCESSED = "processed"
    RETRY = "retry"
    DEAD = "dead"


class _OutboxOutcome(str, Enum):
    SENT = "sent"
    RETRY = "retry"
    CANCELLED = "cancelled"
    DEAD = "dead"


class ImDeliveryCoordinator:
    """持久化的、与渠道无关的 IM 收发投递.

    所有渠道差异都由 :class:`ImChannelFacade` 吸收, 本类只关心队列语义:
    租约、重试退避、幂等与死信。队列参数由 :class:`ImDeliveryPolicy`
    提供, 可经环境变量调优。
    """

    def __init__(
        self,
        registry: ImChannelRegistry,
        *,
        policy: ImDeliveryPolicy | None = None,
        broadcast_fn: BroadcastFn | None = None,
    ) -> None:
        self._registry = registry
        self._facade = ImChannelFacade(registry)
        self._policy = policy or ImDeliveryPolicy.from_env()
        self._broadcast = broadcast_fn
        self._closing = False
        self._inbox_wakeup = asyncio.Event()
        self._outbox_wakeup = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._tasks:
            return
        self._closing = False
        self._inbox_wakeup = asyncio.Event()
        self._outbox_wakeup = asyncio.Event()
        self._tasks = [
            *[
                asyncio.create_task(
                    self._run_inbox(),
                    name=f"im-inbox-worker-{index}",
                )
                for index in range(self._policy.inbox_workers)
            ],
            *[
                asyncio.create_task(
                    self._run_outbox(),
                    name=f"im-outbox-worker-{index}",
                )
                for index in range(self._policy.outbox_workers)
            ],
        ]

    def wake_inbox(self) -> None:
        """唤醒入站 worker — 有新事件入队或死信被重投时调用."""
        self._inbox_wakeup.set()

    def wake_outbox(self) -> None:
        """唤醒出站 worker — 有新消息入队或死信被重投时调用."""
        self._outbox_wakeup.set()

    async def close(self) -> None:
        self._closing = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def accept_inbound(
        self, binding: ImBinding, message: InboundMessage,
    ) -> bool:
        if not message.external_message_id:
            raise ValueError("IM inbound message_id must not be empty")
        event = ImInboxEvent(
            id=0,
            channel_id=binding.channel_id or binding.id,
            channel_type=binding.channel_type.value,
            binding_id=binding.id,
            session_id=binding.session_id,
            external_message_id=message.external_message_id,
            content=message.plain_text,
            route=message.route,
            attachments=message.attachments(binding.channel_type.value),
        )
        async with async_session_factory() as db:
            accepted = await ImInboxRepositoryImpl(db).accept(event)
            await db.commit()
        if accepted is None:
            logger.info(
                "Duplicate IM inbound ignored: channel=%s message_id=%s",
                event.channel_id,
                message.external_message_id,
            )
            return False
        self.wake_inbox()
        return True

    async def enqueue_outbound(
        self,
        session_id: str,
        content: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
        deduplication_key: str | None = None,
        route: ChannelRoute | None = None,
        binding: ImBinding | None = None,
    ) -> int | None:
        if not content.strip() and not attachments:
            return None
        async with async_session_factory() as db:
            if binding is None:
                binding = await ImBindingRepositoryImpl(db).find_by_session_id(session_id)
            if binding is None or binding.binding_status != BindingStatus.BOUND:
                return None
            message = ImOutboxMessage(
                id=0,
                session_id=session_id,
                binding_id=binding.id,
                channel_id=binding.channel_id or binding.id,
                channel_type=binding.channel_type.value,
                content=content,
                attachments=list(attachments or []),
                deduplication_key=self._normalize_deduplication_key(
                    deduplication_key or f"im:{session_id}:{uuid.uuid4().hex}"
                ),
                route=route or self._facade.restore_route(binding),
            )
            saved = await ImOutboxRepositoryImpl(db).enqueue(message)
            await db.commit()
        self.wake_outbox()
        return saved.id

    async def _run_inbox(self) -> None:
        while not self._closing:
            try:
                processed = await self._process_one_inbox()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("IM inbox worker iteration failed", exc_info=True)
                processed = False
            if not processed and not self._closing:
                await self._wait_for_work(self._inbox_wakeup)

    async def _run_outbox(self) -> None:
        while not self._closing:
            try:
                processed = await self._process_one_outbox()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("IM outbox worker iteration failed", exc_info=True)
                processed = False
            if not processed and not self._closing:
                await self._wait_for_work(self._outbox_wakeup)

    async def _process_one_inbox(self) -> bool:
        async with async_session_factory() as db:
            repo = ImInboxRepositoryImpl(db)
            event = await repo.claim_next(datetime.now(), self._policy.lease_seconds)
            if event is None:
                await db.commit()
                return False
            await db.commit()

        try:
            async with async_session_factory() as db:
                binding = await ImBindingRepositoryImpl(db).find_by_session_id(event.session_id)
                if (
                    binding is None
                    or binding.id != event.binding_id
                    or binding.channel_type.value != event.channel_type
                    or binding.binding_status != BindingStatus.BOUND
                ):
                    await self._finish_inbox(
                        event,
                        _InboxOutcome.DEAD,
                        "IM binding changed before inbound processing",
                    )
                    return True

                from ohs.dependencies import (
                    _binding_repos_context,
                    _session_service_context,
                    _stage_inbound_attachments,
                    get_claude_agent_gateway,
                    get_connection_manager,
                    get_create_session_service_factory,
                )

                gateway = get_claude_agent_gateway()
                service = ImChannelApplicationService(
                    registry=self._registry,
                    binding_repo=ImBindingRepositoryImpl(db),
                    init_repo=ChannelInitRepositoryImpl(db),
                    session_service_factory=get_create_session_service_factory(),
                    connection_manager=get_connection_manager(),
                    get_pending_request_context_fn=gateway.get_pending_request_context,
                    resolve_user_response_fn=gateway.resolve_user_response,
                    enqueue_outbound_fn=self.enqueue_outbound,
                    stage_inbound_attachments_fn=_stage_inbound_attachments,
                    session_service_context_factory=_session_service_context,
                    binding_context_factory=_binding_repos_context,
                )
                await service.process_inbound_event(
                    binding,
                    event,
                    is_final_attempt=event.attempt_count >= self._policy.max_attempts,
                )
                await db.commit()
            await self._finish_inbox(event, _InboxOutcome.PROCESSED)
        except ImDeliveryLeaseLostError:
            logger.info(
                "IM inbox completion skipped after lease loss: inbox_id=%s attempt=%s",
                event.id,
                event.attempt_count,
            )
        except RetryableInboundError as exc:
            logger.info(
                "IM inbox deferred: inbox_id=%s attempt=%s reason=%s",
                event.id,
                event.attempt_count,
                exc,
            )
            try:
                await self._finish_inbox(event, _InboxOutcome.RETRY, str(exc))
            except ImDeliveryLeaseLostError:
                logger.info(
                    "IM inbox retry skipped after lease loss: inbox_id=%s attempt=%s",
                    event.id,
                    event.attempt_count,
                )
        except Exception as exc:
            logger.error(
                "IM inbox processing failed: inbox_id=%s attempt=%s",
                event.id,
                event.attempt_count,
                exc_info=True,
            )
            try:
                await self._finish_inbox(event, _InboxOutcome.RETRY, str(exc))
            except ImDeliveryLeaseLostError:
                logger.info(
                    "IM inbox retry skipped after lease loss: inbox_id=%s attempt=%s",
                    event.id,
                    event.attempt_count,
                )
        return True

    async def _process_one_outbox(self) -> bool:
        async with async_session_factory() as db:
            repo = ImOutboxRepositoryImpl(db)
            message = await repo.claim_next(
                datetime.now(), self._policy.lease_seconds,
            )
            if message is None:
                await db.commit()
                return False
            await db.commit()

        try:
            async with async_session_factory() as db:
                binding = await ImBindingRepositoryImpl(db).find_by_session_id(message.session_id)
                if (
                    binding is None
                    or binding.id != message.binding_id
                    or binding.channel_type.value != message.channel_type
                    or binding.binding_status != BindingStatus.BOUND
                ):
                    await self._finish_outbox(
                        message,
                        _OutboxOutcome.CANCELLED,
                        "IM binding changed before outbound delivery",
                    )
                    return True
                attachments = await self._resolve_outbound_attachments(
                    db,
                    message,
                )
            # 渠道调用可能耗时数秒, 放在会话外避免占着连接池等网络.
            receipt = await self._facade.send(
                binding,
                OutboundMessage.of_text_with_attachments(
                    message.content,
                    attachments,
                    route=message.route,
                    idempotency_key=message.deduplication_key,
                ),
            )
            await self._finish_outbox(
                message,
                _OutboxOutcome.SENT,
                external_message_id=receipt.external_message_id,
            )
        except ImDeliveryLeaseLostError:
            logger.info(
                "IM outbox completion skipped after lease loss: outbox_id=%s attempt=%s",
                message.id,
                message.attempt_count,
            )
        except ChannelAuthError as exc:
            # 凭证失效 — 重试只会继续失败, 标记实例需要重新初始化后取消投递.
            logger.error(
                "IM outbox delivery blocked by expired credentials: "
                "outbox_id=%s channel=%s",
                message.id,
                message.channel_type,
            )
            await self._mark_credentials_expired(message, str(exc))
            await self._settle_outbox(
                message, _OutboxOutcome.CANCELLED, str(exc),
            )
        except ChannelPermanentError as exc:
            logger.error(
                "IM outbox delivery rejected permanently: outbox_id=%s channel=%s",
                message.id,
                message.channel_type,
                exc_info=True,
            )
            await self._settle_outbox(message, _OutboxOutcome.DEAD, str(exc))
        except Exception as exc:
            logger.error(
                "IM outbox delivery failed: outbox_id=%s channel=%s attempt=%s",
                message.id,
                message.channel_type,
                message.attempt_count,
                exc_info=True,
            )
            try:
                await self._finish_outbox(
                    message,
                    _OutboxOutcome.RETRY,
                    str(exc),
                )
            except ImDeliveryLeaseLostError:
                logger.info(
                    "IM outbox retry skipped after lease loss: outbox_id=%s attempt=%s",
                    message.id,
                    message.attempt_count,
                )
        return True

    async def _finish_inbox(
        self,
        event: ImInboxEvent,
        outcome: _InboxOutcome,
        error_message: str = "",
    ) -> None:
        if outcome is _InboxOutcome.PROCESSED:
            event.mark_processed()
        elif (
            outcome is _InboxOutcome.DEAD
            or event.attempt_count >= self._policy.max_attempts
        ):
            event.mark_dead(error_message or "Maximum retry attempts reached")
        else:
            event.mark_retry(error_message, self._retry_delay(event.attempt_count))
        async with async_session_factory() as db:
            await ImInboxRepositoryImpl(db).save(event)
            await db.commit()
        if event.status is ImInboxStatus.DEAD:
            await self._notify_terminal_failure(
                event.session_id,
                ImDeliveryKind.INBOX,
                delivery_id=event.id,
                status=event.status.value,
                error_message=event.error_message,
            )

    async def _finish_outbox(
        self,
        message: ImOutboxMessage,
        outcome: _OutboxOutcome,
        error_message: str = "",
        external_message_id: str = "",
    ) -> None:
        if outcome is _OutboxOutcome.SENT:
            message.mark_sent(external_message_id)
        elif outcome is _OutboxOutcome.CANCELLED:
            message.mark_cancelled(error_message)
        elif outcome is _OutboxOutcome.DEAD:
            message.mark_dead(error_message)
        elif message.attempt_count >= self._policy.max_attempts:
            message.mark_dead(error_message or "Maximum retry attempts reached")
        else:
            message.mark_retry(error_message, self._retry_delay(message.attempt_count))
        async with async_session_factory() as db:
            await ImOutboxRepositoryImpl(db).save(message)
            await db.commit()
        if message.status in (ImOutboxStatus.DEAD, ImOutboxStatus.CANCELLED):
            await self._notify_terminal_failure(
                message.session_id,
                ImDeliveryKind.OUTBOX,
                delivery_id=message.id,
                status=message.status.value,
                error_message=message.error_message,
            )

    async def _notify_terminal_failure(
        self,
        session_id: str,
        kind: ImDeliveryKind,
        *,
        delivery_id: int,
        status: str,
        error_message: str,
    ) -> None:
        """终态失败要主动告诉 Web 客户端, 而不是等用户自己发现消息没送到."""
        if self._broadcast is None:
            return
        try:
            await self._broadcast(
                session_id,
                {
                    "event": IM_DELIVERY_UPDATE_EVENT,
                    "data": {
                        "kind": kind.value,
                        "delivery_id": delivery_id,
                        "status": status,
                        "error_message": error_message,
                    },
                },
            )
        except Exception:
            # 广播失败只影响提示的及时性, 不能反过来破坏队列终态写入.
            logger.error(
                "Failed to broadcast IM delivery failure: session=%s kind=%s id=%s",
                session_id,
                kind.value,
                delivery_id,
                exc_info=True,
            )

    async def _wait_for_work(self, wakeup: asyncio.Event) -> None:
        wakeup.clear()
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=1.0)
        except TimeoutError:
            pass

    async def _settle_outbox(
        self,
        message: ImOutboxMessage,
        outcome: _OutboxOutcome,
        error_message: str,
    ) -> None:
        """写入终态, 容忍租约已被其他 worker 抢走的情况."""
        try:
            await self._finish_outbox(message, outcome, error_message)
        except ImDeliveryLeaseLostError:
            logger.info(
                "IM outbox %s skipped after lease loss: outbox_id=%s attempt=%s",
                outcome.value,
                message.id,
                message.attempt_count,
            )

    async def _mark_credentials_expired(
        self, message: ImOutboxMessage, reason: str,
    ) -> None:
        try:
            async with async_session_factory() as db:
                init_repo = ChannelInitRepositoryImpl(db)
                channel_init = await init_repo.find_by_id(message.channel_id)
                if channel_init is None:
                    return
                channel_init.mark_credentials_expired(reason[:500])
                await init_repo.save(channel_init)
                await db.commit()
        except Exception:
            logger.warning(
                "Failed to mark channel credentials expired: channel=%s",
                message.channel_id,
                exc_info=True,
            )

    @staticmethod
    async def _resolve_outbound_attachments(
        db,
        message: ImOutboxMessage,
    ) -> list[dict[str, Any]]:
        if not message.attachments:
            return []
        session = await SessionRepositoryImpl(db).find_by_id(message.session_id)
        project_root = (
            Path(session.project_dir).expanduser().resolve()
            if session is not None and session.project_dir
            else None
        )
        resolved: list[dict[str, Any]] = []
        for attachment in message.attachments:
            item = dict(attachment)
            raw_path = str(item.get("path") or "")
            if raw_path and not Path(raw_path).is_absolute():
                if project_root is None:
                    raise ValueError(
                        "Cannot resolve relative outbound attachment without project directory"
                    )
                absolute_path = (project_root / raw_path).resolve()
                if absolute_path != project_root and project_root not in absolute_path.parents:
                    raise ValueError("Outbound attachment path escapes project workspace")
                item["path"] = str(absolute_path)
            resolved.append(item)
        return resolved

    def _retry_delay(self, attempt_count: int) -> int:
        """指数退避 + 抖动.

        渠道限流时同一批消息往往一起失败, 没有抖动就会在同一秒齐发重试,
        再次触发限流。
        """
        backoff = min(
            self._policy.max_backoff_seconds,
            2 ** min(max(attempt_count, 1), 8),
        )
        return backoff + secrets.randbelow(max(1, backoff // 2) + 1)

    @staticmethod
    def _normalize_deduplication_key(value: str) -> str:
        if len(value) <= 255:
            return value
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"
