from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from domain.shared.async_utils import safe_create_task
from domain.im_binding.acl.channel_errors import (
    ChannelAuthError,
    ChannelRoutingError,
)
from domain.im_binding.acl.im_channel_adapter import (
    BindResult,
    ImChannelAdapter,
    InboundHandler,
    InitResult,
)
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    InboundMessage,
    MessageSegment,
    OutboundMessage,
    SendReceipt,
)
from infr.im.weixin.weixin_api import WeixinApiClient, DEFAULT_BASE_URL

logger = logging.getLogger(__name__)

_TYPING_TICKET_TTL_SECONDS = 600
_TYPING_KEEPALIVE_SECONDS = 5
_MAX_TEXT_CHUNK_LENGTH = 3800
_TEXT_CHUNK_SEND_DELAY_SECONDS = 0.1
_CONTEXT_TOKEN_KEY = "context_token"
_POLL_BACKOFF_SECONDS = 3
_MAX_POLL_BACKOFF_SECONDS = 60
_AUTH_RETRY_BACKOFF_SECONDS = 300
_AUTH_RECOVERY_RETRY_SECONDS = 5


class _TypingStatus(IntEnum):
    TYPING = 1
    CANCEL = 2


@dataclass(frozen=True)
class _TypingSession:
    task: asyncio.Task[None]
    api: WeixinApiClient
    bot_token: str
    user_id: str
    ticket: str


WEIXIN_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.WEIXIN,
    display_name="WeChat",
    icon="weixin",
    required_plugin=None,
    binding_mode=BindingMode.QR_CODE,
    init_fields=(),
    init_mode="qr_login",
    description="WeChat via iLink QR login. Scan QR code with WeChat to connect.",
    capabilities=frozenset({
        ChannelCapability.INBOUND_LISTEN,
        ChannelCapability.OUTBOUND_TEXT,
        ChannelCapability.TYPING_INDICATOR,
        # iLink 无表情回应也无线程回复, 只能用文本回报任务进度.
        ChannelCapability.PROGRESS_ACK,
        ChannelCapability.IDEMPOTENCY,
        ChannelCapability.MESSAGE_ID_ECHO,
    }),
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
        self._listen_lock = asyncio.Lock()
        self._typing_lock = asyncio.Lock()
        self._typing_tickets: dict[str, tuple[str, float]] = {}
        self._typing_sessions: dict[str, _TypingSession] = {}

    # ── Initialization ──

    async def check_init_status(self, config: dict) -> bool:
        bot_token = config.get("bot_token", "")
        if not bot_token:
            return False
        try:
            await self._api.get_config(bot_token, "", "")
            return True
        except Exception:
            logger.warning(
                "[WeChat-adapter] Stored credentials failed validation",
                exc_info=True,
            )
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
        self, binding: ImBinding, _params: dict,
    ) -> BindResult:
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=binding.channel_address or f"weixin-session-{binding.session_id}",
        )

    async def unbind(self, binding: ImBinding) -> None:
        await self.stop_listening(binding)

    # ── Message listening (server-managed long-poll) ──

    async def start_listening(
        self, binding: ImBinding, on_message: InboundHandler | None = None,
    ) -> None:
        """Start long-polling for WeChat messages via iLink getupdates.

        Each channel_id gets its own independent poll loop.  If a poll
        loop already exists for the given channel_id it is stopped first
        before a new one is started.
        """
        channel_id = binding.channel_id

        async with self._listen_lock:
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
            self._poll_tasks[channel_id] = safe_create_task(
                self._run_poll_loop(binding),
            )

    async def stop_listening(self, binding: ImBinding) -> None:
        """Stop the long-poll loop for a specific channel."""
        channel_id = binding.channel_id
        logger.info("[WeChat-adapter] Stopping poll loop for channel=%s", channel_id)

        async with self._listen_lock:
            stop_evt = self._stop_events.pop(channel_id, None)
            if stop_evt:
                stop_evt.set()

            task = self._poll_tasks.pop(channel_id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            self._on_messages.pop(channel_id, None)

        # 通知 iLink 服务端该账号下线 (对齐官方插件 stopAccount 行为);
        # 失败不影响停止流程.
        bot_token = binding.config.get("bot_token", "")
        base_url = binding.config.get("base_url", "")
        if bot_token:
            api = WeixinApiClient(base_url) if base_url else self._api
            try:
                await api.notify_stop(bot_token)
            except Exception:
                logger.warning(
                    "[WeChat-adapter] notifystop failed channel=%s",
                    channel_id,
                    exc_info=True,
                )

    @staticmethod
    async def _notify_session_start(
        api: WeixinApiClient, bot_token: str, channel_id: str,
    ) -> bool:
        """上报客户端上线, 让 iLink 重建/续活服务端会话. 返回是否成功."""
        try:
            await api.notify_start(bot_token)
            logger.info(
                "[WeChat-adapter] notifystart ok channel=%s", channel_id,
            )
            return True
        except Exception:
            logger.warning(
                "[WeChat-adapter] notifystart failed channel=%s",
                channel_id,
                exc_info=True,
            )
            return False

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

        # 官方 openclaw-weixin 插件在每次渠道启动时先 notifystart, 让
        # iLink 服务端同步在线状态; 长时间不上报会被判为 stale session.
        await self._notify_session_start(api, bot_token, channel_id)

        logger.info(
            "[WeChat-adapter] Poll loop started: session=%s channel=%s base_url=%s",
            binding.session_id, channel_id, base_url or "(default)",
        )

        stop_event = self._stop_events.get(channel_id)
        failures = 0
        while not (stop_event and stop_event.is_set()):
            try:
                data = await api.get_updates(bot_token, cursor)
                new_cursor = data.get("get_updates_buf", "")

                for msg in data.get("msgs", []):
                    from_user_id = msg.get("from_user_id", "")
                    context_token = msg.get("context_token", "")
                    message_id = str(msg.get("message_id", msg.get("seq", "")))
                    text = _extract_text(msg)

                    if not text or not message_id:
                        continue

                    logger.info(
                        "[WeChat-adapter] Inbound message: channel=%s msg_id=%s from=%s text=%.100s",
                        channel_id, message_id, from_user_id, text,
                    )

                    on_message = self._on_messages.get(channel_id)
                    if on_message:
                        # context_token 是回复的必要条件, 随消息一起交出去,
                        # 由编排层持久化到 inbox 事件, 重启后仍然能回复.
                        await on_message(
                            InboundMessage(
                                channel_id=channel_id or binding.id,
                                channel_type=ImChannelType.WEIXIN.value,
                                external_message_id=message_id,
                                route=ChannelRoute(
                                    sender_id=from_user_id,
                                    extras=(
                                        {_CONTEXT_TOKEN_KEY: context_token}
                                        if context_token
                                        else {}
                                    ),
                                ),
                                segments=(MessageSegment.of_text(text),),
                            )
                        )
                if new_cursor:
                    cursor = new_cursor

                failures = 0

            except asyncio.CancelledError:
                logger.info("[WeChat-adapter] Poll loop cancelled channel=%s", channel_id)
                break
            except ChannelAuthError:
                # iLink 长时间闲置后把会话判为 stale (-14/401), 直接退出会让
                # 渠道永久静默. 先用 notifystart 重建服务端会话 (无需重新
                # 扫码), 成功则快速恢复轮询; 失败再长退避, 日志持续提示用户
                # 重新扫码 — 重新绑定会重启本循环.
                recovered = await self._notify_session_start(
                    api, bot_token, channel_id,
                )
                delay = (
                    _AUTH_RECOVERY_RETRY_SECONDS
                    if recovered
                    else _AUTH_RETRY_BACKOFF_SECONDS
                )
                logger.error(
                    "[WeChat-adapter] Poll credentials rejected, "
                    "session rebuild %s, retrying in %ds: channel=%s "
                    "(若持续出现, 请重新扫码绑定微信)",
                    "succeeded" if recovered else "failed",
                    delay,
                    channel_id,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
            except Exception:
                failures += 1
                delay = min(
                    _MAX_POLL_BACKOFF_SECONDS, _POLL_BACKOFF_SECONDS * 2 ** (failures - 1),
                )
                logger.error(
                    "[WeChat-adapter] Poll error channel=%s failures=%d, retrying in %ds",
                    channel_id, failures, delay, exc_info=True,
                )
                await asyncio.sleep(delay)

        logger.info("[WeChat-adapter] Poll loop ended: session=%s channel=%s", binding.session_id, channel_id)

    # ── Send message ──

    async def send(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> SendReceipt:
        bot_token = binding.config.get("bot_token", "")
        if not bot_token:
            raise ChannelRoutingError(
                "WeChat bot token is unavailable",
                channel_type=ImChannelType.WEIXIN.value,
            )

        to_user_id = message.route.sender_id
        if not to_user_id:
            raise ChannelRoutingError(
                "Cannot send WeChat message: no recipient in routing context. "
                "Send one message from WeChat first to establish routing.",
                channel_type=ImChannelType.WEIXIN.value,
            )

        api = self._api_for_binding(binding)
        content = message.plain_text
        chunks = self._split_text(content)
        logger.info(
            "[WeChat-adapter] Sending message: to=%s length=%d chunks=%d",
            to_user_id,
            len(content),
            len(chunks),
        )

        external_message_id = ""
        for index, chunk in enumerate(chunks):
            if index > 0:
                await asyncio.sleep(_TEXT_CHUNK_SEND_DELAY_SECONDS)
            chunk_key = idempotency_key = message.idempotency_key
            if idempotency_key and len(chunks) > 1:
                chunk_key = f"{idempotency_key}:chunk:{index + 1}:{len(chunks)}"
            external_message_id = await api.send_text_message(
                bot_token,
                to_user_id,
                chunk,
                message.route.extras.get(_CONTEXT_TOKEN_KEY, ""),
                idempotency_key=chunk_key,
            )
        logger.info(
            "[WeChat-adapter] Message delivered: chunks=%d last_message_id=%s",
            len(chunks),
            external_message_id,
        )
        return SendReceipt.of(external_message_id)

    @staticmethod
    def _split_text(content: str) -> list[str]:
        remaining = content
        if len(remaining) <= _MAX_TEXT_CHUNK_LENGTH:
            return [remaining]

        chunks: list[str] = []
        while len(remaining) > _MAX_TEXT_CHUNK_LENGTH:
            boundary = _MAX_TEXT_CHUNK_LENGTH
            for separator in ("\n\n", "\n", "。", " "):
                candidate = remaining.rfind(
                    separator,
                    _MAX_TEXT_CHUNK_LENGTH // 2,
                    _MAX_TEXT_CHUNK_LENGTH + 1,
                )
                if candidate >= 0:
                    boundary = candidate + len(separator)
                    break
            chunks.append(remaining[:boundary])
            remaining = remaining[boundary:]
        if remaining:
            chunks.append(remaining)
        return chunks

    async def close(self) -> None:
        """Shutdown adapter — stop all poll loops across all channels."""
        async with self._listen_lock:
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
        await self._stop_all_typing_sessions()
        logger.info("[WeChat-adapter] Adapter closed, %d channels stopped", len(channel_ids))

    # ── Routing — WeChat 回复必须带 context_token ──

    def route_extra_keys(self) -> tuple[str, ...]:
        return (_CONTEXT_TOKEN_KEY,)

    # ── Typing indicator ──

    async def start_typing(self, binding: ImBinding, route: ChannelRoute) -> str:
        bot_token = binding.config.get("bot_token", "")
        user_id = route.sender_id or self.restore_route(binding).sender_id
        if not bot_token or not user_id:
            return ""

        api = self._api_for_binding(binding)
        context_token = route.extras.get(
            _CONTEXT_TOKEN_KEY,
        ) or self.restore_route(binding).extras.get(_CONTEXT_TOKEN_KEY, "")
        ticket = await self._get_typing_ticket(
            api, binding, user_id, context_token,
        )
        if not ticket:
            return ""

        session_key = f"{binding.channel_id or binding.id}:{user_id}"
        await api.send_typing(bot_token, user_id, ticket, _TypingStatus.TYPING)
        keepalive = safe_create_task(
            self._run_typing_keepalive(api, bot_token, user_id, ticket),
            name=f"weixin-typing-{binding.channel_id or binding.id}",
        )
        async with self._typing_lock:
            previous = self._typing_sessions.pop(session_key, None)
            self._typing_sessions[session_key] = _TypingSession(
                task=keepalive,
                api=api,
                bot_token=bot_token,
                user_id=user_id,
                ticket=ticket,
            )
        if previous is not None:
            previous.task.cancel()
            await asyncio.gather(previous.task, return_exceptions=True)
        return session_key

    async def stop_typing(self, binding: ImBinding, ticket: str) -> None:
        async with self._typing_lock:
            session = self._typing_sessions.pop(ticket, None)
        if session is None:
            return

        session.task.cancel()
        await asyncio.gather(session.task, return_exceptions=True)
        await session.api.send_typing(
            session.bot_token,
            session.user_id,
            session.ticket,
            _TypingStatus.CANCEL,
        )

    def _api_for_binding(self, binding: ImBinding) -> WeixinApiClient:
        base_url = binding.config.get("base_url", "")
        return WeixinApiClient(base_url) if base_url else self._api

    async def _get_typing_ticket(
        self,
        api: WeixinApiClient,
        binding: ImBinding,
        user_id: str,
        context_token: str,
    ) -> str:
        now = time.monotonic()
        cache_key = f"{binding.channel_id or binding.id}:{user_id}"
        async with self._typing_lock:
            cached = self._typing_tickets.get(cache_key)
            if cached is not None and cached[1] > now:
                return cached[0]

            response = await api.get_config(
                binding.config.get("bot_token", ""),
                user_id,
                context_token,
            )
            ticket = str(response.get("typing_ticket") or "").strip()
            if not ticket:
                logger.warning(
                    "[WeChat-adapter] getconfig returned no typing ticket: channel=%s user=%s",
                    binding.channel_id or binding.id,
                    user_id,
                )
                return ""
            self._typing_tickets[cache_key] = (
                ticket,
                now + _TYPING_TICKET_TTL_SECONDS,
            )
            return ticket

    @staticmethod
    async def _run_typing_keepalive(
        api: WeixinApiClient,
        bot_token: str,
        user_id: str,
        ticket: str,
    ) -> None:
        while True:
            await asyncio.sleep(_TYPING_KEEPALIVE_SECONDS)
            await api.send_typing(
                bot_token,
                user_id,
                ticket,
                _TypingStatus.TYPING,
            )

    async def _stop_all_typing_sessions(self) -> None:
        async with self._typing_lock:
            sessions = list(self._typing_sessions.values())
            self._typing_sessions.clear()
        for session in sessions:
            session.task.cancel()
        if sessions:
            await asyncio.gather(
                *(session.task for session in sessions),
                return_exceptions=True,
            )


def _extract_text(msg: dict[str, Any]) -> str:
    """Concatenate the text items (``type == 1``) of an iLink message."""
    parts: list[str] = []
    for item in msg.get("item_list", []):
        if item.get("type") != 1:
            continue
        text_item = item.get("text_item", {})
        parts.append(
            text_item.get("text", "")
            if isinstance(text_item, dict)
            else str(text_item)
        )
    return "".join(parts).strip()
