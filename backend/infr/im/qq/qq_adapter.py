from __future__ import annotations

import logging
from typing import Any

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
from infr.im.qq.qq_api import QqApiClient
from infr.im.qq.qq_ws_client import QqWsClient

logger = logging.getLogger(__name__)

QQ_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.QQ,
    display_name="QQ",
    icon="qq",
    required_plugin=None,
    binding_mode=BindingMode.QR_CODE,  # server-managed
    init_fields=("app_id", "app_secret"),
    init_mode="credentials",
    description="QQ bot via WebSocket gateway. Requires QQ Open Platform app credentials.",
)


class QqAdapter(ImChannelAdapter):
    """QQ IM channel adapter — server-managed binding.

    Supports multiple concurrent channel instances, each with its own
    WebSocket connection managed by the shared ``QqWsClient``.

    Initialization: validate credentials via QQ token API.
    Binding: starts a background WebSocket listener per channel.
    """

    def __init__(
        self,
        ws_client: QqWsClient,
        api_client: QqApiClient,
    ) -> None:
        self._ws = ws_client
        self._api = api_client

    # ── Initialization ──

    async def check_init_status(self, config: dict) -> bool:
        app_id = config.get("app_id", "")
        app_secret = config.get("app_secret", "")
        if not app_id or not app_secret:
            return False
        try:
            await self._api.ensure_token(app_id, app_secret)
            return True
        except Exception:
            return False

    async def initialize(self, params: dict) -> InitResult:
        app_id = params.get("app_id", "").strip()
        app_secret = params.get("app_secret", "").strip()

        if not app_id or not app_secret:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message="app_id and app_secret are required.",
            )

        try:
            self._api.set_credentials(app_id, app_secret)
            await self._api.ensure_token()
        except Exception as e:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message=f"QQ credential validation failed: {e}",
            )

        # Verify gateway connectivity
        try:
            gw_url = await self._api.get_gateway_url()
        except Exception as e:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message=f"QQ gateway check failed: {e}",
            )

        if not gw_url:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message="QQ gateway returned no URL. Credentials may lack bot permissions.",
            )

        logger.info("QQ credentials validated: gateway=%s", gw_url)
        return InitResult(
            status=ChannelInitStatus.READY,
            config={"app_id": app_id, "app_secret": app_secret},
        )

    # ── Binding lifecycle ──

    async def bind(
        self, session_id: str, binding: ImBinding, params: dict,
    ) -> BindResult:
        app_id = params.get("app_id", "")
        app_secret = params.get("app_secret", "")
        logger.info("[QQ-adapter] bind: session=%s app_id=%s", session_id, app_id)
        if app_id and app_secret:
            self._api.set_credentials(app_id, app_secret)

        return BindResult(
            status=BindingStatus.BOUND,
            channel_address="qq-bot",
            config={"app_id": app_id, "app_secret": app_secret},
        )

    async def start_listening(
        self, binding: ImBinding, on_message: Any,
    ) -> None:
        """Start the QQ WebSocket listener for this specific channel."""
        channel_id = binding.channel_id
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")

        logger.info(
            "[QQ-adapter] start_listening: channel=%s session=%s running=%s",
            channel_id, binding.session_id,
            self._ws.is_channel_running(channel_id),
        )

        if not app_id or not app_secret:
            logger.warning("[QQ-adapter] No credentials in binding config for channel=%s!", channel_id)
            return

        # start() internally stops any existing connection for this channel
        await self._ws.start(
            channel_id=channel_id,
            session_id=binding.session_id,
            on_message=on_message,
            app_id=app_id,
            app_secret=app_secret,
        )
        logger.info("[QQ-adapter] WS client started for channel=%s", channel_id)

    async def stop_listening(self, binding: ImBinding) -> None:
        """Stop the QQ WebSocket listener for a specific channel."""
        channel_id = binding.channel_id
        logger.info("[QQ-adapter] stop_listening: channel=%s", channel_id)
        await self._ws.stop(channel_id)

    async def complete_bind(
        self, binding: ImBinding, params: dict,
    ) -> BindResult:
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=binding.channel_address or "qq-bot",
        )

    async def unbind(self, binding: ImBinding) -> None:
        channel_id = binding.channel_id
        logger.info("[QQ-adapter] unbind: channel=%s", channel_id)
        await self._ws.stop(channel_id)

    async def send_message(
        self, binding: ImBinding, content: str,
        reply_context: dict | None = None,
    ) -> None:
        ctx = reply_context or {}
        msg_id = ctx.get("msg_id", "")
        group_id = ctx.get("group_id", "")
        sender_id = ctx.get("sender_id", "")

        # Use per-binding credentials for sending
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")

        logger.info(
            "[QQ-adapter] send_message: session=%s msg_id=%s sender=%s group=%s content=%.100s",
            binding.session_id if hasattr(binding, 'session_id') else '?',
            msg_id, sender_id, group_id, content,
        )

        try:
            if group_id:
                logger.info("[QQ-adapter] Sending group message to %s", group_id)
                await self._api.send_group_message(
                    group_id, content, msg_id,
                    app_id=app_id or None, app_secret=app_secret or None,
                )
            elif sender_id:
                logger.info("[QQ-adapter] Sending C2C message to %s", sender_id)
                await self._api.send_c2c_message(
                    sender_id, content, msg_id,
                    app_id=app_id or None, app_secret=app_secret or None,
                )
            else:
                raise RuntimeError(
                    "Cannot send QQ message: no group_id or sender_id in reply_context. "
                    "Please send at least one message from QQ first to establish routing."
                )
        except Exception:
            logger.error(
                "[QQ-adapter] send_message failed",
                exc_info=True,
            )
            raise
