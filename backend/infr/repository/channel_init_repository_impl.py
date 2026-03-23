from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.im_binding.model.channel_init import ChannelInit
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.repository.channel_init_repository import ChannelInitRepository
from infr.repository.channel_init_model import ChannelInitModel


class ChannelInitRepositoryImpl(ChannelInitRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, channel_init: ChannelInit) -> None:
        model = self._to_model(channel_init)
        await self._session.merge(model)
        await self._session.flush()

    async def find_by_id(self, id: str) -> ChannelInit | None:
        stmt = select(ChannelInitModel).where(ChannelInitModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_channel_type(
        self, channel_type: ImChannelType,
    ) -> ChannelInit | None:
        stmt = select(ChannelInitModel).where(
            ChannelInitModel.channel_type == channel_type.value,
        ).limit(1)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_all_by_channel_type(
        self, channel_type: ImChannelType,
    ) -> list[ChannelInit]:
        stmt = select(ChannelInitModel).where(
            ChannelInitModel.channel_type == channel_type.value,
        ).order_by(ChannelInitModel.created_time)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_all(self) -> list[ChannelInit]:
        stmt = select(ChannelInitModel).order_by(ChannelInitModel.created_time)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove(self, id: str) -> bool:
        stmt = select(ChannelInitModel).where(ChannelInitModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_model(ci: ChannelInit) -> ChannelInitModel:
        return ChannelInitModel(
            id=ci.id,
            channel_type=ci.channel_type.value,
            name=ci.name,
            init_status=ci.init_status.value,
            config_json=json.dumps(ci.config, ensure_ascii=False),
            error_message=ci.error_message,
            created_time=ci.created_at,
            updated_time=ci.updated_at,
        )

    @staticmethod
    def _to_domain(model: ChannelInitModel) -> ChannelInit:
        try:
            config = json.loads(model.config_json) if model.config_json else {}
        except (json.JSONDecodeError, TypeError):
            config = {}

        return ChannelInit.reconstitute(
            id=model.id,
            channel_type=ImChannelType(model.channel_type),
            name=getattr(model, "name", "") or "",
            init_status=ChannelInitStatus(model.init_status),
            config=config,
            error_message=model.error_message or "",
            created_at=model.created_time,
            updated_at=model.updated_time,
        )
