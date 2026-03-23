from __future__ import annotations

from abc import ABC, abstractmethod

from domain.channel_profile.model.channel_profile import ChannelProfile


class ChannelProfileRepository(ABC):

    @abstractmethod
    async def save(self, profile: ChannelProfile) -> None:
        """Save the ChannelProfile aggregate root.

        If a record with the given profile_id does not exist, inserts a new one (INSERT).
        If it already exists, updates all mutable fields
        (name, host, api_key, model_config, is_active, updated_time).
        model_config is stored as a JSON string in a single TEXT column.
        Must complete within a single transaction to guarantee aggregate consistency.
        """
        ...

    @abstractmethod
    async def find_by_id(self, profile_id: str) -> ChannelProfile | None:
        """Find a ChannelProfile aggregate root by profile_id.

        Returns a fully reconstituted aggregate via ChannelProfile.reconstitute.
        model_config column is deserialized from a JSON string to dict[str, str].
        Returns None if the profile_id does not exist.
        """
        ...

    @abstractmethod
    async def find_all(self) -> list[ChannelProfile]:
        """Find all channel profiles.

        Each record is fully reconstituted via ChannelProfile.reconstitute.
        Results are ordered by created_time in descending order.
        Returns an empty list if no data exists.
        """
        ...

    @abstractmethod
    async def find_active(self) -> ChannelProfile | None:
        """Find the currently active channel profile.

        Queries for the record with is_active set to True.
        Business rules guarantee at most one active record.
        Returns None if no active record exists.
        If multiple active records exist (data anomaly), returns the one
        with the earliest created_time.
        """
        ...

    @abstractmethod
    async def remove(self, profile_id: str) -> bool:
        """Remove the specified channel profile.

        Returns True if the profile_id existed and was successfully removed.
        Returns False if the profile_id did not exist.
        No cascade deletion is involved (ChannelProfile has no child entities).
        """
        ...
