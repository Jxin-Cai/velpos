from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.im_binding.model.im_delivery import ImInboxEvent, ImOutboxMessage


class ImInboxRepository(ABC):
    @abstractmethod
    async def accept(self, event: ImInboxEvent) -> ImInboxEvent | None: ...

    @abstractmethod
    async def claim_next(self, now: datetime, lease_seconds: int) -> ImInboxEvent | None: ...

    @abstractmethod
    async def save(self, event: ImInboxEvent) -> None: ...

    @abstractmethod
    async def has_processable(self, now: datetime) -> bool: ...


class ImOutboxRepository(ABC):
    @abstractmethod
    async def enqueue(self, message: ImOutboxMessage) -> ImOutboxMessage: ...

    @abstractmethod
    async def claim_next(self, now: datetime, lease_seconds: int) -> ImOutboxMessage | None: ...

    @abstractmethod
    async def save(self, message: ImOutboxMessage) -> None: ...

    @abstractmethod
    async def has_processable(self, now: datetime) -> bool: ...
