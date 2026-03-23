from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_type import ImChannelType


@dataclass
class ImBinding:
    _id: str
    _session_id: str
    _channel_type: ImChannelType
    _channel_id: str
    _channel_address: str
    _config: dict
    _im_user_id: str
    _im_token: str
    _binding_status: BindingStatus
    _friend_user_id: str
    _qr_code_data: str
    _created_at: datetime

    @property
    def id(self) -> str:
        return self._id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def channel_type(self) -> ImChannelType:
        return self._channel_type

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def channel_address(self) -> str:
        return self._channel_address

    @property
    def config(self) -> dict:
        return self._config

    @property
    def im_user_id(self) -> str:
        return self._im_user_id

    @property
    def im_token(self) -> str:
        return self._im_token

    @property
    def binding_status(self) -> BindingStatus:
        return self._binding_status

    @property
    def friend_user_id(self) -> str:
        return self._friend_user_id

    @property
    def qr_code_data(self) -> str:
        return self._qr_code_data

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @classmethod
    def create(
        cls,
        session_id: str,
        channel_type: ImChannelType = ImChannelType.OPENIM,
        channel_id: str = "",
    ) -> ImBinding:
        if not session_id:
            raise ValueError("session_id must not be empty")
        binding_id = uuid.uuid4().hex[:8]
        im_user_id = (
            f"vp-session-{session_id}"
            if channel_type == ImChannelType.OPENIM
            else ""
        )
        return cls(
            _id=binding_id,
            _session_id=session_id,
            _channel_type=channel_type,
            _channel_id=channel_id,
            _channel_address="",
            _config={},
            _im_user_id=im_user_id,
            _im_token="",
            _binding_status=BindingStatus.UNBOUND,
            _friend_user_id="",
            _qr_code_data="",
            _created_at=datetime.now(),
        )

    @classmethod
    def reconstitute(
        cls,
        id: str,
        session_id: str,
        im_user_id: str,
        im_token: str,
        binding_status: BindingStatus,
        friend_user_id: str,
        qr_code_data: str,
        created_at: datetime,
        channel_type: ImChannelType = ImChannelType.OPENIM,
        channel_id: str = "",
        channel_address: str = "",
        config: dict | None = None,
    ) -> ImBinding:
        return cls(
            _id=id,
            _session_id=session_id,
            _channel_type=channel_type,
            _channel_id=channel_id,
            _channel_address=channel_address,
            _config=config or {},
            _im_user_id=im_user_id,
            _im_token=im_token,
            _binding_status=binding_status,
            _friend_user_id=friend_user_id,
            _qr_code_data=qr_code_data,
            _created_at=created_at,
        )

    def start_binding(self, im_token: str, qr_code_data: str) -> None:
        """Start the binding process.

        Sets im_token and qr_code_data, transitions status from UNBOUND to BINDING.
        Indicates the IM user has been registered and a QR code has been generated,
        waiting for the mobile client to scan.

        Raises ValueError if im_token is empty.
        Raises ValueError if current status is not UNBOUND.
        """
        if self._binding_status != BindingStatus.UNBOUND:
            raise ValueError("Binding already started or completed")
        if not im_token:
            raise ValueError("im_token must not be empty")
        self._im_token = im_token
        self._qr_code_data = qr_code_data
        self._binding_status = BindingStatus.BINDING

    def complete_binding(self, friend_user_id: str) -> None:
        """Complete the binding process.

        Sets friend_user_id, transitions status from BINDING to BOUND.
        Indicates the mobile client has scanned the QR code, the friend relationship
        has been imported, and the bidirectional channel is established.

        Raises ValueError if friend_user_id is empty.
        Raises ValueError if current status is not BINDING.
        """
        if self._binding_status != BindingStatus.BINDING:
            raise ValueError("Binding is not in progress")
        if not friend_user_id:
            raise ValueError("friend_user_id must not be empty")
        self._friend_user_id = friend_user_id
        self._binding_status = BindingStatus.BOUND

    def unbind(self) -> None:
        """Unbind the IM account.

        Clears im_token, friend_user_id, and qr_code_data.
        Resets status to UNBOUND.
        Supports unbinding from either BINDING or BOUND state.

        Raises ValueError if current status is UNBOUND.
        """
        if self._binding_status == BindingStatus.UNBOUND:
            raise ValueError("Cannot unbind: not currently bound or binding")
        self._im_token = ""
        self._friend_user_id = ""
        self._qr_code_data = ""
        self._channel_address = ""
        self._config = {}
        self._binding_status = BindingStatus.UNBOUND

    # --- Generic channel binding methods ---

    def set_channel_address(self, address: str) -> None:
        self._channel_address = address

    def update_config(self, updates: dict) -> None:
        self._config.update(updates)

    def complete_channel_binding(self, channel_address: str = "", config: dict | None = None) -> None:
        """Complete binding for any channel type (generic path)."""
        if channel_address:
            self._channel_address = channel_address
        if config:
            self._config.update(config)
        self._binding_status = BindingStatus.BOUND

    def start_binding_process(self) -> None:
        """Transition status to BINDING (generic channel flow).

        Unlike ``start_binding`` this does not require im_token/qr_code_data
        and can be called from any non-BOUND state.
        """
        self._binding_status = BindingStatus.BINDING
