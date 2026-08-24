"""内置渠道清单 — 新增渠道只需在此追加一行 provider.

参考插件化消息网关的常见做法（内置清单 + 可选外部发现）, 这里先收敛
内置渠道; 若未来需要三方渠道包, 可在此基础上叠加 entry-points 扫描,
组合根与编排层都不需要改动。
"""

from __future__ import annotations

import logging

from domain.im_binding.model.channel_registry import ImChannelRegistry
from infr.im.channel_provider import ChannelBuildContext, ChannelProviderFn
from infr.im.lark import provider as lark_provider
from infr.im.openim import provider as openim_provider
from infr.im.qq import provider as qq_provider
from infr.im.weixin import provider as weixin_provider

logger = logging.getLogger(__name__)

BUILTIN_CHANNEL_PROVIDERS: tuple[ChannelProviderFn, ...] = (
    openim_provider.build_channel,
    lark_provider.build_channel,
    qq_provider.build_channel,
    weixin_provider.build_channel,
)


def register_builtin_channels(
    registry: ImChannelRegistry,
    context: ChannelBuildContext,
) -> None:
    """把所有内置渠道注册到 *registry*.

    provider 构建失败会直接抛出 — 渠道装配错误属于启动期缺陷,
    静默跳过只会把问题推迟到用户绑定时才暴露。
    """
    for provider in BUILTIN_CHANNEL_PROVIDERS:
        registration = provider(context)
        registry.register(registration.spec, registration.adapter_factory)
        logger.info(
            "IM channel registered: %s",
            registration.spec.channel_type.value,
        )
