from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.im_binding.model.im_delivery import (
    ImInboxEvent,
    ImInboxStatus,
    ImOutboxMessage,
    ImOutboxStatus,
)
from domain.im_binding.repository.im_delivery_repository import (
    ImInboxRepository,
    ImOutboxRepository,
)
from domain.shared.utils import safe_json_loads
from infr.repository.im_delivery_model import ImInboxEventModel, ImOutboxMessageModel


class ImDeliveryLeaseLostError(RuntimeError):
    """Raised when a stale worker tries to complete a reclaimed delivery."""


class ImInboxRepositoryImpl(ImInboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def accept(self, event: ImInboxEvent) -> ImInboxEvent | None:
        existing = await self._session.scalar(
            select(ImInboxEventModel).where(
                ImInboxEventModel.channel_id == event.channel_id,
                ImInboxEventModel.external_message_id == event.external_message_id,
            )
        )
        if existing is not None:
            return None

        model = self._to_model(event)
        try:
            async with self._session.begin_nested():
                self._session.add(model)
                await self._session.flush()
        except IntegrityError:
            return None
        event.id = model.id
        return event

    async def claim_next(self, now: datetime, lease_seconds: int) -> ImInboxEvent | None:
        earlier = aliased(ImInboxEventModel)
        processable = or_(
            and_(
                ImInboxEventModel.status.in_(
                    [ImInboxStatus.RECEIVED.value, ImInboxStatus.RETRY.value]
                ),
                ImInboxEventModel.next_attempt_at <= now,
            ),
            and_(
                ImInboxEventModel.status == ImInboxStatus.PROCESSING.value,
                ImInboxEventModel.lease_until.is_not(None),
                ImInboxEventModel.lease_until <= now,
            ),
        )
        model = await self._session.scalar(
            select(ImInboxEventModel)
            .where(
                processable,
                ~exists(
                    select(earlier.id).where(
                        earlier.session_id == ImInboxEventModel.session_id,
                        earlier.id < ImInboxEventModel.id,
                        earlier.status.in_(
                            [
                                ImInboxStatus.RECEIVED.value,
                                ImInboxStatus.RETRY.value,
                                ImInboxStatus.PROCESSING.value,
                            ]
                        ),
                    )
                ),
            )
            .order_by(ImInboxEventModel.created_at.asc(), ImInboxEventModel.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if model is None:
            return None
        event = self._to_domain(model)
        event.claim(lease_seconds)
        self._apply(model, event)
        return event

    async def save(self, event: ImInboxEvent) -> None:
        model = await self._session.scalar(
            select(ImInboxEventModel)
            .where(ImInboxEventModel.id == event.id)
            .with_for_update()
        )
        if model is None:
            raise ValueError(f"IM inbox event not found: {event.id}")
        if (
            model.status != ImInboxStatus.PROCESSING.value
            or model.attempt_count != event.attempt_count
        ):
            raise ImDeliveryLeaseLostError(
                f"IM inbox lease lost: id={event.id} attempt={event.attempt_count}"
            )
        self._apply(model, event)
        await self._session.flush()

    async def has_processable(self, now: datetime) -> bool:
        return bool(
            await self._session.scalar(
                select(
                    exists().where(
                        or_(
                            and_(
                                ImInboxEventModel.status.in_(
                                    [ImInboxStatus.RECEIVED.value, ImInboxStatus.RETRY.value]
                                ),
                                ImInboxEventModel.next_attempt_at <= now,
                            ),
                            and_(
                                ImInboxEventModel.status == ImInboxStatus.PROCESSING.value,
                                ImInboxEventModel.lease_until <= now,
                            ),
                        )
                    )
                )
            )
        )

    @staticmethod
    def _to_model(event: ImInboxEvent) -> ImInboxEventModel:
        return ImInboxEventModel(
            channel_id=event.channel_id,
            channel_type=event.channel_type,
            binding_id=event.binding_id,
            session_id=event.session_id,
            external_message_id=event.external_message_id,
            content=event.content,
            sender_id=event.sender_id,
            group_id=event.group_id,
            status=event.status.value,
            attempt_count=event.attempt_count,
            next_attempt_at=event.next_attempt_at,
            lease_until=event.lease_until,
            error_message=event.error_message,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    @staticmethod
    def _apply(model: ImInboxEventModel, event: ImInboxEvent) -> None:
        model.status = event.status.value
        model.attempt_count = event.attempt_count
        model.next_attempt_at = event.next_attempt_at
        model.lease_until = event.lease_until
        model.error_message = event.error_message
        model.updated_at = event.updated_at

    @staticmethod
    def _to_domain(model: ImInboxEventModel) -> ImInboxEvent:
        return ImInboxEvent(
            id=model.id,
            channel_id=model.channel_id,
            channel_type=model.channel_type,
            binding_id=model.binding_id,
            session_id=model.session_id,
            external_message_id=model.external_message_id,
            content=model.content,
            sender_id=model.sender_id,
            group_id=model.group_id,
            status=ImInboxStatus(model.status),
            attempt_count=model.attempt_count,
            next_attempt_at=model.next_attempt_at,
            lease_until=model.lease_until,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ImOutboxRepositoryImpl(ImOutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, message: ImOutboxMessage) -> ImOutboxMessage:
        existing = await self._session.scalar(
            select(ImOutboxMessageModel).where(
                ImOutboxMessageModel.deduplication_key == message.deduplication_key
            )
        )
        if existing is not None:
            return self._to_domain(existing)

        model = self._to_model(message)
        try:
            async with self._session.begin_nested():
                self._session.add(model)
                await self._session.flush()
        except IntegrityError:
            existing = await self._session.scalar(
                select(ImOutboxMessageModel).where(
                    ImOutboxMessageModel.deduplication_key == message.deduplication_key
                )
            )
            if existing is None:
                raise
            return self._to_domain(existing)
        message.id = model.id
        return message

    async def claim_next(self, now: datetime, lease_seconds: int) -> ImOutboxMessage | None:
        earlier = aliased(ImOutboxMessageModel)
        processable = or_(
            and_(
                ImOutboxMessageModel.status.in_(
                    [ImOutboxStatus.PENDING.value, ImOutboxStatus.RETRY.value]
                ),
                ImOutboxMessageModel.next_attempt_at <= now,
            ),
            and_(
                ImOutboxMessageModel.status == ImOutboxStatus.SENDING.value,
                ImOutboxMessageModel.lease_until.is_not(None),
                ImOutboxMessageModel.lease_until <= now,
            ),
        )
        model = await self._session.scalar(
            select(ImOutboxMessageModel)
            .where(
                processable,
                ~exists(
                    select(earlier.id).where(
                        earlier.session_id == ImOutboxMessageModel.session_id,
                        earlier.id < ImOutboxMessageModel.id,
                        earlier.status.in_(
                            [
                                ImOutboxStatus.PENDING.value,
                                ImOutboxStatus.RETRY.value,
                                ImOutboxStatus.SENDING.value,
                            ]
                        ),
                    )
                ),
            )
            .order_by(ImOutboxMessageModel.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if model is None:
            return None
        message = self._to_domain(model)
        message.claim(lease_seconds)
        self._apply(model, message)
        return message

    async def save(self, message: ImOutboxMessage) -> None:
        model = await self._session.scalar(
            select(ImOutboxMessageModel)
            .where(ImOutboxMessageModel.id == message.id)
            .with_for_update()
        )
        if model is None:
            raise ValueError(f"IM outbox message not found: {message.id}")
        if (
            model.status != ImOutboxStatus.SENDING.value
            or model.attempt_count != message.attempt_count
        ):
            raise ImDeliveryLeaseLostError(
                f"IM outbox lease lost: id={message.id} attempt={message.attempt_count}"
            )
        self._apply(model, message)
        await self._session.flush()

    async def has_processable(self, now: datetime) -> bool:
        return bool(
            await self._session.scalar(
                select(
                    exists().where(
                        or_(
                            and_(
                                ImOutboxMessageModel.status.in_(
                                    [ImOutboxStatus.PENDING.value, ImOutboxStatus.RETRY.value]
                                ),
                                ImOutboxMessageModel.next_attempt_at <= now,
                            ),
                            and_(
                                ImOutboxMessageModel.status == ImOutboxStatus.SENDING.value,
                                ImOutboxMessageModel.lease_until <= now,
                            ),
                        )
                    )
                )
            )
        )

    @staticmethod
    def _to_model(message: ImOutboxMessage) -> ImOutboxMessageModel:
        return ImOutboxMessageModel(
            session_id=message.session_id,
            binding_id=message.binding_id,
            channel_id=message.channel_id,
            channel_type=message.channel_type,
            content=message.content,
            deduplication_key=message.deduplication_key,
            reply_context_json=json.dumps(message.reply_context, ensure_ascii=False),
            status=message.status.value,
            attempt_count=message.attempt_count,
            next_attempt_at=message.next_attempt_at,
            lease_until=message.lease_until,
            error_message=message.error_message,
            external_message_id=message.external_message_id,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    @staticmethod
    def _apply(model: ImOutboxMessageModel, message: ImOutboxMessage) -> None:
        model.status = message.status.value
        model.attempt_count = message.attempt_count
        model.next_attempt_at = message.next_attempt_at
        model.lease_until = message.lease_until
        model.error_message = message.error_message
        model.external_message_id = message.external_message_id
        model.updated_at = message.updated_at

    @staticmethod
    def _to_domain(model: ImOutboxMessageModel) -> ImOutboxMessage:
        return ImOutboxMessage(
            id=model.id,
            session_id=model.session_id,
            binding_id=model.binding_id,
            channel_id=model.channel_id,
            channel_type=model.channel_type,
            content=model.content,
            deduplication_key=model.deduplication_key,
            reply_context=safe_json_loads(model.reply_context_json, default={}),
            status=ImOutboxStatus(model.status),
            attempt_count=model.attempt_count,
            next_attempt_at=model.next_attempt_at,
            lease_until=model.lease_until,
            error_message=model.error_message,
            external_message_id=model.external_message_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
