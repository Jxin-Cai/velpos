from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChannelProfile:
    _profile_id: str
    _name: str
    _host: str
    _api_key: str
    _auth_env_name: str
    _model_config: dict[str, str]
    _is_active: bool
    _created_time: datetime
    _updated_time: datetime

    @property
    def profile_id(self) -> str:
        return self._profile_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def host(self) -> str:
        return self._host

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def auth_env_name(self) -> str:
        return self._auth_env_name

    @property
    def model_config(self) -> dict[str, str]:
        return dict(self._model_config)

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def created_time(self) -> datetime:
        return self._created_time

    @property
    def updated_time(self) -> datetime:
        return self._updated_time

    @classmethod
    def create(
        cls,
        name: str,
        host: str,
        api_key: str,
        model_config: dict[str, str],
        auth_env_name: str = "ANTHROPIC_API_KEY",
    ) -> ChannelProfile:
        """Create a new ChannelProfile.

        Generates an 8-character UUID hex prefix as profile_id.
        Initial is_active is False.
        created_time and updated_time are set to the current time.

        Raises ValueError if name is empty.
        """
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        now = datetime.now()
        return cls(
            _profile_id=uuid.uuid4().hex[:8],
            _name=name,
            _host=host or "",
            _api_key=api_key or "",
            _auth_env_name=auth_env_name or "ANTHROPIC_API_KEY",
            _model_config=dict(model_config) if model_config else {},
            _is_active=False,
            _created_time=now,
            _updated_time=now,
        )

    @classmethod
    def reconstitute(
        cls,
        profile_id: str,
        name: str,
        host: str,
        api_key: str,
        auth_env_name: str,
        model_config: dict[str, str],
        is_active: bool,
        created_time: datetime,
        updated_time: datetime,
    ) -> ChannelProfile:
        """Reconstitute a ChannelProfile from persisted data.

        Does not perform business validation; directly restores aggregate state.
        Called by Repository implementations when loading from the database.
        """
        return cls(
            _profile_id=profile_id,
            _name=name,
            _host=host,
            _api_key=api_key,
            _auth_env_name=auth_env_name or "ANTHROPIC_API_KEY",
            _model_config=dict(model_config),
            _is_active=is_active,
            _created_time=created_time,
            _updated_time=updated_time,
        )

    def activate(self) -> None:
        """Set is_active to True and update updated_time.

        Idempotent: does not raise if already active.
        """
        self._is_active = True
        self._updated_time = datetime.now()

    def deactivate(self) -> None:
        """Set is_active to False and update updated_time.

        Idempotent: does not raise if already inactive.
        """
        self._is_active = False
        self._updated_time = datetime.now()

    def update_config(
        self,
        name: str,
        host: str,
        api_key: str,
        auth_env_name: str,
        model_config: dict[str, str],
    ) -> None:
        """Update all mutable configuration fields.

        Updates name, host, api_key, auth_env_name, and model_config.
        Sets updated_time to the current time.

        Raises ValueError if name is empty.
        """
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        self._name = name
        self._host = host
        self._api_key = api_key
        self._auth_env_name = auth_env_name or "ANTHROPIC_API_KEY"
        self._model_config = dict(model_config) if model_config else {}
        self._updated_time = datetime.now()
