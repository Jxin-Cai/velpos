from __future__ import annotations

from abc import ABC, abstractmethod

from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding


class ImBindingRepository(ABC):

    @abstractmethod
    async def save(self, im_binding: ImBinding) -> None: ...

    @abstractmethod
    async def find_by_session_id(self, session_id: str) -> ImBinding | None: ...

    @abstractmethod
    async def find_by_session_and_channel(
        self, session_id: str, channel_type: ImChannelType,
    ) -> ImBinding | None: ...

    @abstractmethod
    async def find_by_channel(
        self, channel_type: ImChannelType, channel_address: str,
    ) -> ImBinding | None: ...

    @abstractmethod
    async def find_by_channel_id(self, channel_id: str) -> ImBinding | None: ...

    @abstractmethod
    async def find_by_id(self, id: str) -> ImBinding | None: ...

    @abstractmethod
    async def remove(self, session_id: str) -> bool: ...

    @abstractmethod
    async def remove_by_session_and_channel(
        self, session_id: str, channel_type: ImChannelType,
    ) -> bool: ...

    @abstractmethod
    async def find_all_bound(self) -> list[ImBinding]: ...
