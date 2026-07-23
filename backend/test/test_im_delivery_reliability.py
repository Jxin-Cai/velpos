from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domain.im_binding.model.im_delivery import (
    ImInboxEvent,
    ImInboxStatus,
    ImOutboxMessage,
    ImOutboxStatus,
)
from infr.repository.im_delivery_model import ImInboxEventModel, ImOutboxMessageModel
from infr.repository.im_delivery_repository_impl import (
    ImDeliveryLeaseLostError,
    ImInboxRepositoryImpl,
    ImOutboxRepositoryImpl,
)


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ImInboxEventModel.__table__.create)
        await connection.run_sync(ImOutboxMessageModel.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _inbox(message_id: str) -> ImInboxEvent:
    return ImInboxEvent(
        id=0,
        channel_id="channel-1",
        channel_type="lark",
        binding_id="binding1",
        session_id="session1",
        external_message_id=message_id,
        content="hello",
    )


def _outbox(key: str, content: str) -> ImOutboxMessage:
    return ImOutboxMessage(
        id=0,
        session_id="session1",
        binding_id="binding1",
        channel_id="channel-1",
        channel_type="lark",
        content=content,
        deduplication_key=key,
    )


@pytest.mark.asyncio
async def test_returns_duplicate_when_same_inbound_message_is_accepted_twice():
    # Arrange
    engine, session_factory = await _database()
    first = _inbox("external-1")
    duplicate = _inbox("external-1")

    try:
        async with session_factory() as session:
            repository = ImInboxRepositoryImpl(session)

            # Act
            accepted = await repository.accept(first)
            await session.commit()
            repeated = await repository.accept(duplicate)

            # Assert
            assert accepted is first
            assert repeated is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_blocks_later_outbound_when_earlier_message_is_unfinished():
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            first = await repository.enqueue(_outbox("key-1", "first"))
            second = await repository.enqueue(_outbox("key-2", "second"))
            await session.commit()

            # Act
            now = datetime.now()
            claimed_first = await repository.claim_next(now, lease_seconds=60)
            await session.commit()
            blocked_second = await repository.claim_next(now, lease_seconds=60)

            # Assert
            assert claimed_first is not None and claimed_first.id == first.id
            assert second.id != first.id
            assert blocked_second is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reclaims_inbound_when_processing_lease_has_expired():
    # Arrange
    engine, session_factory = await _database()
    now = datetime.now()

    try:
        async with session_factory() as session:
            repository = ImInboxRepositoryImpl(session)
            event = await repository.accept(_inbox("external-2"))
            assert event is not None
            await session.commit()
            event = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert event is not None
            event.lease_until = now - timedelta(seconds=1)
            await repository.save(event)
            await session.commit()

            # Act
            reclaimed = await repository.claim_next(now, lease_seconds=60)

            # Assert
            assert reclaimed is not None
            assert reclaimed.status == ImInboxStatus.PROCESSING
            assert reclaimed.attempt_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rejects_completion_when_inbox_lease_was_reclaimed():
    # Arrange
    engine, session_factory = await _database()

    try:
        async with session_factory() as session:
            repository = ImInboxRepositoryImpl(session)
            await repository.accept(_inbox("external-3"))
            await session.commit()
            stale_event = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert stale_event is not None
            await session.commit()

            model = await session.get(ImInboxEventModel, stale_event.id)
            assert model is not None
            model.attempt_count += 1
            await session.commit()
            stale_event.mark_processed()

            # Act / Assert
            with pytest.raises(ImDeliveryLeaseLostError):
                await repository.save(stale_event)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_claims_next_outbound_after_earlier_message_is_sent():
    # Arrange
    engine, session_factory = await _database()

    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            first = await repository.enqueue(_outbox("key-4", "first"))
            second = await repository.enqueue(_outbox("key-5", "second"))
            await session.commit()
            claimed_first = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed_first is not None and claimed_first.id == first.id
            await session.commit()
            claimed_first.mark_sent("external-1")
            await repository.save(claimed_first)
            await session.commit()

            # Act
            claimed_second = await repository.claim_next(
                datetime.now(),
                lease_seconds=60,
            )

            # Assert
            assert claimed_second is not None and claimed_second.id == second.id
    finally:
        await engine.dispose()


def test_moves_outbound_to_retry_when_delivery_fails():
    # Arrange
    message = _outbox("key-3", "payload")
    message.claim(lease_seconds=60)

    # Act
    message.mark_retry("temporary failure", delay_seconds=2)

    # Assert
    assert message.status == ImOutboxStatus.RETRY
    assert message.lease_until is None
    assert message.next_attempt_at > datetime.now()
