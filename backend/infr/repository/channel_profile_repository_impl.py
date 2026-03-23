from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.channel_profile.model.channel_profile import ChannelProfile
from domain.channel_profile.repository.channel_profile_repository import (
    ChannelProfileRepository,
)
from infr.repository.channel_profile_model import ChannelProfileModel


class ChannelProfileRepositoryImpl(ChannelProfileRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, profile: ChannelProfile) -> None:
        model = self._to_model(profile)
        await self._session.merge(model)
        await self._session.flush()

    async def find_by_id(self, profile_id: str) -> ChannelProfile | None:
        stmt = select(ChannelProfileModel).where(
            ChannelProfileModel.profile_id == profile_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_all(self) -> list[ChannelProfile]:
        stmt = select(ChannelProfileModel).order_by(
            ChannelProfileModel.created_time.desc(),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def find_active(self) -> ChannelProfile | None:
        stmt = (
            select(ChannelProfileModel)
            .where(ChannelProfileModel.is_active == 1)
            .order_by(ChannelProfileModel.created_time.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def remove(self, profile_id: str) -> bool:
        stmt = select(ChannelProfileModel).where(
            ChannelProfileModel.profile_id == profile_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_model(profile: ChannelProfile) -> ChannelProfileModel:
        return ChannelProfileModel(
            profile_id=profile.profile_id,
            name=profile.name,
            host=profile.host,
            api_key=profile.api_key,
            auth_env_name=profile.auth_env_name,
            model_config_json=json.dumps(
                profile.model_config, ensure_ascii=False,
            ),
            is_active=1 if profile.is_active else 0,
            created_time=profile.created_time,
            updated_time=profile.updated_time,
        )

    @staticmethod
    def _to_domain(model: ChannelProfileModel) -> ChannelProfile:
        return ChannelProfile.reconstitute(
            profile_id=model.profile_id,
            name=model.name,
            host=model.host,
            api_key=model.api_key,
            auth_env_name=model.auth_env_name,
            model_config=json.loads(model.model_config_json),
            is_active=model.is_active == 1,
            created_time=model.created_time,
            updated_time=model.updated_time,
        )
