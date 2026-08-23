from __future__ import annotations

import enum
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_route import ChannelRoute

_EMPTY_PAYLOAD: Mapping[str, Any] = MappingProxyType({})


class SegmentType(str, enum.Enum):
    """消息片段类型 — 渠道无关的最小内容单元."""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    CARD = "card"


#: 每种片段类型所需的渠道能力. 门面据此过滤渠道不支持的片段。
SEGMENT_CAPABILITY: Mapping[SegmentType, ChannelCapability] = MappingProxyType({
    SegmentType.TEXT: ChannelCapability.OUTBOUND_TEXT,
    SegmentType.IMAGE: ChannelCapability.OUTBOUND_ATTACHMENT,
    SegmentType.FILE: ChannelCapability.OUTBOUND_ATTACHMENT,
    SegmentType.AUDIO: ChannelCapability.OUTBOUND_ATTACHMENT,
    SegmentType.VIDEO: ChannelCapability.OUTBOUND_ATTACHMENT,
    SegmentType.CARD: ChannelCapability.RICH_CARD,
})

_MEDIA_SEGMENTS = frozenset({
    SegmentType.IMAGE,
    SegmentType.FILE,
    SegmentType.AUDIO,
    SegmentType.VIDEO,
})


@dataclass(frozen=True)
class MessageSegment:
    """消息片段.

    文本片段只用 ``text``；媒体片段用 ``path`` 指向已落盘的本地文件；
    卡片片段用 ``payload`` 承载渠道原生的卡片结构。
    """

    segment_type: SegmentType
    text: str = ""
    path: str = ""
    filename: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    duration_seconds: int = 0
    external_key: str = ""
    payload: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_PAYLOAD)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload or {})))

    @property
    def is_media(self) -> bool:
        return self.segment_type in _MEDIA_SEGMENTS

    @property
    def required_capability(self) -> ChannelCapability:
        return SEGMENT_CAPABILITY[self.segment_type]

    # -- 构造快捷方式 --

    @classmethod
    def of_text(cls, text: str) -> MessageSegment:
        return cls(segment_type=SegmentType.TEXT, text=text)

    @classmethod
    def of_card(cls, payload: Mapping[str, Any], fallback_text: str = "") -> MessageSegment:
        return cls(segment_type=SegmentType.CARD, payload=payload, text=fallback_text)

    @classmethod
    def of_media(
        cls,
        segment_type: SegmentType,
        *,
        path: str,
        filename: str = "",
        mime_type: str = "",
        size_bytes: int = 0,
        duration_seconds: int = 0,
        external_key: str = "",
    ) -> MessageSegment:
        return cls(
            segment_type=segment_type,
            path=path,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            external_key=external_key,
        )

    # -- 与现有附件 dict 的互转 --

    @classmethod
    def from_attachment(cls, attachment: Mapping[str, Any]) -> MessageSegment:
        mime_type = str(attachment.get("mime_type") or "application/octet-stream")
        return cls(
            segment_type=segment_type_for_mime(mime_type),
            path=str(attachment.get("path") or ""),
            filename=str(attachment.get("filename") or attachment.get("name") or ""),
            mime_type=mime_type,
            size_bytes=int(attachment.get("size_bytes") or 0),
            duration_seconds=int(attachment.get("duration") or 0),
            external_key=str(attachment.get("external_key") or ""),
        )

    def to_attachment(self, source: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "path": self.path,
        }
        if self.external_key:
            payload["external_key"] = self.external_key
        if self.duration_seconds:
            payload["duration"] = self.duration_seconds
        if source:
            payload["source"] = source
        return payload


def segment_type_for_mime(mime_type: str) -> SegmentType:
    normalized = (mime_type or "").lower()
    if normalized.startswith("image/"):
        return SegmentType.IMAGE
    if normalized.startswith("audio/"):
        return SegmentType.AUDIO
    if normalized.startswith("video/"):
        return SegmentType.VIDEO
    return SegmentType.FILE


@dataclass(frozen=True)
class InboundMessage:
    """入站消息 — 各渠道将平台私有格式翻译成本结构后交给编排层."""

    channel_id: str
    channel_type: str
    external_message_id: str
    route: ChannelRoute = field(default_factory=ChannelRoute)
    segments: Sequence[MessageSegment] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(self.segments))

    @property
    def plain_text(self) -> str:
        return "\n".join(
            segment.text
            for segment in self.segments
            if segment.segment_type is SegmentType.TEXT and segment.text
        ).strip()

    @property
    def media_segments(self) -> tuple[MessageSegment, ...]:
        return tuple(segment for segment in self.segments if segment.is_media)

    def attachments(self, source: str = "") -> list[dict[str, Any]]:
        return [
            segment.to_attachment(source or self.channel_type)
            for segment in self.media_segments
        ]


@dataclass(frozen=True)
class OutboundMessage:
    """出站消息 — 编排层构造, 由门面裁剪到渠道能力范围后交给适配器."""

    segments: Sequence[MessageSegment] = ()
    route: ChannelRoute = field(default_factory=ChannelRoute)
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(self.segments))

    @classmethod
    def of_text(
        cls,
        text: str,
        *,
        route: ChannelRoute | None = None,
        idempotency_key: str = "",
    ) -> OutboundMessage:
        return cls(
            segments=(MessageSegment.of_text(text),),
            route=route or ChannelRoute(),
            idempotency_key=idempotency_key,
        )

    @classmethod
    def of_text_with_attachments(
        cls,
        text: str,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        *,
        route: ChannelRoute | None = None,
        idempotency_key: str = "",
    ) -> OutboundMessage:
        segments: list[MessageSegment] = []
        if text.strip():
            segments.append(MessageSegment.of_text(text))
        segments.extend(
            MessageSegment.from_attachment(item) for item in (attachments or [])
        )
        return cls(
            segments=tuple(segments),
            route=route or ChannelRoute(),
            idempotency_key=idempotency_key,
        )

    @property
    def is_empty(self) -> bool:
        return not self.segments

    @property
    def plain_text(self) -> str:
        return "\n".join(
            segment.text
            for segment in self.segments
            if segment.segment_type is SegmentType.TEXT and segment.text
        ).strip()

    @property
    def media_segments(self) -> tuple[MessageSegment, ...]:
        return tuple(segment for segment in self.segments if segment.is_media)

    def with_route(self, route: ChannelRoute) -> OutboundMessage:
        return OutboundMessage(
            segments=self.segments,
            route=route,
            idempotency_key=self.idempotency_key,
        )

    def with_segments(self, segments: Sequence[MessageSegment]) -> OutboundMessage:
        return OutboundMessage(
            segments=segments,
            route=self.route,
            idempotency_key=self.idempotency_key,
        )


@dataclass(frozen=True)
class SendReceipt:
    """发送回执 — 门面据此判定投递是否真的成功."""

    external_message_id: str = ""
    skipped: bool = False
    skip_reason: str = ""

    @classmethod
    def of(cls, external_message_id: str) -> SendReceipt:
        return cls(external_message_id=external_message_id)

    @classmethod
    def skip(cls, reason: str) -> SendReceipt:
        return cls(skipped=True, skip_reason=reason)
