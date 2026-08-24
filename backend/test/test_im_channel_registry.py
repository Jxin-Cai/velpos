"""渠道注册表与内置 provider 装配测试.

注册表是渠道插拔的核心: 重复注册必须在启动时失败, 内置清单必须
把所有渠道装配完整, OpenIM 依据配置在真实适配器与 stub 之间切换。
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest

from domain.im_binding.model.channel_registry import (
    ChannelRegistrationError,
    ImChannelRegistry,
)
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from infr.config.im_config import ImConfig
from infr.im.builtin_channels import register_builtin_channels
from infr.im.channel_provider import ChannelBuildContext
from infr.im.openim.openim_adapter import OpenImAdapter, OpenImStubAdapter


def _spec(channel_type: ImChannelType) -> ImChannelSpec:
    return ImChannelSpec(
        channel_type=channel_type,
        display_name="Fake",
        icon="fake",
        required_plugin=None,
        binding_mode=BindingMode.QR_CODE,
    )


def _disabled_openim_config() -> ImConfig:
    return ImConfig(ws_addr="", api_addr="", admin_secret="", admin_user_id="")


def _enabled_openim_config() -> ImConfig:
    return ImConfig(
        ws_addr="ws://localhost:10001",
        api_addr="http://localhost:10002",
        admin_secret="secret",
        admin_user_id="admin",
    )


def test_rejects_duplicate_registration_when_channel_type_already_registered() -> None:
    # Arrange
    registry = ImChannelRegistry()
    registry.register(_spec(ImChannelType.LARK), lambda: None)

    # Act / Assert
    with pytest.raises(ChannelRegistrationError):
        registry.register(_spec(ImChannelType.LARK), lambda: None)


def test_reports_registered_when_spec_is_added() -> None:
    # Arrange
    registry = ImChannelRegistry()

    # Act
    registry.register(_spec(ImChannelType.QQ), lambda: None)

    # Assert
    assert registry.is_registered(ImChannelType.QQ)


def test_registers_every_channel_type_when_builtin_manifest_is_loaded() -> None:
    # Arrange
    registry = ImChannelRegistry()
    context = ChannelBuildContext(im_config=_disabled_openim_config())

    # Act
    register_builtin_channels(registry, context)

    # Assert — 每个渠道类型都必须被某个 provider 覆盖.
    assert set(registry.registered_types) == set(ImChannelType)


def test_uses_stub_adapter_when_openim_is_not_configured() -> None:
    # Arrange
    registry = ImChannelRegistry()
    context = ChannelBuildContext(im_config=_disabled_openim_config())
    register_builtin_channels(registry, context)

    # Act
    adapter = registry.get_adapter_factory(ImChannelType.OPENIM)()

    # Assert
    assert isinstance(adapter, OpenImStubAdapter)


def test_uses_real_adapter_when_openim_is_configured() -> None:
    # Arrange
    registry = ImChannelRegistry()
    context = ChannelBuildContext(im_config=_enabled_openim_config())
    register_builtin_channels(registry, context)

    # Act
    adapter = registry.get_adapter_factory(ImChannelType.OPENIM)()

    # Assert
    assert isinstance(adapter, OpenImAdapter)
