from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.user.model.user import User, UserRole
from domain.user.repository.user_repository import UserRepository
from infr.repository.user_model import UserModel


class UserRepositoryImpl(UserRepository):

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def save(self, user: User) -> User:
        if user.id == 0:
            model = UserModel(
                username=user.username,
                display_name=user.display_name,
                role=user.role.value,
                hashed_password=user.hashed_password,
                created_time=user.created_at,
            )
            self._db.add(model)
            await self._db.flush()
            return User.reconstitute(
                id=model.id,
                username=model.username,
                display_name=model.display_name,
                role=UserRole(model.role),
                hashed_password=model.hashed_password,
                created_at=model.created_time,
            )
        else:
            model = await self._db.get(UserModel, user.id)
            if model is None:
                raise ValueError(f"User with id {user.id} not found")
            model.username = user.username
            model.display_name = user.display_name
            model.role = user.role.value
            model.hashed_password = user.hashed_password
            await self._db.flush()
            return user

    async def find_by_id(self, user_id: int) -> User | None:
        model = await self._db.get(UserModel, user_id)
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_username(self, username: str) -> User | None:
        stmt = select(UserModel).where(UserModel.username == username)
        result = await self._db.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User.reconstitute(
            id=model.id,
            username=model.username,
            display_name=model.display_name,
            role=UserRole(model.role),
            hashed_password=model.hashed_password,
            created_at=model.created_time,
        )
