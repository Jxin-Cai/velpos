from __future__ import annotations

from infr.im.channel_provider import ChannelBuildContext, ChannelRegistration
from infr.im.lark.lark_adapter import LARK_CHANNEL_SPEC, LarkAdapter


def build_channel(_context: ChannelBuildContext) -> ChannelRegistration:
    """飞书适配器必须是单例 — WS 监听连接的生命周期挂在实例上."""
    adapter = LarkAdapter()
    return ChannelRegistration(
        spec=LARK_CHANNEL_SPEC,
        adapter_factory=lambda: adapter,
    )
