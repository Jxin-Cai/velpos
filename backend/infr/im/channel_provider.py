"""渠道 Provider 契约 — 每个渠道包自带装配逻辑, 组合根零渠道知识.

新增渠道的完整步骤:

1. 在 :mod:`domain.im_binding.model.channel_type` 中新增枚举成员;
2. 新建 ``infr/im/<channel>/`` 包, 实现 ``ImChannelAdapter`` 与
   ``ImChannelSpec``;
3. 在包内提供 ``provider.py``, 暴露 ``build_channel(context)``;
4. 在 :mod:`infr.im.builtin_channels` 的清单中追加一行。

除清单一行之外, 不需要触碰 ``ohs/dependencies.py``、``main.py`` 或任何
编排代码 — 渠道私有的客户端、长连接与单例策略全部封装在 provider 内。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from domain.im_binding.acl.im_channel_adapter import ImChannelAdapter
from domain.im_binding.model.channel_spec import ImChannelSpec
from infr.config.im_config import ImConfig


@dataclass(frozen=True)
class ChannelBuildContext:
    """渠道装配上下文 — provider 构建适配器时可用的共享配置."""

    im_config: ImConfig


@dataclass(frozen=True)
class ChannelRegistration:
    """一个渠道向注册表提交的完整注册信息."""

    spec: ImChannelSpec
    adapter_factory: Callable[[], ImChannelAdapter]


#: 渠道 provider 的统一签名: 构建渠道私有依赖并返回注册信息.
ChannelProviderFn = Callable[[ChannelBuildContext], ChannelRegistration]
