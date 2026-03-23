from __future__ import annotations

import asyncio
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
from infr.im.weixin.weixin_api import WeixinApiClient, DEFAULT_BASE_URL

logger = logging.getLogger(__name__)

WEIXIN_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.WEIXIN,
    display_name="WeChat",
    icon="weixin",
    required_plugin=None,
    binding_mode=BindingMode.QR_CODE,
    init_fields=(),
    init_mode="qr_login",
    description="WeChat via iLink QR login. Scan QR code with WeChat to connect.",
)


class WeixinAdapter(ImChannelAdapter):
    """WeChat IM channel adapter.

    Ported from Claude-to-IM-skill WeixinAdapter.
    Initialization: QR code login flow via iLink API.
    Binding mode: server-managed (backend long-polls for messages).

    Supports multiple concurrent channel instances, each with its own
    independent poll loop, callback, and offset cursor — keyed by
    ``channel_id``.  This allows several WeChat bindings to receive
    messages simultaneously without interfering with each other.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self._api = WeixinApiClient(base_url)
        # Per-channel poll state keyed by channel_id
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._on_messages: dict[str, Any] = {}
        self._stop_events: dict[str, asyncio.Event] = {}

    # ── Initialization ──

    async def check_init_status(self, config: dict) -> bool:
        bot_token = config.get("bot_token", "")
        if not bot_token:
            return False
        try:
            await self._api.get_config(bot_token, "", "")
            return True
        except Exception:
            return False

    async def initialize(self, params: dict) -> InitResult:
        step = params.get("step", "start")
        logger.info("[WeChat-adapter] initialize: step=%s params=%s", step, list(params.keys()))

        if step == "start":
            try:
                logger.info("[WeChat-adapter] Calling start_login_qr at %s", self._api._base_url)
                qr_data = await self._api.start_login_qr()
                logger.info("[WeChat-adapter] start_login_qr response keys: %s", list(qr_data.keys()))
                qrcode = qr_data.get("qrcode", "")
                qr_img = qr_data.get("qrcode_img_content", "")

                if not qrcode or not qr_img:
                    logger.warning(
                        "[WeChat-adapter] Missing QR data: qrcode=%s qr_img=%s (len=%d)",
                        bool(qrcode), bool(qr_img), len(qr_img) if qr_img else 0,
                    )
                    return InitResult(
                        status=ChannelInitStatus.ERROR,
                        error_message="Failed to get QR code from iLink API.",
                    )

                logger.info("[WeChat-adapter] QR code obtained: qrcode=%.50s qr_img_len=%d", qrcode, len(qr_img))
                return InitResult(
                    status=ChannelInitStatus.INITIALIZING,
                    ui_data={
                        # qrcode_img_content is a text/URL to be encoded as a QR code
                        # (NOT a base64 image).  Use verification_url so the frontend
                        # renders it via QRCode.toCanvas(), matching the Skill-side flow.
                        "verification_url": qr_img,
                        "qrcode": qrcode,
                        "step": "poll",
                        "login_status": "wait",
                    },
                )
            except Exception as e:
                logger.error("[WeChat-adapter] start_login_qr failed", exc_info=True)
                return InitResult(
                    status=ChannelInitStatus.ERROR,
                    error_message=f"Failed to start QR login: {e}",
                )

        elif step == "poll":
            qrcode = params.get("qrcode", "")
            logger.info("[WeChat-adapter] Polling QR status: qrcode=%.50s", qrcode)
            if not qrcode:
                return InitResult(
                    status=ChannelInitStatus.ERROR,
                    error_message="Missing qrcode parameter for polling.",
                )

            try:
                status_data = await self._api.poll_login_qr_status(qrcode)
                status = status_data.get("status", "")
                bot_token = status_data.get("bot_token", "")
                logger.info("[WeChat-adapter] Poll result: status=%s bot_token=%s", status, bool(bot_token))

                if status == "confirmed" and bot_token:
                    ilink_bot_id = status_data.get("ilink_bot_id", "")
                    base_url = status_data.get("baseurl", "") or self._api._base_url
                    logger.info("[WeChat-adapter] Login confirmed: ilink_bot_id=%s base_url=%s", ilink_bot_id, base_url)
                    return InitResult(
                        status=ChannelInitStatus.READY,
                        config={
                            "bot_token": bot_token,
                            "ilink_bot_id": ilink_bot_id,
                            "base_url": base_url,
                        },
                    )
                elif status in ("wait", "scaned"):
                    return InitResult(
                        status=ChannelInitStatus.INITIALIZING,
                        ui_data={
                            "login_status": status,
                            "qrcode": qrcode,
                            "step": "poll",
                        },
                    )
                elif status == "expired":
                    return InitResult(
                        status=ChannelInitStatus.ERROR,
                        error_message="QR code expired. Please try again.",
                    )
                else:
                    return InitResult(
                        status=ChannelInitStatus.ERROR,
                        error_message=f"QR login failed with status: {status}",
                    )
            except Exception as e:
                logger.error("[WeChat-adapter] poll_login_qr_status failed", exc_info=True)
                return InitResult(
                    status=ChannelInitStatus.ERROR,
                    error_message=f"QR login poll failed: {e}",
                )

        return InitResult(
            status=ChannelInitStatus.ERROR,
            error_message=f"Unknown init step: {step}",
        )

    # ── Binding lifecycle ──

    async def bind(
        self, session_id: str, binding: ImBinding, params: dict,
    ) -> BindResult:
        # Pass through init config (bot_token, base_url) so binding.config has them
        bot_token = params.get("bot_token", "")
        base_url = params.get("base_url", "")
        ilink_bot_id = params.get("ilink_bot_id", "")
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=f"weixin-session-{session_id}",
            config={
                "bot_token": bot_token,
                "base_url": base_url,
                "ilink_bot_id": ilink_bot_id,
            },
            ui_data={
                "mode": "direct",
                "display_name": "WeChat",
                "description": "Session is now listening for WeChat messages.",
            },
        )

    async def complete_bind(
        self, binding: ImBinding, params: dict,
    ) -> BindResult:
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=binding.channel_address or f"weixin-session-{binding.session_id}",
        )

    async def unbind(self, binding: ImBinding) -> None:
        await self.stop_listening(binding)

    # ── Message listening (server-managed long-poll) ──

    async def start_listening(self, binding: ImBinding, on_message=None) -> None:
        """Start long-polling for WeChat messages via iLink getupdates.

        Each channel_id gets its own independent poll loop.  If a poll
        loop already exists for the given channel_id it is stopped first
        before a new one is started.
        """
        channel_id = binding.channel_id

        # Stop existing poll loop for this specific channel if any
        existing_task = self._poll_tasks.get(channel_id)
        if existing_task and not existing_task.done():
            logger.info(
                "[WeChat-adapter] Stopping existing poll loop for channel=%s before restart",
                channel_id,
            )
            stop_evt = self._stop_events.get(channel_id)
            if stop_evt:
                stop_evt.set()
            existing_task.cancel()
            try:
                await existing_task
            except (asyncio.CancelledError, Exception):
                pass

        self._on_messages[channel_id] = on_message
        self._stop_events[channel_id] = asyncio.Event()
        logger.info(
            "[WeChat-adapter] Starting poll loop for session=%s channel=%s",
            binding.session_id, channel_id,
        )
        self._poll_tasks[channel_id] = asyncio.create_task(
            self._run_poll_loop(binding),
        )

    async def stop_listening(self, binding: ImBinding) -> None:
        """Stop the long-poll loop for a specific channel."""
        channel_id = binding.channel_id
        logger.info("[WeChat-adapter] Stopping poll loop for channel=%s", channel_id)

        stop_evt = self._stop_events.pop(channel_id, None)
        if stop_evt:
            stop_evt.set()

        task = self._poll_tasks.pop(channel_id, None)
        if task and not task.done():
            task.cancel()

        self._on_messages.pop(channel_id, None)

    async def _run_poll_loop(self, binding: ImBinding) -> None:
        """Long-poll iLink getupdates and dispatch messages for one channel."""
        channel_id = binding.channel_id
        bot_token = binding.config.get("bot_token", "")
        base_url = binding.config.get("base_url", "")
        if not bot_token:
            logger.error("[WeChat-adapter] No bot_token in binding config, cannot poll channel=%s", channel_id)
            return

        api = WeixinApiClient(base_url) if base_url else self._api
        cursor = ""

        logger.info(
            "[WeChat-adapter] Poll loop started: session=%s channel=%s base_url=%s",
            binding.session_id, channel_id, base_url or "(default)",
        )

        stop_event = self._stop_events.get(channel_id)
        while not (stop_event and stop_event.is_set()):
            try:
                data = await api.get_updates(bot_token, cursor)
                new_cursor = data.get("get_updates_buf", "")
                if new_cursor:
                    cursor = new_cursor

                msgs = data.get("msgs", [])
                for msg in msgs:
                    from_user_id = msg.get("from_user_id", "")
                    context_token = msg.get("context_token", "")
                    message_id = str(msg.get("message_id", msg.get("seq", "")))

                    # Persist context_token into binding config for outbound use
                    if from_user_id and context_token:
                        self._persist_context_token(binding, from_user_id, context_token)

                    # Extract text from item_list (type 1 = text)
                    text = ""
                    for item in msg.get("item_list", []):
                        if item.get("type") == 1:
                            text_item = item.get("text_item", {})
                            if isinstance(text_item, dict):
                                text += text_item.get("text", "")
                            else:
                                text += str(text_item)

                    if not text.strip() or not message_id:
                        continue

                    logger.info(
                        "[WeChat-adapter] Inbound message: channel=%s msg_id=%s from=%s text=%.100s",
                        channel_id, message_id, from_user_id, text.strip(),
                    )

                    on_message = self._on_messages.get(channel_id)
                    if on_message:
                        await on_message(
                            message_id, text.strip(), from_user_id, "",
                        )

            except asyncio.CancelledError:
                logger.info("[WeChat-adapter] Poll loop cancelled channel=%s", channel_id)
                break
            except Exception:
                logger.error("[WeChat-adapter] Poll error channel=%s, retrying in 3s", channel_id, exc_info=True)
                await asyncio.sleep(3)

        logger.info("[WeChat-adapter] Poll loop ended: session=%s channel=%s", binding.session_id, channel_id)

    @staticmethod
    def _persist_context_token(
        binding: ImBinding, from_user_id: str, context_token: str,
    ) -> None:
        """Write context_token into binding.config (in-memory).

        The application service's _persist_reply_context will flush routing
        context to DB on each inbound message.  We piggyback context_token
        onto the same config dict.
        """
        binding._config["last_context_token"] = context_token
        binding._config["last_sender_id"] = from_user_id

    # ── Send message ──

    async def send_message(
        self, binding: ImBinding, content: str,
        reply_context: dict | None = None,
    ) -> None:
        bot_token = binding.config.get("bot_token", "")
        if not bot_token:
            logger.warning("[WeChat-adapter] No bot_token for send_message")
            return

        ctx = reply_context or {}
        to_user_id = ctx.get("sender_id", "")
        context_token = ctx.get("context_token", "")

        if not to_user_id:
            logger.warning("[WeChat-adapter] No target user for send_message")
            return

        base_url = binding.config.get("base_url", "")
        api = WeixinApiClient(base_url) if base_url else self._api

        try:
            logger.info(
                "[WeChat-adapter] Sending message: to=%s content=%.100s",
                to_user_id, content,
            )
            await api.send_text_message(bot_token, to_user_id, content, context_token)
            logger.info("[WeChat-adapter] Message sent successfully")
        except Exception:
            logger.error("[WeChat-adapter] send_message failed", exc_info=True)

    async def close(self) -> None:
        """Shutdown adapter — stop all poll loops across all channels."""
        channel_ids = list(self._poll_tasks.keys())

        for cid in channel_ids:
            stop_evt = self._stop_events.pop(cid, None)
            if stop_evt:
                stop_evt.set()

            task = self._poll_tasks.pop(cid, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        self._on_messages.clear()
        self._stop_events.clear()
        self._poll_tasks.clear()
        logger.info("[WeChat-adapter] Adapter closed, %d channels stopped", len(channel_ids))

    # ── Routing context — WeChat needs context_token in addition to sender_id ──

    def extract_routing_context(
        self, sender_id: str, group_id: str,
    ) -> dict[str, str]:
        ctx = super().extract_routing_context(sender_id, group_id)
        # context_token is written to binding._config by _persist_context_token
        # during polling; it will be included when _persist_reply_context flushes.
        return ctx

    def build_reply_context(self, binding: ImBinding) -> dict[str, str] | None:
        ctx = super().build_reply_context(binding) or {}
        ct = binding.config.get("last_context_token", "")
        if ct:
            ctx["context_token"] = ct
        return ctx if ctx else None

    def routing_config_keys(self) -> tuple[str, ...]:
        return ("last_sender_id", "last_group_id", "last_context_token")

    # ── Reactions (typing indicator) ──

    async def add_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> None:
        bot_token = binding.config.get("bot_token", "")
        ilink_user_id = binding.config.get("ilink_user_id", "")
        if bot_token and ilink_user_id:
            await self._api.send_typing(bot_token, ilink_user_id, message_id, 1)

    async def remove_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> None:
        bot_token = binding.config.get("bot_token", "")
        ilink_user_id = binding.config.get("ilink_user_id", "")
        if bot_token and ilink_user_id:
            await self._api.send_typing(bot_token, ilink_user_id, message_id, 0)
