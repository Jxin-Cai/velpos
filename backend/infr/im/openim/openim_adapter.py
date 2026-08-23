from __future__ import annotations

import logging

from domain.im_binding.acl.channel_errors import (
    ChannelPermanentError,
    ChannelRoutingError,
)
from domain.im_binding.acl.im_channel_adapter import (
    BindResult,
    ImChannelAdapter,
    InitResult,
)
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import OutboundMessage, SendReceipt
from domain.im_binding.acl.im_gateway import ImGateway
from domain.im_binding.acl.im_ws_gateway import ImWsGateway

logger = logging.getLogger(__name__)

#: OpenIM 通过 friend_user_id 定位收件人, 而不是 sender_id / group_id.
_FRIEND_USER_KEY = "friend_user_id"

OPENIM_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.OPENIM,
    display_name="OpenIM",
    icon="openim",
    required_plugin=None,
    binding_mode=BindingMode.QR_CODE,
    init_fields=("api_addr", "ws_addr", "admin_secret", "admin_user_id"),
    init_mode="credentials",
    description="OpenIM server for real-time messaging via WebSocket.",
    capabilities=frozenset({
        ChannelCapability.OUTBOUND_TEXT,
        ChannelCapability.PROGRESS_ACK,
    }),
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

    async def check_init_status(self, _config: dict) -> bool:
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
        self, session_id: str, binding: ImBinding, _params: dict,
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

    async def send(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> SendReceipt:
        friend_user_id = (
            message.route.extras.get(_FRIEND_USER_KEY) or binding.friend_user_id
        )
        if not friend_user_id:
            raise ChannelRoutingError(
                "Cannot send OpenIM message: binding has no friend user",
                channel_type=ImChannelType.OPENIM.value,
            )
        await self._im_gateway.send_message(
            binding.im_user_id, friend_user_id, message.plain_text,
        )
        # OpenIM 网关不回传消息标识, 所以 spec 未声明 MESSAGE_ID_ECHO.
        return SendReceipt.of("")

    # OpenIM 网关目前只能推送原始 WS 帧, 无法翻译成 InboundMessage,
    # 因此 spec 不声明 INBOUND_LISTEN, 也不实现监听原语。WS 连接的建立与
    # 断开由 complete_bind / unbind 负责。

    async def close(self) -> None:
        await self._im_ws_gateway.close_all()

    # ── Routing — OpenIM 用 friend_user_id 定位收件人 ──

    def route_extra_keys(self) -> tuple[str, ...]:
        return (_FRIEND_USER_KEY,)

    def restore_route(self, binding: ImBinding) -> ChannelRoute:
        fallback = (
            ChannelRoute(extras={_FRIEND_USER_KEY: binding.friend_user_id})
            if binding.friend_user_id
            else ChannelRoute()
        )
        return fallback.merge(super().restore_route(binding))


class OpenImStubAdapter(ImChannelAdapter):
    """Stub adapter when OpenIM infrastructure is not configured."""

    async def check_init_status(self, _config: dict) -> bool:
        return False

    async def initialize(self, _params: dict) -> InitResult:
        return InitResult(
            status=ChannelInitStatus.ERROR,
            error_message="OpenIM not configured. Set IM_API_ADDR, IM_WS_ADDR, IM_ADMIN_SECRET, IM_ADMIN_USER_ID env vars.",
        )

    async def bind(self, _session_id: str, _binding: ImBinding, _params: dict) -> BindResult:
        raise ValueError("OpenIM not configured")

    async def complete_bind(self, _binding: ImBinding, _params: dict) -> BindResult:
        raise ValueError("OpenIM not configured")

    async def unbind(self, _binding: ImBinding) -> None:
        pass

    async def send(
        self, _binding: ImBinding, _message: OutboundMessage,
    ) -> SendReceipt:
        raise ChannelPermanentError(
            "OpenIM infrastructure is not configured",
            channel_type=ImChannelType.OPENIM.value,
        )
