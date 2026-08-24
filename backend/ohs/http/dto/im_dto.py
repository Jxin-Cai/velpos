from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from domain.im_binding.model.im_binding import ImBinding


# ── Requests ──

class CreateChannelRequest(BaseModel):
    channel_type: str = Field(min_length=1, description="Channel type (e.g. qq, lark)")
    name: str = Field(default="", description="Instance display name")


class RenameChannelRequest(BaseModel):
    name: str = Field(min_length=1, description="New instance name")


class InitChannelRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict, description="Init params (credentials or QR step)")


class BindImRequest(BaseModel):
    session_id: str = Field(min_length=1, description="Session ID to bind IM")
    channel_id: str = Field(min_length=1, description="Channel instance ID")
    params: dict[str, Any] = Field(default_factory=dict, description="Channel-specific params")


class CompleteBindingRequest(BaseModel):
    session_id: str = Field(min_length=1, description="Session ID")
    channel_id: str = Field(min_length=1, description="Channel instance ID")
    friend_user_id: str = Field(default="", description="Friend user ID from IM (OpenIM)")
    params: dict[str, Any] = Field(default_factory=dict, description="Channel-specific params")


# ── Responses ──

class ChannelInstanceInfo(BaseModel):
    id: str
    name: str = ""
    app_id: str = ""
    init_status: str = "not_initialized"
    error_message: str = ""
    bound_session_id: str = ""


class ChannelInfo(BaseModel):
    channel_type: str
    display_name: str
    icon: str
    binding_mode: str
    init_mode: str = "credentials"
    init_fields: list[str] = []
    description: str = ""
    instances: list[ChannelInstanceInfo] = []


class InitChannelResponse(BaseModel):
    channel_id: str = ""
    channel_type: str = ""
    name: str = ""
    init_status: str = "not_initialized"
    error_message: str = ""
    init_mode: str = ""
    init_fields: list[str] = []
    description: str = ""
    ui_data: dict[str, Any] = {}


class BindImResponse(BaseModel):
    id: str = ""
    session_id: str
    channel_type: str = ""
    channel_id: str = ""
    im_user_id: str = ""
    binding_status: str
    qr_code_data: str | None = None
    friend_user_id: str | None = None
    channel_address: str = ""
    ui_data: dict[str, Any] = {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BindImResponse:
        return cls(**data)


class ImDeliveryItem(BaseModel):
    """一条未结清的投递条目 — 前端据此展示失败原因并发起重投."""

    id: int
    kind: str = Field(description="Queue direction: inbox | outbox")
    status: str
    content_preview: str = ""
    attempt_count: int = 0
    next_attempt_at: str = ""
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""


class ImDeliveryQueueStatus(BaseModel):
    counts: dict[str, int] = Field(default_factory=dict)
    unsettled: list[ImDeliveryItem] = Field(default_factory=list)


class ImDeliveryOverviewResponse(BaseModel):
    session_id: str
    inbox: ImDeliveryQueueStatus
    outbox: ImDeliveryQueueStatus


class RetryDeliveryResponse(BaseModel):
    requeued: bool = Field(
        description="Whether the delivery was actually put back on the queue",
    )


class ImStatusResponse(BaseModel):
    session_id: str
    channel_type: str = ""
    channel_id: str = ""
    im_user_id: str = ""
    binding_status: str
    qr_code_data: str | None = None
    friend_user_id: str | None = None
    channel_address: str = ""

    @classmethod
    def from_domain(cls, binding: ImBinding) -> ImStatusResponse:
        return cls(
            session_id=binding.session_id,
            channel_type=binding.channel_type.value,
            channel_id=binding.channel_id,
            im_user_id=binding.im_user_id,
            binding_status=binding.binding_status.value,
            qr_code_data=binding.qr_code_data or None,
            friend_user_id=binding.friend_user_id or None,
            channel_address=binding.channel_address,
        )
