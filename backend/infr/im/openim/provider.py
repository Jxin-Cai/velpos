from __future__ import annotations

from infr.client.im_api_gateway import ImApiGateway
from infr.client.im_ws_client import ImWsClient
from infr.im.channel_provider import ChannelBuildContext, ChannelRegistration
from infr.im.openim.openim_adapter import (
    OPENIM_CHANNEL_SPEC,
    OpenImAdapter,
    OpenImStubAdapter,
)


def build_channel(context: ChannelBuildContext) -> ChannelRegistration:
    """OpenIM 依赖环境变量配置; 未配置时注册 stub, 让 UI 能提示缺什么."""
    if not context.im_config.enabled:
        return ChannelRegistration(
            spec=OPENIM_CHANNEL_SPEC,
            adapter_factory=OpenImStubAdapter,
        )
    adapter = OpenImAdapter(
        im_gateway=ImApiGateway(config=context.im_config),
        im_ws_gateway=ImWsClient(config=context.im_config),
    )
    return ChannelRegistration(
        spec=OPENIM_CHANNEL_SPEC,
        adapter_factory=lambda: adapter,
    )
