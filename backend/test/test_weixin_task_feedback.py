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
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from infr.im.weixin.weixin_adapter import WeixinAdapter
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
            "last_context_token": "context1",
            **(config or {}),
        },
    )


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
    reaction_id = await adapter.add_reaction(binding, "message1", "OnIt")

    # Assert
    assert reaction_id == "channel1:message1"
    adapter._api.get_config.assert_awaited_once_with(
        "token",
        "user1",
        "context1",
    )
    adapter._api.send_typing.assert_awaited_once_with(
        "token",
        "user1",
        "ticket1",
        1,
    )

    await adapter.remove_reaction(binding, "message1", reaction_id)


@pytest.mark.asyncio
async def test_stops_typing_with_cancel_status_when_wechat_task_finishes():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_config=AsyncMock(return_value={"typing_ticket": "ticket1"}),
        send_typing=AsyncMock(),
    )
    binding = _binding()
    reaction_id = await adapter.add_reaction(binding, "message1", "OnIt")
    adapter._api.send_typing.reset_mock()

    # Act
    await adapter.remove_reaction(binding, "message1", reaction_id)

    # Assert
    adapter._api.send_typing.assert_awaited_once_with(
        "token",
        "user1",
        "ticket1",
        2,
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
    first_id = await adapter.add_reaction(binding, "message1", "OnIt")
    await adapter.remove_reaction(binding, "message1", first_id)
    second_id = await adapter.add_reaction(binding, "message2", "OnIt")

    # Assert
    adapter._api.get_config.assert_awaited_once()

    await adapter.remove_reaction(binding, "message2", second_id)


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
    adapter._api = Mock(
        send_text_message=AsyncMock(return_value={"message_id": "message1"}),
    )
    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter._TEXT_CHUNK_SEND_DELAY_SECONDS",
        0,
    )
    content = "第一部分。" + ("内容" * 2000)

    # Act
    await adapter.send_message(
        _binding(),
        content,
        {"sender_id": "user1", "context_token": "context1"},
        idempotency_key="result1",
    )

    # Assert
    sent_chunks = [
        call.args[2]
        for call in adapter._api.send_text_message.await_args_list
    ]
    assert len(sent_chunks) == 2
    assert "".join(sent_chunks) == content
    assert all(len(chunk) <= 3800 for chunk in sent_chunks)


@pytest.mark.asyncio
async def test_uses_distinct_idempotency_keys_when_wechat_result_is_chunked(
    monkeypatch,
):
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(
        send_text_message=AsyncMock(return_value={"message_id": "message1"}),
    )
    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter._TEXT_CHUNK_SEND_DELAY_SECONDS",
        0,
    )

    # Act
    await adapter.send_message(
        _binding(),
        "内容" * 2000,
        {"sender_id": "user1", "context_token": "context1"},
        idempotency_key="result1",
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
    adapter = Mock(
        add_reaction=AsyncMock(return_value="typing1"),
        remove_reaction=AsyncMock(),
    )
    registry = Mock()
    registry.get_adapter_factory.return_value = lambda: adapter
    service = ImChannelApplicationService(
        registry=registry,
        binding_repo=Mock(),
        init_repo=Mock(),
        session_service_factory=AsyncMock(),
    )
    service._persist_reply_context = AsyncMock()
    service._execute_inbound = AsyncMock(return_value="已修改两个文件，测试通过。")
    service._send_inbound_reply = AsyncMock()

    # Act
    await service._process_inbound(
        _binding(),
        "message1",
        "修复问题",
        "user1",
        "",
    )

    # Assert
    sent_content = service._send_inbound_reply.await_args.args[1]
    assert "· 已完成 · 用时" in sent_content
    assert sent_content.endswith("已修改两个文件，测试通过。")


@pytest.mark.asyncio
async def test_sends_started_feedback_when_wechat_task_exceeds_delay(monkeypatch):
    # Arrange
    registry = Mock()
    service = ImChannelApplicationService(
        registry=registry,
        binding_repo=Mock(),
        init_repo=Mock(),
    )
    service._send_inbound_reply = AsyncMock()
    monkeypatch.setattr(
        "application.im_binding.im_channel_application_service."
        "_WEIXIN_PROGRESS_ACK_DELAY_SECONDS",
        0,
    )

    # Act
    await service._send_delayed_inbound_ack(
        _binding(),
        {"sender_id": "user1"},
        "channel1",
        "message1",
        "ABC123",
    )

    # Assert
    sent_content = service._send_inbound_reply.await_args.args[1]
    assert sent_content == (
        "任务 ABC123 · 已开始\n\n"
        "正在执行你的请求，完成后会发送结果。"
    )


@pytest.mark.asyncio
async def test_formats_failed_feedback_when_wechat_task_returns_terminal_error():
    # Arrange
    adapter = Mock(
        add_reaction=AsyncMock(return_value="typing1"),
        remove_reaction=AsyncMock(),
    )
    registry = Mock()
    registry.get_adapter_factory.return_value = lambda: adapter
    service = ImChannelApplicationService(
        registry=registry,
        binding_repo=Mock(),
        init_repo=Mock(),
        session_service_factory=AsyncMock(),
    )
    service._persist_reply_context = AsyncMock()
    service._execute_inbound = AsyncMock(
        side_effect=TerminalInboundError("测试未通过"),
    )
    service._send_inbound_reply = AsyncMock()

    # Act
    await service._process_inbound(
        _binding(),
        "message1",
        "修复问题",
        "user1",
        "",
    )

    # Assert
    sent_content = service._send_inbound_reply.await_args.args[1]
    assert "· 未完成 · 用时" in sent_content
    assert sent_content.endswith("原因：测试未通过")


@pytest.mark.asyncio
async def test_sends_waiting_feedback_when_wechat_session_is_busy():
    # Arrange
    adapter = Mock(
        add_reaction=AsyncMock(return_value="typing1"),
        remove_reaction=AsyncMock(),
    )
    registry = Mock()
    registry.get_adapter_factory.return_value = lambda: adapter
    service = ImChannelApplicationService(
        registry=registry,
        binding_repo=Mock(),
        init_repo=Mock(),
        session_service_factory=AsyncMock(),
    )
    service._persist_reply_context = AsyncMock()
    service._execute_inbound = AsyncMock(
        side_effect=RetryableInboundError("Session is busy"),
    )
    service._send_inbound_reply = AsyncMock()

    # Act / Assert
    with pytest.raises(RetryableInboundError, match="Session is busy"):
        await service._process_inbound(
            _binding(),
            "message1",
            "继续处理",
            "user1",
            "",
        )
    sent_content = service._send_inbound_reply.await_args.args[1]
    assert "· 等待中" in sent_content
