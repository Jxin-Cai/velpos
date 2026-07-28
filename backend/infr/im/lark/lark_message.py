from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class LarkMessageType(str, Enum):
    TEXT = "text"
    POST = "post"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    MEDIA = "media"
    INTERACTIVE = "interactive"


_TYPE_ALIASES = {
    "rich_text": LarkMessageType.POST,
    "card": LarkMessageType.INTERACTIVE,
    "video": LarkMessageType.MEDIA,
}


@dataclass(frozen=True)
class LarkOutboundMessage:
    """A typed Lark message.

    Media messages use ``file_path``. Video messages may additionally provide
    ``image_path`` or an already uploaded ``image_key`` for the cover image.
    """

    message_type: LarkMessageType
    content: str | dict[str, Any] = ""
    file_path: str = ""
    image_path: str = ""
    image_key: str = ""
    duration: int = 0
    file_name: str = ""

    @classmethod
    def from_value(
        cls,
        value: str | dict[str, Any] | LarkOutboundMessage,
    ) -> LarkOutboundMessage:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(message_type=LarkMessageType.TEXT, content=value)
        if not isinstance(value, dict):
            raise TypeError("Lark message content must be text, a mapping, or LarkOutboundMessage")

        raw_type = str(value.get("message_type") or value.get("msg_type") or value.get("type") or "text")
        message_type = _TYPE_ALIASES.get(raw_type)
        if message_type is None:
            try:
                message_type = LarkMessageType(raw_type)
            except ValueError as exc:
                raise ValueError(f"Unsupported Lark message type: {raw_type}") from exc
        return cls(
            message_type=message_type,
            content=value.get("content", value.get("text", "")),
            file_path=str(value.get("file_path") or value.get("path") or ""),
            image_path=str(value.get("image_path") or ""),
            image_key=str(value.get("image_key") or ""),
            duration=int(value.get("duration") or 0),
            file_name=str(value.get("file_name") or value.get("filename") or ""),
        )

    def encoded_content(self, *, file_key: str = "", image_key: str = "") -> str:
        if self.message_type is LarkMessageType.TEXT:
            return json.dumps({"text": str(self.content)}, ensure_ascii=False)
        if self.message_type in (LarkMessageType.POST, LarkMessageType.INTERACTIVE):
            if not isinstance(self.content, dict):
                raise ValueError(f"{self.message_type.value} content must be a mapping")
            return json.dumps(self.content, ensure_ascii=False)
        if self.message_type is LarkMessageType.IMAGE:
            return json.dumps({"image_key": image_key}, ensure_ascii=False)
        if self.message_type is LarkMessageType.FILE:
            return json.dumps({"file_key": file_key}, ensure_ascii=False)
        if self.message_type is LarkMessageType.AUDIO:
            body: dict[str, Any] = {"file_key": file_key}
            if self.duration > 0:
                body["duration"] = self.duration
            return json.dumps(body, ensure_ascii=False)
        if self.message_type is LarkMessageType.MEDIA:
            body: dict[str, Any] = {
                "file_key": file_key,
                "image_key": image_key,
            }
            if self.resolved_file_name():
                body["file_name"] = self.resolved_file_name()
            if self.duration > 0:
                body["duration"] = self.duration
            return json.dumps(body, ensure_ascii=False)
        raise ValueError(f"Unsupported Lark message type: {self.message_type.value}")

    def resolved_file_name(self) -> str:
        return self.file_name or Path(self.file_path).name or "attachment.bin"


@dataclass(frozen=True)
class LarkInboundContent:
    text: str
    resources: tuple[tuple[str, str], ...] = ()


def parse_inbound_content(message_type: str, raw_content: str) -> LarkInboundContent:
    """Convert a Lark message body into readable text and downloadable keys."""
    try:
        content = json.loads(raw_content) if raw_content else {}
    except (json.JSONDecodeError, TypeError):
        content = raw_content

    if message_type == LarkMessageType.TEXT.value:
        text = content.get("text", "") if isinstance(content, dict) else str(content)
        return LarkInboundContent(text=text.strip())

    if message_type == LarkMessageType.IMAGE.value:
        key = _string_value(content, "image_key")
        return LarkInboundContent(text="[收到图片]", resources=(("image", key),) if key else ())

    if message_type in {
        LarkMessageType.FILE.value,
        LarkMessageType.AUDIO.value,
        LarkMessageType.MEDIA.value,
    }:
        key = _string_value(content, "file_key")
        label = {
            LarkMessageType.FILE.value: "文件",
            LarkMessageType.AUDIO.value: "音频",
            LarkMessageType.MEDIA.value: "视频",
        }[message_type]
        name = _string_value(content, "file_name")
        suffix = f": {name}" if name else ""
        return LarkInboundContent(
            text=f"[收到{label}{suffix}]",
            resources=(("file", key),) if key else (),
        )

    if message_type == LarkMessageType.POST.value:
        resources: list[tuple[str, str]] = []
        text = _render_rich_text(content, resources)
        return LarkInboundContent(
            text=text or "[收到富文本消息]",
            resources=tuple(resources),
        )

    if message_type == LarkMessageType.INTERACTIVE.value:
        text = _render_card(content)
        return LarkInboundContent(text=text or "[收到卡片消息]")

    readable = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else str(content)
    return LarkInboundContent(text=f"[收到 {message_type} 消息]\n{readable}".strip())


def _string_value(value: Any, key: str) -> str:
    if not isinstance(value, dict):
        return ""
    result = value.get(key)
    return result if isinstance(result, str) else ""


def _render_rich_text(
    content: Any,
    resources: list[tuple[str, str]],
) -> str:
    if not isinstance(content, dict):
        return str(content or "").strip()
    localized = next(
        (value for value in content.values() if isinstance(value, dict) and "content" in value),
        content,
    )
    title = str(localized.get("title") or "").strip() if isinstance(localized, dict) else ""
    paragraphs = localized.get("content", []) if isinstance(localized, dict) else []
    lines: list[str] = [title] if title else []
    for paragraph in paragraphs if isinstance(paragraphs, list) else []:
        parts: list[str] = []
        for element in paragraph if isinstance(paragraph, list) else []:
            if not isinstance(element, dict):
                continue
            tag = element.get("tag")
            if tag == "img":
                key = str(element.get("image_key") or "")
                if key:
                    resources.append(("image", key))
                parts.append("[图片]")
            elif tag == "a":
                label = str(element.get("text") or element.get("href") or "")
                href = str(element.get("href") or "")
                parts.append(f"{label} ({href})" if href and label != href else label)
            elif tag == "at":
                parts.append(f"@{element.get('user_name') or element.get('user_id') or ''}")
            else:
                parts.append(str(element.get("text") or ""))
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _render_card(content: Any) -> str:
    if not isinstance(content, (dict, list)):
        return str(content or "").strip()
    collected: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"text", "content", "title", "value"} and isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned and cleaned not in collected:
                        collected.append(cleaned)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(content)
    return "\n".join(collected)
