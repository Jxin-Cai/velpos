"""渠道契约测试 — 所有 IM 渠道对编排层必须表现一致.

飞书是能力全集的参照渠道; 其余渠道只要如实声明自己的能力, 门面就会把
未声明的动作安全降级成空操作, 编排层因此不需要任何渠道特判。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.im_binding.im_channel_facade import ImChannelFacade
from domain.im_binding.acl.channel_errors import ChannelTransientError
from domain.im_binding.acl.im_channel_adapter import ImChannelAdapter
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    MessageSegment,
    OutboundMessage,
    SegmentType,
    SendReceipt,
)
from infr.im.lark.lark_adapter import LARK_CHANNEL_SPEC, LarkAdapter
from infr.im.openim.openim_adapter import OPENIM_CHANNEL_SPEC, OpenImAdapter
from infr.im.qq.qq_adapter import QQ_CHANNEL_SPEC, QqAdapter
from infr.im.weixin.weixin_adapter import WEIXIN_CHANNEL_SPEC, WeixinAdapter

#: 每种能力对应必须被适配器覆写的原语.
CAPABILITY_PRIMITIVES: dict[ChannelCapability, tuple[str, ...]] = {
    ChannelCapability.INBOUND_LISTEN: ("start_listening", "stop_listening"),
    ChannelCapability.REACTION: ("add_reaction", "remove_reaction"),
    ChannelCapability.TYPING_INDICATOR: ("start_typing", "stop_typing"),
}

CHANNELS = [
    pytest.param(LARK_CHANNEL_SPEC, LarkAdapter, id="lark"),
    pytest.param(WEIXIN_CHANNEL_SPEC, WeixinAdapter, id="weixin"),
    pytest.param(QQ_CHANNEL_SPEC, QqAdapter, id="qq"),
    pytest.param(OPENIM_CHANNEL_SPEC, OpenImAdapter, id="openim"),
]


def _binding(channel_type: ImChannelType) -> ImBinding:
    return ImBinding.reconstitute(
        id="binding1",
        session_id="session1",
        im_user_id="im-user",
        im_token="",
        binding_status=BindingStatus.BOUND,
        friend_user_id="friend1",
        qr_code_data="",
        created_at=datetime.now(),
        channel_type=channel_type,
        channel_id="channel1",
        config={},
    )


def _facade(spec: ImChannelSpec, adapter: ImChannelAdapter) -> ImChannelFacade:
    registry = ImChannelRegistry()
    registry.register(spec, lambda: adapter)
    return ImChannelFacade(registry)


class _RecordingAdapter(ImChannelAdapter):
    """记录调用的最小适配器, 用于验证门面的降级行为."""

    def __init__(self, receipt: SendReceipt | None = None) -> None:
        self.sent: list[OutboundMessage] = []
        self._receipt = receipt or SendReceipt.of("message1")

    async def bind(self, session_id, binding, params):  # pragma: no cover - 未使用
        raise NotImplementedError

    async def complete_bind(self, binding, params):  # pragma: no cover - 未使用
        raise NotImplementedError

    async def unbind(self, binding) -> None:  # pragma: no cover - 未使用
        raise NotImplementedError

    async def check_init_status(self, config) -> bool:  # pragma: no cover - 未使用
        return True

    async def initialize(self, params):  # pragma: no cover - 未使用
        raise NotImplementedError

    async def send(self, binding, message: OutboundMessage) -> SendReceipt:
        self.sent.append(message)
        return self._receipt


def _spec(*capabilities: ChannelCapability) -> ImChannelSpec:
    return ImChannelSpec(
        channel_type=ImChannelType.LARK,
        display_name="Fake",
        icon="fake",
        required_plugin=None,
        binding_mode=BindingMode.QR_CODE,
        capabilities=frozenset(capabilities),
    )


# ── 声明与实现必须一致 ───────────────────────────────────────────


@pytest.mark.parametrize(("spec", "adapter_class"), CHANNELS)
def test_implements_primitive_when_capability_is_declared(
    spec: ImChannelSpec, adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange
    declared = [
        (capability, primitive)
        for capability, primitives in CAPABILITY_PRIMITIVES.items()
        if spec.supports(capability)
        for primitive in primitives
    ]

    # Act
    missing = [
        f"{capability.value}->{primitive}"
        for capability, primitive in declared
        if getattr(adapter_class, primitive) is getattr(ImChannelAdapter, primitive)
    ]

    # Assert
    assert missing == []


@pytest.mark.parametrize(("spec", "adapter_class"), CHANNELS)
def test_declares_capability_when_primitive_is_implemented(
    spec: ImChannelSpec, adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange
    implemented = [
        (capability, primitive)
        for capability, primitives in CAPABILITY_PRIMITIVES.items()
        for primitive in primitives
        if getattr(adapter_class, primitive) is not getattr(ImChannelAdapter, primitive)
    ]

    # Act — 门面只按能力调用原语, 未声明的实现永远不会被触达.
    undeclared = [
        f"{capability.value}->{primitive}"
        for capability, primitive in implemented
        if not spec.supports(capability)
    ]

    # Assert
    assert undeclared == []


@pytest.mark.parametrize(("spec", "_adapter_class"), CHANNELS)
def test_declares_outbound_text_when_channel_is_registered(
    spec: ImChannelSpec, _adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange / Act / Assert — 发文本是所有渠道的底线能力.
    assert spec.supports(ChannelCapability.OUTBOUND_TEXT)


@pytest.mark.parametrize(("spec", "_adapter_class"), CHANNELS)
def test_supports_idempotency_when_message_id_echo_is_declared(
    spec: ImChannelSpec, _adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange — 门面在缺少消息标识时靠重试确认投递, 而重试只有在渠道
    # 自己去重时才安全.
    if not spec.supports(ChannelCapability.MESSAGE_ID_ECHO):
        pytest.skip("channel does not promise a message id")

    # Act / Assert
    assert spec.supports(ChannelCapability.IDEMPOTENCY)


@pytest.mark.parametrize(("spec", "_adapter_class"), CHANNELS)
def test_provides_progress_feedback_when_channel_is_registered(
    spec: ImChannelSpec, _adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange — 飞书用表情, 微信用输入中, 其余渠道用文本兜底; 但"任务在跑"
    # 这件事必须以某种方式告诉用户.
    feedback = {
        ChannelCapability.REACTION,
        ChannelCapability.TYPING_INDICATOR,
        ChannelCapability.PROGRESS_ACK,
    }

    # Act / Assert
    assert spec.capabilities & feedback


# ── 未声明的能力必须安全降级 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_skips_adapter_when_reaction_is_unsupported() -> None:
    # Arrange
    adapter = Mock(spec=ImChannelAdapter, add_reaction=AsyncMock())
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act
    reaction_id = await facade.add_reaction(
        _binding(ImChannelType.LARK), "message1", "OnIt",
    )

    # Assert
    adapter.add_reaction.assert_not_awaited()
    assert reaction_id == ""


@pytest.mark.asyncio
async def test_skips_adapter_when_typing_indicator_is_unsupported() -> None:
    # Arrange
    adapter = Mock(spec=ImChannelAdapter, start_typing=AsyncMock())
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act
    ticket = await facade.start_typing(_binding(ImChannelType.LARK), ChannelRoute())

    # Assert
    assert ticket == ""


@pytest.mark.asyncio
async def test_reports_unsupported_when_inbound_listen_is_missing() -> None:
    # Arrange
    adapter = Mock(spec=ImChannelAdapter, start_listening=AsyncMock())
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act
    started = await facade.start_listening(_binding(ImChannelType.LARK), AsyncMock())

    # Assert
    assert started is False


@pytest.mark.asyncio
async def test_degrades_media_to_text_when_attachment_is_unsupported() -> None:
    # Arrange
    adapter = _RecordingAdapter()
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act
    await facade.send(
        _binding(ImChannelType.LARK),
        OutboundMessage(
            segments=(
                MessageSegment.of_media(
                    SegmentType.IMAGE, path="/tmp/a.png", filename="a.png",
                ),
            ),
        ),
    )

    # Assert
    assert adapter.sent[0].plain_text == "[图片: a.png]"


@pytest.mark.asyncio
async def test_drops_reply_target_when_thread_reply_is_unsupported() -> None:
    # Arrange
    adapter = _RecordingAdapter()
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act
    await facade.send(
        _binding(ImChannelType.LARK),
        OutboundMessage.of_text(
            "hi", route=ChannelRoute(sender_id="u1", reply_to_message_id="m1"),
        ),
    )

    # Assert
    assert adapter.sent[0].route.reply_to_message_id == ""


@pytest.mark.asyncio
async def test_skips_delivery_when_no_segment_survives_degradation() -> None:
    # Arrange
    adapter = _RecordingAdapter()
    facade = _facade(_spec(ChannelCapability.RICH_CARD), adapter)

    # Act
    receipt = await facade.send(
        _binding(ImChannelType.LARK),
        OutboundMessage.of_text("hi"),
    )

    # Assert
    assert receipt.skipped is True


# ── 投递结果必须可信 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_delivery_when_promised_message_id_is_missing() -> None:
    # Arrange
    adapter = _RecordingAdapter(receipt=SendReceipt.of(""))
    facade = _facade(
        _spec(
            ChannelCapability.OUTBOUND_TEXT,
            ChannelCapability.MESSAGE_ID_ECHO,
            ChannelCapability.IDEMPOTENCY,
        ),
        adapter,
    )

    # Act / Assert
    with pytest.raises(ChannelTransientError):
        await facade.send(
            _binding(ImChannelType.LARK), OutboundMessage.of_text("hi"),
        )


@pytest.mark.asyncio
async def test_accepts_unconfirmed_delivery_when_channel_cannot_deduplicate() -> None:
    # Arrange — 渠道不去重时重试可能发出第二条, 宁可接受状态未知.
    adapter = _RecordingAdapter(receipt=SendReceipt.of(""))
    facade = _facade(
        _spec(
            ChannelCapability.OUTBOUND_TEXT, ChannelCapability.MESSAGE_ID_ECHO,
        ),
        adapter,
    )

    # Act
    receipt = await facade.send(
        _binding(ImChannelType.LARK), OutboundMessage.of_text("hi"),
    )

    # Assert
    assert receipt.external_message_id == ""


@pytest.mark.asyncio
async def test_closes_every_registered_adapter_when_process_shuts_down() -> None:
    # Arrange
    adapter = Mock(spec=ImChannelAdapter, close=AsyncMock())
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act
    await facade.close_all()

    # Assert
    adapter.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_keeps_closing_when_one_adapter_fails_to_shut_down() -> None:
    # Arrange
    registry = ImChannelRegistry()
    failing = Mock(spec=ImChannelAdapter, close=AsyncMock(side_effect=RuntimeError))
    healthy = Mock(spec=ImChannelAdapter, close=AsyncMock())
    registry.register(_spec(ChannelCapability.OUTBOUND_TEXT), lambda: failing)
    registry.register(
        ImChannelSpec(
            channel_type=ImChannelType.QQ,
            display_name="Fake QQ",
            icon="qq",
            required_plugin=None,
            binding_mode=BindingMode.QR_CODE,
        ),
        lambda: healthy,
    )

    # Act
    await ImChannelFacade(registry).close_all()

    # Assert
    healthy.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_normalizes_unknown_error_as_transient_when_adapter_raises() -> None:
    # Arrange
    adapter = Mock(
        spec=ImChannelAdapter,
        send=AsyncMock(side_effect=RuntimeError("boom")),
    )
    adapter.restore_route = Mock(return_value=ChannelRoute())
    facade = _facade(_spec(ChannelCapability.OUTBOUND_TEXT), adapter)

    # Act / Assert
    with pytest.raises(ChannelTransientError):
        await facade.send(
            _binding(ImChannelType.LARK), OutboundMessage.of_text("hi"),
        )


# ── 路由持久化必须可往返 ─────────────────────────────────────────


@pytest.mark.parametrize(("_spec_unused", "adapter_class"), CHANNELS)
def test_restores_route_when_persisted_route_is_reloaded(
    _spec_unused: ImChannelSpec, adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange
    adapter = adapter_class.__new__(adapter_class)
    route = ChannelRoute(
        sender_id="user1",
        group_id="group1",
        extras={key: "value1" for key in adapter.route_extra_keys()},
    )
    binding = _binding(ImChannelType.LARK)
    binding.update_config(adapter.persist_route(route))

    # Act
    restored = adapter.restore_route(binding)

    # Assert
    assert restored.extras == route.extras


@pytest.mark.parametrize(("_spec_unused", "adapter_class"), CHANNELS)
def test_covers_extra_keys_when_route_config_keys_are_listed(
    _spec_unused: ImChannelSpec, adapter_class: type[ImChannelAdapter],
) -> None:
    # Arrange
    adapter = adapter_class.__new__(adapter_class)
    route = ChannelRoute(
        sender_id="user1",
        extras={key: "value1" for key in adapter.route_extra_keys()},
    )

    # Act
    persisted = adapter.persist_route(route)

    # Assert — 换绑继承的键必须覆盖所有会被写入的键.
    assert set(persisted) <= set(adapter.route_config_keys())
