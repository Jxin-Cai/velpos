from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.repository.im_binding_repository import ImBindingRepository
from infr.repository.im_binding_model import ImBindingModel


class ImBindingRepositoryImpl(ImBindingRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, im_binding: ImBinding) -> None:
        model = self._to_model(im_binding)
        await self._session.merge(model)
        await self._session.flush()

    async def find_by_session_id(self, session_id: str) -> ImBinding | None:
        stmt = select(ImBindingModel).where(
            ImBindingModel.session_id == session_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_session_and_channel(
        self, session_id: str, channel_type: ImChannelType,
    ) -> ImBinding | None:
        stmt = select(ImBindingModel).where(
            ImBindingModel.session_id == session_id,
            ImBindingModel.channel_type == channel_type.value,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_channel(
        self, channel_type: ImChannelType, channel_address: str,
    ) -> ImBinding | None:
        stmt = select(ImBindingModel).where(
            ImBindingModel.channel_type == channel_type.value,
            ImBindingModel.channel_address == channel_address,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_channel_id(self, channel_id: str) -> ImBinding | None:
        stmt = select(ImBindingModel).where(
            ImBindingModel.channel_id == channel_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_id(self, id: str) -> ImBinding | None:
        stmt = select(ImBindingModel).where(
            ImBindingModel.id == id,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def remove(self, session_id: str) -> bool:
        stmt = select(ImBindingModel).where(
            ImBindingModel.session_id == session_id,
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        if not models:
            return False
        for model in models:
            await self._session.delete(model)
        await self._session.flush()
        return True

    async def remove_by_session_and_channel(
        self, session_id: str, channel_type: ImChannelType,
    ) -> bool:
        stmt = select(ImBindingModel).where(
            ImBindingModel.session_id == session_id,
            ImBindingModel.channel_type == channel_type.value,
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        if not models:
            return False
        for model in models:
            await self._session.delete(model)
        await self._session.flush()
        return True

    async def find_all_bound(self) -> list[ImBinding]:
        stmt = select(ImBindingModel).where(
            ImBindingModel.binding_status == "bound",
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    @staticmethod
    def _to_model(im_binding: ImBinding) -> ImBindingModel:
        return ImBindingModel(
            id=im_binding.id,
            session_id=im_binding.session_id,
            channel_type=im_binding.channel_type.value,
            channel_id=im_binding.channel_id,
            channel_address=im_binding.channel_address,
            config_json=json.dumps(im_binding.config, ensure_ascii=False),
            im_user_id=im_binding.im_user_id,
            im_token=im_binding.im_token,
            binding_status=im_binding.binding_status.value,
            friend_user_id=im_binding.friend_user_id,
            qr_code_data=im_binding.qr_code_data,
            created_time=im_binding.created_at,
        )

    @staticmethod
    def _to_domain(model: ImBindingModel) -> ImBinding:
        try:
            config = json.loads(model.config_json) if model.config_json else {}
        except (json.JSONDecodeError, TypeError):
            config = {}

        try:
            channel_type = ImChannelType(model.channel_type)
        except ValueError:
            channel_type = ImChannelType.OPENIM

        return ImBinding.reconstitute(
            id=model.id,
            session_id=model.session_id,
            im_user_id=model.im_user_id,
            im_token=model.im_token,
            binding_status=BindingStatus(model.binding_status),
            friend_user_id=model.friend_user_id,
            qr_code_data=model.qr_code_data,
            created_at=model.created_time,
            channel_type=channel_type,
            channel_id=getattr(model, "channel_id", "") or "",
            channel_address=model.channel_address or "",
            config=config,
        )
