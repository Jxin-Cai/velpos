from __future__ import annotations

from abc import ABC, abstractmethod

from domain.im_binding.model.channel_init import ChannelInit


class ChannelInitRepository(ABC):

    @abstractmethod
    async def save(self, channel_init: ChannelInit) -> None: ...

    @abstractmethod
    async def find_by_id(self, channel_init_id: str) -> ChannelInit | None: ...

    @abstractmethod
    async def find_all(self) -> list[ChannelInit]: ...

    @abstractmethod
    async def remove(self, channel_init_id: str) -> bool: ...
