"""入站语音物化 — 各 IM 渠道共用的落盘与附件组装.

各平台的语音协议差异很大: 飞书下发 opus 文件但不带转写, 需要另调语音识别
接口; 微信 iLink 在 ``voice_item.text`` 里直接给服务端转写结果; QQ 在附件上
同时给 ``asr_refer_text`` 与转码后的 WAV。差异留在各适配器里, 而"把音频字节
落盘并组装成编排层认识的附件字典"是同一件事, 收敛在此避免三处重复实现。
"""

from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from infr.storage.attachment_storage_gateway import AttachmentStorageGateway

logger = logging.getLogger(__name__)

#: 转写缺失时的正文占位 — 保证语音消息不会因空正文在入站阶段被丢弃.
VOICE_PLACEHOLDER_TEXT = "[语音消息]"

#: 各平台都用毫秒表示语音时长, 附件字典统一收敛成秒.
MILLISECONDS_PER_SECOND = 1000


class VoiceCodec(str, enum.Enum):
    """入站语音编码 — 决定落盘后缀与 MIME 类型."""

    SILK = "silk"
    OPUS = "opus"
    WAV = "wav"
    MP3 = "mp3"
    AMR = "amr"

    @property
    def suffix(self) -> str:
        return f".{self.value}"

    @property
    def mime_type(self) -> str:
        return _VOICE_MIME_TYPES[self]


_VOICE_MIME_TYPES: Mapping[VoiceCodec, str] = {
    VoiceCodec.SILK: "audio/silk",
    VoiceCodec.OPUS: "audio/ogg",
    VoiceCodec.WAV: "audio/wav",
    VoiceCodec.MP3: "audio/mpeg",
    VoiceCodec.AMR: "audio/amr",
}


@dataclass(frozen=True)
class InboundVoice:
    """一条入站语音的物化结果.

    ``transcript`` 是平台或识别服务给出的转写文本, ``attachment`` 是已落盘的
    原始音频。两者都可能缺失 — 转写不可用时靠音频文件, 音频下载失败时靠转写
    文本, 全都失败时至少留下占位正文, 用户不会看到"消息已读但无响应"。
    """

    transcript: str = ""
    attachment: Mapping[str, Any] | None = None

    @property
    def display_text(self) -> str:
        return self.transcript.strip() or VOICE_PLACEHOLDER_TEXT

    @property
    def attachments(self) -> list[dict[str, Any]]:
        return [dict(self.attachment)] if self.attachment else []


class InboundVoiceStore:
    """把入站语音字节落盘, 并组装成编排层认识的附件字典."""

    def __init__(self, storage: AttachmentStorageGateway | None = None) -> None:
        self._storage = storage or AttachmentStorageGateway()

    async def store(
        self,
        *,
        session_id: str,
        source: str,
        audio: bytes,
        codec: VoiceCodec,
        filename: str = "",
        transcript: str = "",
        duration_ms: int = 0,
        external_key: str = "",
    ) -> InboundVoice:
        """落盘 *audio* 并返回物化结果; 落盘失败只丢音频, 保留转写文本."""
        if not audio:
            return InboundVoice(transcript=transcript)

        resolved_name = _resolve_filename(filename, source, codec)
        try:
            path, digest = await asyncio.to_thread(
                self._storage.save, "", session_id, resolved_name, audio,
            )
        except (OSError, ValueError):
            logger.error(
                "[IM-voice] Failed to persist inbound voice: source=%s session=%s",
                source,
                session_id,
                exc_info=True,
            )
            return InboundVoice(transcript=transcript)

        attachment: dict[str, Any] = {
            "filename": resolved_name,
            "mime_type": codec.mime_type,
            "size_bytes": len(audio),
            "path": path,
            "sha256": digest,
            "source": source,
        }
        if transcript.strip():
            attachment["transcript"] = transcript.strip()
        if duration_ms > 0:
            attachment["duration"] = round(duration_ms / MILLISECONDS_PER_SECOND)
        if external_key:
            attachment["external_key"] = external_key
        return InboundVoice(transcript=transcript, attachment=attachment)


def _resolve_filename(filename: str, source: str, codec: VoiceCodec) -> str:
    if filename:
        return filename
    return f"{source}-voice-{uuid.uuid4().hex[:12]}{codec.suffix}"
