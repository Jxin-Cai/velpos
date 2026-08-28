from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime

from domain.im_binding.model.im_delivery import (
    ImInboxEvent,
    ImInboxStatus,
    ImOutboxMessage,
    ImOutboxStatus,
)


class ImInboxRepository(ABC):
    @abstractmethod
    async def accept(self, event: ImInboxEvent) -> ImInboxEvent | None: ...

    @abstractmethod
    async def claim_next(self, now: datetime, lease_seconds: int) -> ImInboxEvent | None: ...

    @abstractmethod
    async def save(self, event: ImInboxEvent) -> None: ...

    @abstractmethod
    async def renew_lease(self, event: ImInboxEvent) -> None:
        """把事件的最新租约写回存储.

        事件已被其他 worker 重新认领时抛出租约丢失异常。
        """
        ...

    @abstractmethod
    async def release_pending_retries(self, session_id: str, now: datetime) -> int:
        """把会话所有等待退避的重试事件立即置为可认领, 返回释放数量.

        会话空闲时调用, 避免"会话忙"延后的消息干等退避到期。
        """
        ...

    @abstractmethod
    async def has_processable(self, now: datetime) -> bool: ...

    @abstractmethod
    async def find_recent_by_session(
        self,
        session_id: str,
        limit: int,
        statuses: Iterable[ImInboxStatus] | None = None,
    ) -> list[ImInboxEvent]:
        """按创建倒序返回会话最近的入站事件, 可选按状态过滤."""
        ...

    @abstractmethod
    async def count_by_status(self, session_id: str) -> dict[ImInboxStatus, int]:
        """返回会话入站事件在各状态下的数量."""
        ...

    @abstractmethod
    async def requeue(self, event_id: int, session_id: str) -> ImInboxEvent | None:
        """把会话内的死信事件重新放回队列.

        事件不存在、不属于该会话或不处于可重投状态时返回 None。
        """
        ...


class ImOutboxRepository(ABC):
    @abstractmethod
    async def enqueue(self, message: ImOutboxMessage) -> ImOutboxMessage: ...

    @abstractmethod
    async def claim_next(self, now: datetime, lease_seconds: int) -> ImOutboxMessage | None: ...

    @abstractmethod
    async def save(self, message: ImOutboxMessage) -> None: ...

    @abstractmethod
    async def has_processable(self, now: datetime) -> bool: ...

    @abstractmethod
    async def find_recent_by_session(
        self,
        session_id: str,
        limit: int,
        statuses: Iterable[ImOutboxStatus] | None = None,
    ) -> list[ImOutboxMessage]:
        """按创建倒序返回会话最近的出站消息, 可选按状态过滤."""
        ...

    @abstractmethod
    async def count_by_status(self, session_id: str) -> dict[ImOutboxStatus, int]:
        """返回会话出站消息在各状态下的数量."""
        ...

    @abstractmethod
    async def requeue(self, message_id: int, session_id: str) -> ImOutboxMessage | None:
        """把会话内最终失败的消息重新放回队列.

        消息不存在、不属于该会话或不处于可重投状态时返回 None。
        """
        ...
