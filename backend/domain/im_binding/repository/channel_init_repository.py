from __future__ import annotations

from abc import ABC, abstractmethod

from domain.im_binding.model.channel_init import ChannelInit
from domain.im_binding.model.channel_type import ImChannelType


class ChannelInitRepository(ABC):

    @abstractmethod
    async def save(self, channel_init: ChannelInit) -> None: ...

    @abstractmethod
    async def find_by_id(self, id: str) -> ChannelInit | None: ...

    @abstractmethod
    async def find_by_channel_type(
        self, channel_type: ImChannelType,
    ) -> ChannelInit | None:
        """Legacy: find first instance by channel_type (for backward compat)."""
        ...

    @abstractmethod
    async def find_all_by_channel_type(
        self, channel_type: ImChannelType,
    ) -> list[ChannelInit]: ...

    @abstractmethod
    async def find_all(self) -> list[ChannelInit]: ...

    @abstractmethod
    async def remove(self, id: str) -> bool: ...
