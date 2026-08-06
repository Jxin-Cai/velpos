from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from domain.user.model.user import User, UserRole
from domain.user.repository.user_repository import UserRepository

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


class AuthApplicationService:

    def __init__(
        self,
        user_repository: UserRepository,
        jwt_secret: str,
        jwt_expire_minutes: int,
        mode: str = "dev",
    ) -> None:
        self._user_repo = user_repository
        self._jwt_secret = jwt_secret
        self._jwt_expire_minutes = jwt_expire_minutes
        self._mode = mode

    async def register(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
    ) -> User:
        existing = await self._user_repo.find_by_username(username)
        if existing is not None:
            from domain.shared.business_exception import BusinessException
            raise BusinessException("Username already exists", "USER_EXISTS")

        role = UserRole.MEMBER
        if self._mode == "pro":
            has_active_admin = await self._has_usable_admin()
            if not has_active_admin:
                role = UserRole.ADMIN

        hashed = self._hash_password(password)
        user = User.create(
            username=username,
            display_name=display_name or username,
            hashed_password=hashed,
            role=role,
        )
        return await self._user_repo.save(user)

    async def _has_usable_admin(self) -> bool:
        admin = await self._user_repo.find_by_username("admin")
        if admin is not None and admin.hashed_password:
            return True
        return False

    async def login(self, username: str, password: str) -> tuple[User, str]:
        from domain.shared.business_exception import BusinessException

        user = await self._user_repo.find_by_username(username)
        if user is None:
            raise BusinessException("Invalid username or password", "AUTH_FAILED")

        if not user.hashed_password:
            raise BusinessException("Invalid username or password", "AUTH_FAILED")

        if not user.is_active:
            raise BusinessException("Account is disabled", "ACCOUNT_DISABLED")

        if not self._verify_password(password, user.hashed_password):
            raise BusinessException("Invalid username or password", "AUTH_FAILED")

        # Lazy migration: re-hash legacy PBKDF2 passwords with bcrypt
        if not user.hashed_password.startswith("$2b$"):
            user.update_password(self._hash_password(password))
            await self._user_repo.save(user)

        token = self._generate_token(user)  # instance method – uses self._jwt_secret
        return user, token

    async def get_user_by_id(self, user_id: int) -> User | None:
        return await self._user_repo.find_by_id(user_id)

    def verify_token(self, token: str) -> int | None:
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=[_ALGORITHM])
            return int(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, ValueError):
            return None

    def _generate_token(self, user: User) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self._jwt_expire_minutes)
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "exp": expire,
        }
        return jwt.encode(payload, self._jwt_secret, algorithm=_ALGORITHM)

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def _verify_password(self, password: str, hashed: str) -> bool:
        if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
            return bcrypt.checkpw(password.encode(), hashed.encode())
        # Legacy PBKDF2 path for passwords hashed before bcrypt migration
        salt = self._jwt_secret[:16]
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 100_000
        ).hex()
        return hmac.compare_digest(computed, hashed)
