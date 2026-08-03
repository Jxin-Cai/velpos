from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class UserRole(Enum):
    ADMIN = "admin"
    MEMBER = "member"


@dataclass
class User:
    _id: int
    _username: str
    _display_name: str
    _role: UserRole
    _hashed_password: str
    _created_at: datetime = field(default_factory=datetime.now)
    _is_active: bool = True

    @property
    def id(self) -> int:
        return self._id

    @property
    def username(self) -> str:
        return self._username

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def role(self) -> UserRole:
        return self._role

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_admin(self) -> bool:
        return self._role == UserRole.ADMIN

    @classmethod
    def create(
        cls,
        username: str,
        display_name: str,
        hashed_password: str,
        role: UserRole = UserRole.MEMBER,
    ) -> User:
        return cls(
            _id=0,
            _username=username,
            _display_name=display_name,
            _role=role,
            _hashed_password=hashed_password,
            _created_at=datetime.now(),
            _is_active=True,
        )

    @classmethod
    def reconstitute(
        cls,
        id: int,
        username: str,
        display_name: str,
        role: UserRole,
        hashed_password: str,
        created_at: datetime,
        is_active: bool = True,
    ) -> User:
        return cls(
            _id=id,
            _username=username,
            _display_name=display_name,
            _role=role,
            _hashed_password=hashed_password,
            _created_at=created_at,
            _is_active=is_active,
        )

    def update_display_name(self, display_name: str) -> None:
        self._display_name = display_name

    def update_password(self, hashed_password: str) -> None:
        self._hashed_password = hashed_password

    def update_role(self, role: UserRole) -> None:
        self._role = role

    def activate(self) -> None:
        self._is_active = True

    def deactivate(self) -> None:
        self._is_active = False
