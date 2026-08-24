from __future__ import annotations

from infr.im.channel_provider import ChannelBuildContext, ChannelRegistration
from infr.im.weixin.weixin_adapter import WEIXIN_CHANNEL_SPEC, WeixinAdapter


def build_channel(_context: ChannelBuildContext) -> ChannelRegistration:
    """微信适配器必须是单例 — 每渠道轮询循环的生命周期挂在实例上."""
    adapter = WeixinAdapter()
    return ChannelRegistration(
        spec=WEIXIN_CHANNEL_SPEC,
        adapter_factory=lambda: adapter,
    )
