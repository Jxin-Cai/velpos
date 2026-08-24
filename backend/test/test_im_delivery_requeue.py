"""死信重投与投递可观测性测试.

覆盖三层行为: 领域对象的重投状态机、仓储的按会话查询/计数/原子重投,
以及协调器在消息进入终态失败时的 WebSocket 通知。
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.im_delivery import (
    ImDeliveryKind,
    ImInboxEvent,
    ImInboxStatus,
    ImOutboxMessage,
    ImOutboxStatus,
)
from infr.config.im_delivery_config import ImDeliveryPolicy
from infr.repository.im_delivery_model import ImInboxEventModel, ImOutboxMessageModel
from infr.repository.im_delivery_repository_impl import (
    ImInboxRepositoryImpl,
    ImOutboxRepositoryImpl,
)
from ohs.im_delivery_coordinator import (
    IM_DELIVERY_UPDATE_EVENT,
    ImDeliveryCoordinator,
    _OutboxOutcome,
)


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ImInboxEventModel.__table__.create)
        await connection.run_sync(ImOutboxMessageModel.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _outbox(key: str, session_id: str = "session1") -> ImOutboxMessage:
    return ImOutboxMessage(
        id=0,
        session_id=session_id,
        binding_id="binding1",
        channel_id="channel-1",
        channel_type="lark",
        content=f"content-{key}",
        deduplication_key=key,
    )


def _inbox(message_id: str, session_id: str = "session1") -> ImInboxEvent:
    return ImInboxEvent(
        id=0,
        channel_id="channel-1",
        channel_type="lark",
        binding_id="binding1",
        session_id=session_id,
        external_message_id=message_id,
        content="hello",
    )


# ── 领域: 重投状态机 ──


def test_resets_attempt_count_when_dead_outbound_is_requeued() -> None:
    # Arrange
    message = _outbox("key-1")
    message.claim(lease_seconds=60)
    message.mark_dead("permanent failure")

    # Act
    message.requeue()

    # Assert
    assert message.status == ImOutboxStatus.RETRY
    assert message.attempt_count == 0
    assert message.next_attempt_at <= datetime.now()


def test_allows_requeue_when_outbound_message_is_cancelled() -> None:
    # Arrange
    message = _outbox("key-2")
    message.claim(lease_seconds=60)
    message.mark_cancelled("credentials expired")

    # Act
    message.requeue()

    # Assert
    assert message.status == ImOutboxStatus.RETRY


def test_rejects_requeue_when_outbound_message_is_sent() -> None:
    # Arrange
    message = _outbox("key-3")
    message.claim(lease_seconds=60)
    message.mark_sent("external-1")

    # Act / Assert
    with pytest.raises(ValueError):
        message.requeue()


def test_rejects_requeue_when_inbound_event_is_processed() -> None:
    # Arrange
    event = _inbox("external-1")
    event.claim(lease_seconds=60)
    event.mark_processed()

    # Act / Assert
    with pytest.raises(ValueError):
        event.requeue()


# ── 仓储: 原子重投 ──


@pytest.mark.asyncio
async def test_makes_dead_outbound_claimable_when_requeued() -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            saved = await repository.enqueue(_outbox("key-4"))
            await session.commit()
            claimed = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed is not None
            claimed.mark_dead("boom")
            await repository.save(claimed)
            await session.commit()

            # Act
            requeued = await repository.requeue(saved.id, "session1")
            await session.commit()
            reclaimed = await repository.claim_next(datetime.now(), lease_seconds=60)

            # Assert
            assert requeued is not None
            assert reclaimed is not None and reclaimed.id == saved.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ignores_requeue_when_outbound_belongs_to_other_session() -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            saved = await repository.enqueue(_outbox("key-5"))
            await session.commit()
            claimed = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed is not None
            claimed.mark_dead("boom")
            await repository.save(claimed)
            await session.commit()

            # Act
            requeued = await repository.requeue(saved.id, "other-session")

            # Assert
            assert requeued is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ignores_requeue_when_outbound_is_still_pending() -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            saved = await repository.enqueue(_outbox("key-6"))
            await session.commit()

            # Act
            requeued = await repository.requeue(saved.id, "session1")

            # Assert
            assert requeued is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_makes_dead_inbound_claimable_when_requeued() -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImInboxRepositoryImpl(session)
            accepted = await repository.accept(_inbox("external-2"))
            assert accepted is not None
            await session.commit()
            claimed = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed is not None
            claimed.mark_dead("boom")
            await repository.save(claimed)
            await session.commit()

            # Act
            requeued = await repository.requeue(accepted.id, "session1")
            await session.commit()
            reclaimed = await repository.claim_next(datetime.now(), lease_seconds=60)

            # Assert
            assert requeued is not None
            assert reclaimed is not None and reclaimed.id == accepted.id
    finally:
        await engine.dispose()


# ── 仓储: 状态计数与未结清查询 ──


@pytest.mark.asyncio
async def test_counts_outbound_by_status_when_queue_has_mixed_outcomes() -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            await repository.enqueue(_outbox("key-7"))
            claimed = None
            second = await repository.enqueue(_outbox("key-8"))
            await session.commit()
            claimed = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed is not None
            claimed.mark_sent("external-1")
            await repository.save(claimed)
            await session.commit()
            assert second is not None

            # Act
            counts = await repository.count_by_status("session1")

            # Assert
            assert counts == {
                ImOutboxStatus.SENT: 1,
                ImOutboxStatus.PENDING: 1,
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_filters_unsettled_outbound_when_statuses_are_given() -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            await repository.enqueue(_outbox("key-9"))
            await repository.enqueue(_outbox("key-10"))
            await session.commit()
            claimed = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed is not None
            claimed.mark_sent("external-1")
            await repository.save(claimed)
            await session.commit()

            # Act
            unsettled = await repository.find_recent_by_session(
                "session1", 10, statuses=(ImOutboxStatus.PENDING,),
            )

            # Assert
            assert [item.status for item in unsettled] == [ImOutboxStatus.PENDING]
    finally:
        await engine.dispose()


# ── 协调器: 终态失败通知 ──


@pytest.mark.asyncio
async def test_broadcasts_update_when_outbound_message_dead_letters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    engine, session_factory = await _database()
    try:
        async with session_factory() as session:
            repository = ImOutboxRepositoryImpl(session)
            await repository.enqueue(_outbox("key-11"))
            await session.commit()
            claimed = await repository.claim_next(datetime.now(), lease_seconds=60)
            assert claimed is not None
            await session.commit()

        @asynccontextmanager
        async def fake_session_factory():
            async with session_factory() as db:
                yield db

        monkeypatch.setattr(
            "ohs.im_delivery_coordinator.async_session_factory",
            fake_session_factory,
        )
        broadcast = AsyncMock()
        coordinator = ImDeliveryCoordinator(
            ImChannelRegistry(),
            policy=ImDeliveryPolicy(max_attempts=1),
            broadcast_fn=broadcast,
        )

        # Act — attempt_count 已达上限, RETRY 结果会落成死信.
        await coordinator._finish_outbox(claimed, _OutboxOutcome.RETRY, "boom")

        # Assert
        broadcast.assert_awaited_once()
        session_id, payload = broadcast.await_args.args
        assert session_id == "session1"
        assert payload["event"] == IM_DELIVERY_UPDATE_EVENT
        assert payload["data"]["kind"] == ImDeliveryKind.OUTBOX.value
        assert payload["data"]["status"] == ImOutboxStatus.DEAD.value
    finally:
        await engine.dispose()
