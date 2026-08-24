from __future__ import annotations

from infr.im.channel_provider import ChannelBuildContext, ChannelRegistration
from infr.im.qq.qq_adapter import QQ_CHANNEL_SPEC, QqAdapter
from infr.im.qq.qq_api import QqApiClient
from infr.im.qq.qq_ws_client import QqWsClient


def build_channel(_context: ChannelBuildContext) -> ChannelRegistration:
    """QQ 适配器共享同一对 API/WS 客户端, 适配器本身无状态可即用即建."""
    api_client = QqApiClient()
    ws_client = QqWsClient(api_client=api_client)
    return ChannelRegistration(
        spec=QQ_CHANNEL_SPEC,
        adapter_factory=lambda: QqAdapter(ws_client=ws_client, api_client=api_client),
    )
