from __future__ import annotations

from typing import Any

from domain.session.model.message import Message
from domain.session.model.message_type import MessageType


class MessageConversionService:
    """Encapsulates conversion rules between Claude Code message formats
    and VP domain model, stream message parsing, and assistant text extraction.
    """

    @staticmethod
    def convert_cc_messages(cc_messages: list) -> list[Message]:
        """Convert a Claude Code SessionMessage list to VP Message list.

        Iterates cc_messages, mapping each item by msg.type ("user" / "assistant")
        and msg.message.content structure (str / list[dict]) to the corresponding
        VP Message value object.

        Skips entries whose msg.message is None, and entries that produce
        no valid blocks after conversion.
        """
        pf_messages: list[Message] = []

        for cc_msg in cc_messages:
            msg_type = cc_msg.type
            raw_message = cc_msg.message

            if raw_message is None:
                continue

            content = raw_message.get("content", "")

            if msg_type == "user":
                _convert_user_message(content, pf_messages)
            elif msg_type == "assistant":
                _convert_assistant_message(content, pf_messages)

        return pf_messages

    @staticmethod
    def convert_stream_message(msg_dict: dict[str, Any]) -> Message | None:
        """Convert a single stream dict to a VP Message.

        Reads msg_dict["message_type"], attempts to resolve it to a MessageType
        enum value. Returns None if the type string is unknown (ValueError),
        signalling the caller to skip this entry.
        """
        msg_type_str = msg_dict["message_type"]
        try:
            msg_type_enum = MessageType(msg_type_str)
        except ValueError:
            return None

        return Message.create(
            message_type=msg_type_enum,
            content=msg_dict["content"],
        )

    @staticmethod
    def extract_assistant_text(messages: list[Message]) -> str:
        """Extract the text content from the last assistant message.

        Traverses the list from the end, finds the first message with
        MessageType.ASSISTANT, collects all text blocks from its
        content["blocks"], and returns the joined text stripped of
        leading/trailing whitespace. Returns empty string if no
        assistant message or no text blocks are found.
        """
        for msg in reversed(messages):
            if msg.message_type == MessageType.ASSISTANT:
                content = msg.content
                if isinstance(content, dict):
                    blocks = content.get("blocks", [])
                    texts = [
                        b.get("text", "")
                        for b in blocks
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    text = "".join(texts).strip()
                    if text:
                        return text
        return ""

    @staticmethod
    def summarise_content(content: dict[str, Any]) -> str:
        """Return a summary of message content for diagnostics, max 200 chars.

        Matching priority:
        1. content has "blocks" list -> first text block's text[:200],
           or "[tool_use: {name}]" for tool_use block
        2. content has "text" key -> str(text)[:200]
        3. content has "subtype" key -> "[system: {subtype}]"
        4. content has "results" key -> "[tool_results: {count} items]"
        5. fallback -> str(content)[:200]
        """
        if isinstance(content, dict):
            blocks = content.get("blocks", [])
            for b in blocks:
                if b.get("type") == "text":
                    text = b.get("text", "")
                    return text[:200] if text else "(empty text)"
                if b.get("type") == "tool_use":
                    return f"[tool_use: {b.get('name', '?')}]"

            if "text" in content:
                return str(content["text"])[:200]

            if "subtype" in content:
                return f"[system: {content.get('subtype', '')}]"

            if "results" in content:
                return f"[tool_results: {len(content['results'])} items]"

        return str(content)[:200]


def _convert_user_message(
    content: str | list,
    pf_messages: list[Message],
) -> None:
    """Process user-type content and append resulting Message(s) to pf_messages."""
    if isinstance(content, str):
        pf_messages.append(Message.create(
            message_type=MessageType.USER,
            content={"text": content},
        ))
    elif isinstance(content, list):
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in content
        )
        if has_tool_result:
            # Preserve text blocks alongside tool_result blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            if text_parts:
                pf_messages.append(Message.create(
                    message_type=MessageType.USER,
                    content={"text": " ".join(text_parts)},
                ))
            results = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    results.append({
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": str(block.get("content", "")),
                        "is_error": block.get("is_error", False),
                    })
            pf_messages.append(Message.create(
                message_type=MessageType.TOOL_RESULT,
                content={"results": results},
            ))
        else:
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            if text_parts:
                pf_messages.append(Message.create(
                    message_type=MessageType.USER,
                    content={"text": " ".join(text_parts)},
                ))


def _convert_assistant_message(
    content: str | list,
    pf_messages: list[Message],
) -> None:
    """Process assistant-type content and append resulting Message(s) to pf_messages."""
    if isinstance(content, str):
        pf_messages.append(Message.create(
            message_type=MessageType.ASSISTANT,
            content={"blocks": [{"type": "text", "text": content}]},
        ))
    elif isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                blocks.append({"type": "text", "text": block.get("text", "")})
            elif block_type == "tool_use":
                blocks.append({
                    "type": "tool_use",
                    "name": block.get("name", ""),
                    "id": block.get("id", ""),
                    "input": block.get("input", {}),
                })
            elif block_type == "thinking":
                blocks.append({
                    "type": "thinking",
                    "thinking": block.get("thinking", ""),
                })
            elif block_type == "tool_result":
                blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id", ""),
                    "content": str(block.get("content", "")),
                    "is_error": block.get("is_error", False),
                })

        if blocks:
            pf_messages.append(Message.create(
                message_type=MessageType.ASSISTANT,
                content={"blocks": blocks},
            ))
