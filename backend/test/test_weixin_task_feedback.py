from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from application.im_binding.im_channel_application_service import (
    ImChannelApplicationService,
    RetryableInboundError,
    TerminalInboundError,
)
from application.im_binding.im_channel_facade import ImChannelFacade
from application.im_binding.inbound_progress_reporter import (
    InboundProgressReporter,
    TaskOutcome,
)
from domain.im_binding.acl.channel_errors import ChannelAuthError
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    InboundMessage,
    MessageSegment,
    OutboundMessage,
)
from infr.im.weixin.weixin_adapter import WEIXIN_CHANNEL_SPEC, WeixinAdapter
from infr.im.weixin.weixin_api import WeixinApiClient


def _binding(config: dict | None = None) -> ImBinding:
    return ImBinding.reconstitute(
        id="binding1",
        session_id="session1",
        im_user_id="",
        im_token="",
        binding_status=BindingStatus.BOUND,
        friend_user_id="",
        qr_code_data="",
        created_at=datetime.now(),
        channel_type=ImChannelType.WEIXIN,
        channel_id="channel1",
        config={
            "bot_token": "token",
            "last_sender_id": "user1",
            "last_route_context_token": "context1",
            **(config or {}),
        },
    )


def _inbound(text: str = "修复问题") -> InboundMessage:
    return InboundMessage(
        channel_id="channel1",
        channel_type=ImChannelType.WEIXIN.value,
        external_message_id="message1",
        route=ChannelRoute(
            sender_id="user1", extras={"context_token": "context1"},
        ),
        segments=(MessageSegment.of_text(text),),
    )


def _weixin_service(adapter: Mock) -> ImChannelApplicationService:
    """Build the service wired to a stubbed WeChat adapter but the real spec."""
    registry = Mock()
    registry.get_spec.return_value = WEIXIN_CHANNEL_SPEC
    registry.get_adapter_factory.return_value = lambda: adapter
    service = ImChannelApplicationService(
        registry=registry,
        binding_repo=Mock(),
        init_repo=Mock(),
        session_service_factory=AsyncMock(),
    )
    service._persist_route = AsyncMock()
    service._dispatch_outbound = AsyncMock()
    return service


def _stub_adapter() -> Mock:
    adapter = Mock(
        start_typing=AsyncMock(return_value="typing1"),
        stop_typing=AsyncMock(),
        add_reaction=AsyncMock(return_value=""),
        remove_reaction=AsyncMock(),
    )
    adapter.restore_route = Mock(return_value=ChannelRoute())
    adapter.persist_route = Mock(return_value={})
    return adapter


def _sent_text(service: ImChannelApplicationService) -> str:
    message: OutboundMessage = service._dispatch_outbound.await_args.args[1]
    return message.plain_text


@pytest.mark.asyncio
async def test_starts_typing_with_ticket_when_wechat_task_begins():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_config=AsyncMock(return_value={"typing_ticket": "ticket1"}),
        send_typing=AsyncMock(),
    )
    binding = _binding()

    # Act
    ticket = await adapter.start_typing(binding, ChannelRoute())

    # Assert
    adapter._api.send_typing.assert_awaited_once_with(
        "token", "user1", "ticket1", 1,
    )

    await adapter.stop_typing(binding, ticket)


@pytest.mark.asyncio
async def test_reads_context_token_from_binding_when_typing_starts():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_config=AsyncMock(return_value={"typing_ticket": "ticket1"}),
        send_typing=AsyncMock(),
    )
    binding = _binding()

    # Act
    ticket = await adapter.start_typing(binding, ChannelRoute())

    # Assert
    adapter._api.get_config.assert_awaited_once_with("token", "user1", "context1")

    await adapter.stop_typing(binding, ticket)


@pytest.mark.asyncio
async def test_stops_typing_with_cancel_status_when_wechat_task_finishes():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_config=AsyncMock(return_value={"typing_ticket": "ticket1"}),
        send_typing=AsyncMock(),
    )
    binding = _binding()
    ticket = await adapter.start_typing(binding, ChannelRoute())
    adapter._api.send_typing.reset_mock()

    # Act
    await adapter.stop_typing(binding, ticket)

    # Assert
    adapter._api.send_typing.assert_awaited_once_with(
        "token", "user1", "ticket1", 2,
    )


@pytest.mark.asyncio
async def test_reuses_cached_ticket_when_same_wechat_user_starts_another_task():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_config=AsyncMock(return_value={"typing_ticket": "ticket1"}),
        send_typing=AsyncMock(),
    )
    binding = _binding()

    # Act
    first = await adapter.start_typing(binding, ChannelRoute())
    await adapter.stop_typing(binding, first)
    second = await adapter.start_typing(binding, ChannelRoute())

    # Assert
    adapter._api.get_config.assert_awaited_once()

    await adapter.stop_typing(binding, second)


@pytest.mark.asyncio
async def test_refreshes_typing_status_when_keepalive_interval_elapses(monkeypatch):
    # Arrange
    api = Mock(send_typing=AsyncMock())
    sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter.asyncio.sleep",
        sleep,
    )

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await WeixinAdapter._run_typing_keepalive(
            api,
            "token",
            "user1",
            "ticket1",
        )
    api.send_typing.assert_awaited_once_with(
        "token",
        "user1",
        "ticket1",
        1,
    )


@pytest.mark.asyncio
async def test_stops_polling_when_wechat_credentials_expire():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_updates=AsyncMock(side_effect=ChannelAuthError("token expired")),
    )
    binding = _binding()
    adapter._stop_events[binding.channel_id] = asyncio.Event()

    # Act
    await adapter._run_poll_loop(binding)

    # Assert — 循环退出而不是无限重试.
    adapter._api.get_updates.assert_awaited_once()


@pytest.mark.asyncio
async def test_backs_off_progressively_when_wechat_polling_keeps_failing(monkeypatch):
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(get_updates=AsyncMock(side_effect=RuntimeError("network")))
    binding = _binding()
    stop_event = asyncio.Event()
    adapter._stop_events[binding.channel_id] = stop_event
    delays: list[float] = []

    async def record_delay(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) == 3:
            stop_event.set()

    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter.asyncio.sleep", record_delay,
    )

    # Act
    await adapter._run_poll_loop(binding)

    # Assert
    assert delays == [3, 6, 12]


@pytest.mark.asyncio
async def test_propagates_typing_error_when_wechat_api_rejects_request():
    # Arrange
    api = WeixinApiClient()
    api._post = AsyncMock(side_effect=RuntimeError("typing rejected"))

    # Act / Assert
    with pytest.raises(RuntimeError, match="typing rejected"):
        await api.send_typing("token", "user1", "ticket1", 1)


@pytest.mark.asyncio
async def test_splits_long_result_when_wechat_message_exceeds_limit(monkeypatch):
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(send_text_message=AsyncMock(return_value="message1"))
    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter._TEXT_CHUNK_SEND_DELAY_SECONDS",
        0,
    )
    content = "第一部分。" + ("内容" * 2000)

    # Act
    await adapter.send(
        _binding(),
        OutboundMessage.of_text(
            content,
            route=ChannelRoute(
                sender_id="user1", extras={"context_token": "context1"},
            ),
            idempotency_key="result1",
        ),
    )

    # Assert
    sent_chunks = [
        call.args[2] for call in adapter._api.send_text_message.await_args_list
    ]
    assert len(sent_chunks) == 2
    assert "".join(sent_chunks) == content


@pytest.mark.asyncio
async def test_uses_distinct_idempotency_keys_when_wechat_result_is_chunked(
    monkeypatch,
):
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(send_text_message=AsyncMock(return_value="message1"))
    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter._TEXT_CHUNK_SEND_DELAY_SECONDS",
        0,
    )

    # Act
    await adapter.send(
        _binding(),
        OutboundMessage.of_text(
            "内容" * 2000,
            route=ChannelRoute(
                sender_id="user1", extras={"context_token": "context1"},
            ),
            idempotency_key="result1",
        ),
    )

    # Assert
    sent_keys = [
        call.kwargs["idempotency_key"]
        for call in adapter._api.send_text_message.await_args_list
    ]
    assert sent_keys == ["result1:chunk:1:2", "result1:chunk:2:2"]


@pytest.mark.asyncio
async def test_formats_completed_feedback_when_wechat_task_succeeds():
    # Arrange
    service = _weixin_service(_stub_adapter())
    service._execute_inbound = AsyncMock(return_value="已修改两个文件，测试通过。")

    # Act
    await service._process_inbound(_binding(), _inbound())

    # Assert
    assert "· 已完成 · 用时" in _sent_text(service)


@pytest.mark.asyncio
async def test_appends_assistant_answer_when_wechat_task_succeeds():
    # Arrange
    service = _weixin_service(_stub_adapter())
    service._execute_inbound = AsyncMock(return_value="已修改两个文件，测试通过。")

    # Act
    await service._process_inbound(_binding(), _inbound())

    # Assert
    assert _sent_text(service).endswith("已修改两个文件，测试通过。")


@pytest.mark.asyncio
async def test_sends_started_feedback_when_wechat_task_exceeds_delay(monkeypatch):
    # Arrange
    send_text = AsyncMock()
    monkeypatch.setattr(
        "application.im_binding.inbound_progress_reporter."
        "PROGRESS_ACK_DELAY_SECONDS",
        0,
    )
    registry = Mock()
    registry.get_spec.return_value = WEIXIN_CHANNEL_SPEC
    registry.get_adapter_factory.return_value = _stub_adapter
    reporter = InboundProgressReporter(
        facade=ImChannelFacade(registry),
        binding=_binding(),
        route=ChannelRoute(sender_id="user1"),
        source_message_id="message1",
        task_code="ABC123",
        send_text=send_text,
    )

    # Act
    async with reporter:
        await asyncio.sleep(0.05)

    # Assert
    assert send_text.await_args.args[0] == (
        "任务 ABC123 · 已开始\n\n"
        "正在执行你的请求，完成后会发送结果。"
    )


@pytest.mark.asyncio
async def test_formats_failed_feedback_when_wechat_task_returns_terminal_error():
    # Arrange
    service = _weixin_service(_stub_adapter())
    service._execute_inbound = AsyncMock(
        side_effect=TerminalInboundError("测试未通过"),
    )

    # Act
    await service._process_inbound(_binding(), _inbound())

    # Assert
    assert _sent_text(service).endswith("原因：测试未通过")


@pytest.mark.asyncio
async def test_sends_waiting_feedback_when_wechat_session_is_busy():
    # Arrange
    service = _weixin_service(_stub_adapter())
    service._execute_inbound = AsyncMock(
        side_effect=RetryableInboundError("Session is busy"),
    )

    # Act / Assert
    with pytest.raises(RetryableInboundError, match="Session is busy"):
        await service._process_inbound(_binding(), _inbound("继续处理"))
    assert TaskOutcome.WAITING.value in _sent_text(service)
