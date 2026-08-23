from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

_EMPTY: Mapping[str, str] = MappingProxyType({})

#: ``extras`` 中每个键的最大长度, 防止渠道返回超长令牌撑爆持久化字段.
_MAX_EXTRA_VALUE_LENGTH = 1024


@dataclass(frozen=True)
class ChannelRoute:
    """回复路由 — 描述"这条回复该发到渠道的哪里".

    取代此前散落在各处的裸 ``dict`` reply_context。``extras`` 承载渠道
    私有的路由字段（如微信的 ``context_token``），由适配器通过
    :meth:`ImChannelAdapter.route_extra_keys` 声明，随入站事件与出站消息
    一起持久化，因此进程重启或换 worker 处理都不会丢失。
    """

    sender_id: str = ""
    group_id: str = ""
    reply_to_message_id: str = ""
    extras: Mapping[str, str] = field(default_factory=lambda: _EMPTY)

    def __post_init__(self) -> None:
        normalized = {
            str(key): str(value)[:_MAX_EXTRA_VALUE_LENGTH]
            for key, value in (self.extras or {}).items()
            if key and value
        }
        object.__setattr__(self, "extras", MappingProxyType(normalized))

    @property
    def is_empty(self) -> bool:
        return not (
            self.sender_id
            or self.group_id
            or self.reply_to_message_id
            or self.extras
        )

    def merge(self, other: ChannelRoute | None) -> ChannelRoute:
        """用 *other* 中的非空字段覆盖本路由, 返回新实例."""
        if other is None:
            return self
        return ChannelRoute(
            sender_id=other.sender_id or self.sender_id,
            group_id=other.group_id or self.group_id,
            reply_to_message_id=(
                other.reply_to_message_id or self.reply_to_message_id
            ),
            extras={**self.extras, **other.extras},
        )

    def with_reply_to(self, message_id: str) -> ChannelRoute:
        return ChannelRoute(
            sender_id=self.sender_id,
            group_id=self.group_id,
            reply_to_message_id=message_id,
            extras=self.extras,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为可持久化的 JSON 结构."""
        payload: dict[str, Any] = {}
        if self.sender_id:
            payload["sender_id"] = self.sender_id
        if self.group_id:
            payload["group_id"] = self.group_id
        if self.reply_to_message_id:
            payload["reply_to_message_id"] = self.reply_to_message_id
        if self.extras:
            payload["extras"] = dict(self.extras)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> ChannelRoute:
        """从持久化结构还原.

        同时兼容历史格式：旧版 reply_context 是扁平 dict, 用 ``msg_id``
        表示线程回复目标, 且渠道私有字段直接平铺在顶层。
        """
        if not payload:
            return cls()

        known = {"sender_id", "group_id", "reply_to_message_id", "msg_id", "extras"}
        extras = dict(payload.get("extras") or {})
        for key, value in payload.items():
            if key not in known and isinstance(value, (str, int, float)):
                extras[key] = str(value)

        return cls(
            sender_id=str(payload.get("sender_id") or ""),
            group_id=str(payload.get("group_id") or ""),
            reply_to_message_id=str(
                payload.get("reply_to_message_id") or payload.get("msg_id") or ""
            ),
            extras=extras,
        )
