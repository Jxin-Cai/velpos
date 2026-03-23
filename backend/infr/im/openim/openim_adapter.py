from __future__ import annotations

import logging

from domain.im_binding.acl.im_channel_adapter import (
    BindResult,
    ImChannelAdapter,
    InitResult,
)
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.acl.im_gateway import ImGateway
from domain.im_binding.acl.im_ws_gateway import ImWsGateway

logger = logging.getLogger(__name__)

OPENIM_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.OPENIM,
    display_name="OpenIM",
    icon="openim",
    required_plugin=None,
    binding_mode=BindingMode.QR_CODE,
    init_fields=("api_addr", "ws_addr", "admin_secret", "admin_user_id"),
    init_mode="credentials",
    description="OpenIM server for real-time messaging via WebSocket.",
)


class OpenImAdapter(ImChannelAdapter):
    """OpenIM 渠道适配器 — 封装现有 ImGateway / ImWsGateway."""

    def __init__(
        self,
        im_gateway: ImGateway,
        im_ws_gateway: ImWsGateway,
    ) -> None:
        self._im_gateway = im_gateway
        self._im_ws_gateway = im_ws_gateway

    # ── Initialization ──

    async def check_init_status(self, config: dict) -> bool:
        try:
            return self._im_gateway is not None
        except Exception:
            return False

    async def initialize(self, params: dict) -> InitResult:
        # OpenIM uses env-based config; if gateway exists, it's ready
        if self._im_gateway is not None:
            return InitResult(
                status=ChannelInitStatus.READY,
                config=params,
            )
        return InitResult(
            status=ChannelInitStatus.ERROR,
            error_message="OpenIM gateway not configured. Set IM_API_ADDR, IM_WS_ADDR, IM_ADMIN_SECRET, IM_ADMIN_USER_ID env vars.",
        )

    # ── Binding lifecycle ──

    async def bind(
        self, session_id: str, binding: ImBinding, params: dict,
    ) -> BindResult:
        im_user_id = binding.im_user_id or f"vp-session-{session_id}"

        await self._im_gateway.register_user(
            im_user_id, f"Session {session_id}",
        )
        im_token = await self._im_gateway.get_user_token(im_user_id)
        qr_code_data = await self._im_gateway.generate_add_friend_link(im_user_id)

        binding.start_binding(im_token, qr_code_data)

        return BindResult(
            status=BindingStatus.BINDING,
            ui_data={
                "mode": "qr_code",
                "qr_code_data": qr_code_data,
                "im_user_id": im_user_id,
            },
        )

    async def complete_bind(
        self, binding: ImBinding, params: dict,
    ) -> BindResult:
        friend_user_id = params.get("friend_user_id", "")
        if not friend_user_id:
            raise ValueError("friend_user_id is required")

        binding.complete_binding(friend_user_id)
        await self._im_gateway.import_friend(binding.im_user_id, friend_user_id)

        try:
            await self._im_ws_gateway.connect(binding.im_user_id, binding.im_token)
        except Exception:
            logger.warning(
                "Failed to establish WS connection for %s", binding.im_user_id,
            )

        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=friend_user_id,
            ui_data={
                "mode": "qr_code",
                "im_user_id": binding.im_user_id,
                "friend_user_id": friend_user_id,
            },
        )

    async def unbind(self, binding: ImBinding) -> None:
        try:
            await self._im_ws_gateway.disconnect(binding.im_user_id)
        except Exception:
            logger.warning(
                "Failed to disconnect WS for %s", binding.im_user_id,
            )

    async def send_message(self, binding: ImBinding, content: str, reply_context: dict | None = None) -> None:
        await self._im_gateway.send_message(
            binding.im_user_id, binding.friend_user_id, content,
        )

    # ── Message lifecycle ──

    async def start_listening(self, binding: ImBinding, on_message=None) -> None:
        try:
            if not await self._im_ws_gateway.is_connected(binding.im_user_id):
                await self._im_ws_gateway.connect(binding.im_user_id, binding.im_token)
        except Exception:
            logger.warning("start_listening failed for %s", binding.im_user_id)

    async def stop_listening(self, binding: ImBinding) -> None:
        try:
            await self._im_ws_gateway.disconnect(binding.im_user_id)
        except Exception:
            logger.warning("stop_listening failed for %s", binding.im_user_id)

    # ── Routing context — OpenIM uses friend_user_id, not sender/group ──

    def extract_routing_context(self, sender_id: str, group_id: str) -> dict[str, str]:
        return {}

    def build_reply_context(self, binding: ImBinding) -> dict[str, str] | None:
        return {"friend_user_id": binding.friend_user_id} if binding.friend_user_id else None

    def routing_config_keys(self) -> tuple[str, ...]:
        return ()


class OpenImStubAdapter(ImChannelAdapter):
    """Stub adapter when OpenIM infrastructure is not configured."""

    async def check_init_status(self, config: dict) -> bool:
        return False

    async def initialize(self, params: dict) -> InitResult:
        return InitResult(
            status=ChannelInitStatus.ERROR,
            error_message="OpenIM not configured. Set IM_API_ADDR, IM_WS_ADDR, IM_ADMIN_SECRET, IM_ADMIN_USER_ID env vars.",
        )

    async def bind(self, session_id: str, binding: ImBinding, params: dict) -> BindResult:
        raise ValueError("OpenIM not configured")

    async def complete_bind(self, binding: ImBinding, params: dict) -> BindResult:
        raise ValueError("OpenIM not configured")

    async def unbind(self, binding: ImBinding) -> None:
        pass

    async def send_message(self, binding: ImBinding, content: str, reply_context: dict | None = None) -> None:
        pass
