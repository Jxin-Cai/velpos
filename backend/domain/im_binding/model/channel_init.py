from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_type import ImChannelType


@dataclass
class ChannelInit:
    """渠道实例实体 — 跟踪单个 IM 渠道实例的初始化状态和凭证.

    同一 channel_type 可有多个实例, 各自持有独立的凭证和状态.
    """

    _id: str
    _channel_type: ImChannelType
    _name: str
    _init_status: ChannelInitStatus
    _config: dict
    _error_message: str
    _created_at: datetime
    _updated_at: datetime

    # ── Properties ──

    @property
    def id(self) -> str:
        return self._id

    @property
    def channel_type(self) -> ImChannelType:
        return self._channel_type

    @property
    def name(self) -> str:
        return self._name

    @property
    def init_status(self) -> ChannelInitStatus:
        return self._init_status

    @property
    def config(self) -> dict:
        return self._config

    @property
    def error_message(self) -> str:
        return self._error_message

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def is_ready(self) -> bool:
        return self._init_status == ChannelInitStatus.READY

    # ── Factories ──

    @classmethod
    def create(cls, channel_type: ImChannelType, name: str = "") -> ChannelInit:
        now = datetime.now()
        return cls(
            _id=uuid.uuid4().hex[:8],
            _channel_type=channel_type,
            _name=name or channel_type.value,
            _init_status=ChannelInitStatus.NOT_INITIALIZED,
            _config={},
            _error_message="",
            _created_at=now,
            _updated_at=now,
        )

    @classmethod
    def reconstitute(
        cls,
        id: str,
        channel_type: ImChannelType,
        init_status: ChannelInitStatus,
        config: dict,
        error_message: str,
        created_at: datetime,
        updated_at: datetime,
        name: str = "",
    ) -> ChannelInit:
        return cls(
            _id=id,
            _channel_type=channel_type,
            _name=name or channel_type.value,
            _init_status=init_status,
            _config=config,
            _error_message=error_message,
            _created_at=created_at,
            _updated_at=updated_at,
        )

    # ── Mutators ──

    def rename(self, name: str) -> None:
        self._name = name
        self._updated_at = datetime.now()

    # ── State transitions ──

    def start_init(self) -> None:
        if self._init_status not in (
            ChannelInitStatus.NOT_INITIALIZED,
            ChannelInitStatus.ERROR,
        ):
            raise ValueError(
                f"Cannot start init from status {self._init_status.value}"
            )
        self._init_status = ChannelInitStatus.INITIALIZING
        self._error_message = ""
        self._updated_at = datetime.now()

    def complete_init(self, config: dict) -> None:
        if self._init_status != ChannelInitStatus.INITIALIZING:
            raise ValueError("Can only complete init from INITIALIZING status")
        if not config:
            raise ValueError("Config must not be empty")
        self._config = config
        self._init_status = ChannelInitStatus.READY
        self._error_message = ""
        self._updated_at = datetime.now()

    def fail_init(self, error_message: str) -> None:
        if self._init_status != ChannelInitStatus.INITIALIZING:
            raise ValueError("Can only fail init from INITIALIZING status")
        self._init_status = ChannelInitStatus.ERROR
        self._error_message = error_message
        self._updated_at = datetime.now()

    def reset(self) -> None:
        self._init_status = ChannelInitStatus.NOT_INITIALIZED
        self._config = {}
        self._error_message = ""
        self._updated_at = datetime.now()

    def update_config(self, updates: dict) -> None:
        """Merge additional key-value pairs into channel config."""
        self._config.update(updates)
        self._updated_at = datetime.now()
