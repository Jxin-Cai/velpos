from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.im_binding.model.channel_spec import ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType


class ChannelRegistrationError(ValueError):
    """渠道注册非法 — 同一渠道类型被重复注册."""


class ImChannelRegistry:
    """IM 渠道注册表 — 运行时单例.

    适配器在启动时调用 register() 注册自身的能力声明和工厂函数。

    同一 ``ImChannelType`` 只允许注册一次: 重复注册几乎总是装配代码出错
    （两个 provider 声明了同一渠道）, 静默覆盖会让先注册的渠道悄悄失效,
    因此在启动时立刻失败。
    """

    def __init__(self) -> None:
        self._specs: dict[ImChannelType, ImChannelSpec] = {}
        self._factories: dict[ImChannelType, Callable[..., Any]] = {}

    def register(
        self,
        spec: ImChannelSpec,
        adapter_factory: Callable[..., Any],
    ) -> None:
        if spec.channel_type in self._specs:
            raise ChannelRegistrationError(
                f"IM channel already registered: {spec.channel_type.value}"
            )
        self._specs[spec.channel_type] = spec
        self._factories[spec.channel_type] = adapter_factory

    def is_registered(self, channel_type: ImChannelType) -> bool:
        return channel_type in self._specs

    def list_all(self) -> list[ImChannelSpec]:
        """返回所有已注册渠道的 spec."""
        return list(self._specs.values())

    def get_spec(self, channel_type: ImChannelType) -> ImChannelSpec:
        if channel_type not in self._specs:
            raise ValueError(f"Unknown channel type: {channel_type}")
        return self._specs[channel_type]

    def get_adapter_factory(self, channel_type: ImChannelType) -> Callable[..., Any]:
        if channel_type not in self._factories:
            raise ValueError(f"No adapter registered for: {channel_type}")
        return self._factories[channel_type]

    @property
    def registered_types(self) -> list[ImChannelType]:
        return list(self._specs.keys())
