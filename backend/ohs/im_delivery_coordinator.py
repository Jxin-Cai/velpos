from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from application.im_binding.im_channel_application_service import ImChannelApplicationService
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_delivery import ImInboxEvent, ImOutboxMessage
from domain.im_binding.model.im_binding import ImBinding
from infr.config.database import async_session_factory
from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl
from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
from infr.repository.im_delivery_repository_impl import (
    ImDeliveryLeaseLostError,
    ImInboxRepositoryImpl,
    ImOutboxRepositoryImpl,
)

logger = logging.getLogger(__name__)

_LEASE_SECONDS = 120
_MAX_ATTEMPTS = 8
_MAX_BACKOFF_SECONDS = 300


class _InboxOutcome(str, Enum):
    PROCESSED = "processed"
    RETRY = "retry"
    DEAD = "dead"


class _OutboxOutcome(str, Enum):
    SENT = "sent"
    RETRY = "retry"
    CANCELLED = "cancelled"


class ImDeliveryCoordinator:
    """Durable, channel-neutral delivery for Lark, QQ, WeChat and OpenIM."""

    def __init__(self, registry: ImChannelRegistry) -> None:
        self._registry = registry
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
        inbox_workers = self._configured_workers("IM_INBOX_WORKERS", 4)
        outbox_workers = self._configured_workers("IM_OUTBOX_WORKERS", 4)
        self._tasks = [
            *[
                asyncio.create_task(
                    self._run_inbox(),
                    name=f"im-inbox-worker-{index}",
                )
                for index in range(inbox_workers)
            ],
            *[
                asyncio.create_task(
                    self._run_outbox(),
                    name=f"im-outbox-worker-{index}",
                )
                for index in range(outbox_workers)
            ],
        ]

    async def close(self) -> None:
        self._closing = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def accept_inbound(
        self,
        binding: ImBinding,
        message_id: str,
        content: str,
        sender_id: str,
        group_id: str,
    ) -> bool:
        if not message_id:
            raise ValueError("IM inbound message_id must not be empty")
        event = ImInboxEvent(
            id=0,
            channel_id=binding.channel_id or binding.id,
            channel_type=binding.channel_type.value,
            binding_id=binding.id,
            session_id=binding.session_id,
            external_message_id=message_id,
            content=content,
            sender_id=sender_id,
            group_id=group_id,
        )
        async with async_session_factory() as db:
            accepted = await ImInboxRepositoryImpl(db).accept(event)
            await db.commit()
        if accepted is None:
            logger.info(
                "Duplicate IM inbound ignored: channel=%s message_id=%s",
                event.channel_id,
                message_id,
            )
            return False
        self._inbox_wakeup.set()
        return True

    async def enqueue_outbound(
        self,
        session_id: str,
        content: str,
        *,
        deduplication_key: str | None = None,
        reply_context: dict[str, Any] | None = None,
        binding: ImBinding | None = None,
    ) -> int | None:
        if not content.strip():
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
                deduplication_key=self._normalize_deduplication_key(
                    deduplication_key or f"im:{session_id}:{uuid.uuid4().hex}"
                ),
                reply_context=reply_context or self._build_reply_context(binding),
            )
            saved = await ImOutboxRepositoryImpl(db).enqueue(message)
            await db.commit()
        self._outbox_wakeup.set()
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
            event = await repo.claim_next(datetime.now(), _LEASE_SECONDS)
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
                )
                await service.process_inbound_event(
                    binding,
                    event.external_message_id,
                    event.content,
                    event.sender_id,
                    event.group_id,
                )
                await db.commit()
            await self._finish_inbox(event, _InboxOutcome.PROCESSED)
        except ImDeliveryLeaseLostError:
            logger.info(
                "IM inbox completion skipped after lease loss: inbox_id=%s attempt=%s",
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
            message = await repo.claim_next(datetime.now(), _LEASE_SECONDS)
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
                adapter = self._registry.get_adapter_factory(
                    ImChannelType(message.channel_type)
                )()
                external_message_id = await adapter.send_message(
                    binding,
                    message.content,
                    reply_context=message.reply_context,
                    idempotency_key=message.deduplication_key,
                )
            await self._finish_outbox(
                message,
                _OutboxOutcome.SENT,
                external_message_id=external_message_id,
            )
        except ImDeliveryLeaseLostError:
            logger.info(
                "IM outbox completion skipped after lease loss: outbox_id=%s attempt=%s",
                message.id,
                message.attempt_count,
            )
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
        elif outcome is _InboxOutcome.DEAD or event.attempt_count >= _MAX_ATTEMPTS:
            event.mark_dead(error_message or "Maximum retry attempts reached")
        else:
            event.mark_retry(error_message, self._retry_delay(event.attempt_count))
        async with async_session_factory() as db:
            await ImInboxRepositoryImpl(db).save(event)
            await db.commit()

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
        elif message.attempt_count >= _MAX_ATTEMPTS:
            message.mark_dead(error_message or "Maximum retry attempts reached")
        else:
            message.mark_retry(error_message, self._retry_delay(message.attempt_count))
        async with async_session_factory() as db:
            await ImOutboxRepositoryImpl(db).save(message)
            await db.commit()

    async def _wait_for_work(self, wakeup: asyncio.Event) -> None:
        wakeup.clear()
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=1.0)
        except TimeoutError:
            pass

    def _build_reply_context(self, binding: ImBinding) -> dict[str, Any]:
        adapter = self._registry.get_adapter_factory(binding.channel_type)()
        return adapter.build_reply_context(binding) or {}

    @staticmethod
    def _retry_delay(attempt_count: int) -> int:
        return min(_MAX_BACKOFF_SECONDS, 2 ** min(max(attempt_count, 1), 8))

    @staticmethod
    def _normalize_deduplication_key(value: str) -> str:
        if len(value) <= 255:
            return value
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _configured_workers(env_name: str, default: int) -> int:
        raw_value = os.getenv(env_name, str(default))
        try:
            return min(16, max(1, int(raw_value)))
        except ValueError:
            logger.warning(
                "Invalid %s=%r; using %s",
                env_name,
                raw_value,
                default,
            )
            return default
