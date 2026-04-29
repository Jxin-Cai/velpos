from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from domain.session.model.session_status import SessionStatus
from domain.session.model.usage import Usage
from domain.session.repository.session_repository import SessionRepository
from infr.repository.session_model import SessionModel


class SessionRepositoryImpl(SessionRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, session: Session) -> None:
        model = self._to_model(session)
        try:
            await self._session.merge(model)
            await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise

    async def find_by_id(self, session_id: str) -> Session | None:
        stmt = select(SessionModel).where(
            SessionModel.session_id == session_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_all(self) -> list[Session]:
        stmt = select(SessionModel).order_by(
            SessionModel.updated_time.desc(),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def find_by_project_id(self, project_id: str) -> list[Session]:
        stmt = select(SessionModel).where(
            SessionModel.project_id == project_id,
        ).order_by(
            SessionModel.updated_time.desc(),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def remove(self, session_id: str) -> bool:
        stmt = select(SessionModel).where(
            SessionModel.session_id == session_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def find_by_sdk_session_id(self, sdk_session_id: str) -> Session | None:
        if not sdk_session_id:
            return None
        stmt = select(SessionModel).where(
            SessionModel.sdk_session_id == sdk_session_id,
        ).limit(1)
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    @staticmethod
    def _to_model(session: Session) -> SessionModel:
        return SessionModel(
            session_id=session.session_id,
            project_id=session.project_id,
            model=session.model,
            status=session.status.value,
            messages=SessionRepositoryImpl._serialize_messages(session.messages),
            input_tokens=session.usage.input_tokens,
            output_tokens=session.usage.output_tokens,
            continue_conversation=1 if session.continue_conversation else 0,
            project_dir=session.project_dir,
            name=session.name,
            sdk_session_id=session.sdk_session_id,
            last_input_tokens=session.last_input_tokens,
            pending_request_context_json=SessionRepositoryImpl._serialize_json_field(session.pending_request_context),
            queued_command_json=SessionRepositoryImpl._serialize_json_field(session.queued_command),
            cancel_requested=1 if session.cancel_requested else 0,
        )

    @staticmethod
    def _to_domain(model: SessionModel) -> Session:
        messages = SessionRepositoryImpl._deserialize_messages(model.messages)
        usage = Usage(
            input_tokens=model.input_tokens,
            output_tokens=model.output_tokens,
        )
        return Session.reconstitute(
            session_id=model.session_id,
            model=model.model,
            status=SessionStatus(model.status),
            messages=messages,
            usage=usage,
            continue_conversation=model.continue_conversation == 1,
            project_id=model.project_id,
            project_dir=model.project_dir,
            name=model.name,
            sdk_session_id=model.sdk_session_id,
            last_input_tokens=model.last_input_tokens,
            pending_request_context=SessionRepositoryImpl._deserialize_json_field(model.pending_request_context_json),
            queued_command=SessionRepositoryImpl._deserialize_json_field(model.queued_command_json),
            cancel_requested=model.cancel_requested == 1,
            updated_time=model.updated_time,
        )

    @staticmethod
    def _serialize_json_field(value: dict[str, Any] | None) -> str:
        if not value:
            return ""
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _deserialize_json_field(json_str: str) -> dict[str, Any] | None:
        if not json_str:
            return None
        return json.loads(json_str)

    @staticmethod
    def _serialize_messages(messages: list[Message]) -> str:
        return json.dumps(
            [{"type": msg.message_type.value, "content": msg.content} for msg in messages],
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_messages(json_str: str) -> list[Message]:
        items: list[dict[str, Any]] = json.loads(json_str)
        return [
            Message(
                message_type=MessageType(item["type"]),
                content=item["content"],
            )
            for item in items
        ]

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def rollback(self) -> None:
        await self._session.rollback()

    async def close(self) -> None:
        await self._session.close()
