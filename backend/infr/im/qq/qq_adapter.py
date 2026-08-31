from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from typing import Any

import httpx

from domain.im_binding.acl.channel_errors import ChannelRoutingError
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
from infr.im.inbound_voice import (
    VOICE_PLACEHOLDER_TEXT,
    InboundVoice,
    InboundVoiceStore,
    VoiceCodec,
)
from infr.im.qq.qq_api import QqApiClient
from infr.im.qq.qq_ws_client import QqInboundEvent, QqWsClient

logger = logging.getLogger(__name__)

#: QQ 附件的 ``content_type`` 取值 — 语音消息是唯一的非 MIME 形式取值.
_VOICE_CONTENT_TYPE = "voice"

QQ_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.QQ,
    display_name="QQ",
    icon="qq",
    required_plugin=None,
    binding_mode=BindingMode.QR_CODE,  # server-managed
    init_fields=("app_id", "app_secret"),
    init_mode="credentials",
    description="QQ bot via WebSocket gateway. Requires QQ Open Platform app credentials.",
    capabilities=frozenset({
        ChannelCapability.INBOUND_LISTEN,
        ChannelCapability.OUTBOUND_TEXT,
        # 语音消息随附件下发, 下载落盘后进入会话工作区.
        ChannelCapability.INBOUND_ATTACHMENT,
        ChannelCapability.THREAD_REPLY,
        ChannelCapability.GROUP_CHAT,
        # msg_seq 让同一 idempotency_key 的重发被 QQ 侧去重.
        ChannelCapability.IDEMPOTENCY,
        ChannelCapability.MESSAGE_ID_ECHO,
        ChannelCapability.PROGRESS_ACK,
    }),
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
        voice_store: InboundVoiceStore | None = None,
    ) -> None:
        self._ws = ws_client
        self._api = api_client
        self._voice_store = voice_store or InboundVoiceStore()

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
            await self._api.ensure_token(app_id, app_secret)
        except Exception as e:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message=f"QQ credential validation failed: {e}",
            )

        # Verify gateway connectivity
        try:
            gw_url = await self._api.get_gateway_url(app_id, app_secret)
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
        self, session_id: str, _binding: ImBinding, params: dict,
    ) -> BindResult:
        app_id = params.get("app_id", "")
        app_secret = params.get("app_secret", "")
        logger.info("[QQ-adapter] bind: session=%s app_id=%s", session_id, app_id)

        return BindResult(
            status=BindingStatus.BOUND,
            channel_address="qq-bot",
            config={"app_id": app_id, "app_secret": app_secret},
        )

    async def start_listening(
        self, binding: ImBinding, on_message: InboundHandler | None = None,
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

        async def dispatch(event: QqInboundEvent) -> None:
            if on_message is None:
                return
            text, attachments = await self._materialize_inbound_event(
                binding.session_id, event,
            )
            if not text:
                logger.warning(
                    "[QQ-adapter] Skipping message without usable content: "
                    "channel=%s msg_id=%s", channel_id, event.message_id,
                )
                return
            await on_message(
                InboundMessage(
                    channel_id=channel_id or binding.id,
                    channel_type=ImChannelType.QQ.value,
                    external_message_id=event.message_id,
                    route=ChannelRoute(
                        sender_id=event.sender_openid,
                        group_id=event.group_openid or "",
                    ),
                    segments=(
                        MessageSegment.of_text(text),
                        *(
                            MessageSegment.from_attachment(item)
                            for item in attachments
                        ),
                    ),
                )
            )

        # start() internally stops any existing connection for this channel
        await self._ws.start(
            channel_id=channel_id,
            session_id=binding.session_id,
            on_message=dispatch,
            app_id=app_id,
            app_secret=app_secret,
        )
        logger.info("[QQ-adapter] WS client started for channel=%s", channel_id)

    async def _materialize_inbound_event(
        self, session_id: str, event: QqInboundEvent,
    ) -> tuple[str, list[dict[str, Any]]]:
        """把 QQ 富媒体转成正文 + 已落盘附件.

        语音附件上腾讯自带 ``asr_refer_text`` 转写结果, 直接当正文使用; 同时把
        转码后的 WAV 落盘, 模型需要时可以听原始音频。
        """
        voices = [
            item
            for item in event.attachments
            if str(item.get("content_type") or "").lower() == _VOICE_CONTENT_TYPE
        ]
        if not voices:
            return event.content, []

        attachments: list[dict[str, Any]] = []
        transcripts: list[str] = []
        for item in voices:
            voice = await self._materialize_voice(session_id, item)
            attachments.extend(voice.attachments)
            if voice.transcript.strip():
                transcripts.append(voice.transcript.strip())

        text = "\n".join([event.content, *transcripts]).strip()
        return text or VOICE_PLACEHOLDER_TEXT, attachments

    async def _materialize_voice(
        self, session_id: str, attachment: Mapping[str, Any],
    ) -> InboundVoice:
        transcript = str(attachment.get("asr_refer_text") or "").strip()
        # 转码后的 WAV 通用得多, 原始链接常常是 SILK, 优先取 WAV.
        wav_url = str(attachment.get("voice_wav_url") or "")
        url = wav_url or str(attachment.get("url") or "")
        codec = VoiceCodec.WAV if wav_url else VoiceCodec.SILK
        try:
            audio = await self._api.download_attachment(url)
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "[QQ-adapter] Failed to download inbound voice, keeping "
                "transcript only: url=%.120s", url,
                exc_info=True,
            )
            return InboundVoice(transcript=transcript)

        return await self._voice_store.store(
            session_id=session_id,
            source=ImChannelType.QQ.value,
            audio=audio,
            codec=codec,
            transcript=transcript,
        )

    async def stop_listening(self, binding: ImBinding) -> None:
        """Stop the QQ WebSocket listener for a specific channel."""
        channel_id = binding.channel_id
        logger.info("[QQ-adapter] stop_listening: channel=%s", channel_id)
        await self._ws.stop(channel_id)

    async def complete_bind(
        self, binding: ImBinding, _params: dict,
    ) -> BindResult:
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=binding.channel_address or "qq-bot",
        )

    async def unbind(self, binding: ImBinding) -> None:
        channel_id = binding.channel_id
        logger.info("[QQ-adapter] unbind: channel=%s", channel_id)
        await self._ws.stop(channel_id)

    async def send(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> SendReceipt:
        route = message.route
        content = message.plain_text

        # Use per-binding credentials for sending
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")

        logger.info(
            "[QQ-adapter] send: session=%s reply_to=%s sender=%s group=%s content=%.100s",
            binding.session_id,
            route.reply_to_message_id, route.sender_id, route.group_id, content,
        )

        if not (route.group_id or route.sender_id):
            raise ChannelRoutingError(
                "Cannot send QQ message: no group or user in routing context. "
                "Send one message from QQ first to establish routing.",
                channel_type=ImChannelType.QQ.value,
            )

        send = (
            self._api.send_group_message
            if route.group_id
            else self._api.send_c2c_message
        )
        result = await send(
            route.group_id or route.sender_id,
            content,
            route.reply_to_message_id,
            app_id=app_id or None,
            app_secret=app_secret or None,
            msg_seq=self._message_sequence(message.idempotency_key),
        )
        return SendReceipt.of(
            str(result.get("id") or result.get("message_id") or ""),
        )

    async def close(self) -> None:
        """Shutdown adapter — drop every channel's WebSocket connection."""
        await self._ws.stop_all()

    @staticmethod
    def _message_sequence(idempotency_key: str) -> int | None:
        if not idempotency_key:
            return None
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 2_000_000_000 + 1
