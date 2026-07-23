from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from application.im_binding.im_channel_application_service import (
    ImChannelApplicationService,
)
from infr.im.lark.lark_adapter import LarkAdapter
from infr.im.lark.lark_api import LarkApiError
from infr.im.qq.qq_adapter import QqAdapter
from infr.im.weixin.weixin_adapter import WeixinAdapter


def _binding(channel_type: ImChannelType, config: dict) -> ImBinding:
    return ImBinding.reconstitute(
        id="binding1",
        session_id="session1",
        im_user_id="",
        im_token="",
        binding_status=BindingStatus.BOUND,
        friend_user_id="",
        qr_code_data="",
        created_at=datetime.now(),
        channel_type=channel_type,
        channel_id="channel1",
        config=config,
    )


@pytest.mark.asyncio
async def test_forwards_idempotency_key_when_lark_message_is_sent():
    # Arrange
    adapter = LarkAdapter()
    adapter._api = SimpleNamespace(
        get_tenant_token=AsyncMock(return_value="token"),
        send_message=AsyncMock(return_value={"message_id": "lark-message"}),
    )
    binding = _binding(
        ImChannelType.LARK,
        {"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )

    # Act
    message_id = await adapter.send_message(
        binding,
        "hello",
        idempotency_key="stable-key",
    )

    # Assert
    assert message_id == "lark-message"
    assert adapter._api.send_message.await_args.kwargs["idempotency_key"] == "stable-key"


@pytest.mark.asyncio
async def test_does_not_fallback_when_lark_reply_outcome_is_ambiguous():
    # Arrange
    adapter = LarkAdapter()
    adapter._api = SimpleNamespace(
        get_tenant_token=AsyncMock(return_value="token"),
        reply_message=AsyncMock(side_effect=TimeoutError("timed out")),
        send_message=AsyncMock(),
    )
    binding = _binding(
        ImChannelType.LARK,
        {"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )

    # Act / Assert
    with pytest.raises(TimeoutError):
        await adapter.send_message(
            binding,
            "hello",
            {"msg_id": "source-message"},
            idempotency_key="stable-key",
        )
    adapter._api.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_falls_back_when_lark_reply_is_explicitly_rejected():
    # Arrange
    adapter = LarkAdapter()
    adapter._api = SimpleNamespace(
        get_tenant_token=AsyncMock(return_value="token"),
        reply_message=AsyncMock(side_effect=LarkApiError("message expired")),
        send_message=AsyncMock(return_value={"message_id": "fallback-message"}),
    )
    binding = _binding(
        ImChannelType.LARK,
        {"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )

    # Act
    message_id = await adapter.send_message(
        binding,
        "hello",
        {"msg_id": "source-message"},
        idempotency_key="stable-key",
    )

    # Assert
    assert message_id == "fallback-message"


@pytest.mark.asyncio
async def test_uses_stable_sequence_when_qq_message_is_retried():
    # Arrange
    api = SimpleNamespace(
        send_c2c_message=AsyncMock(return_value={"id": "qq-message"}),
    )
    adapter = QqAdapter(SimpleNamespace(), api)
    binding = _binding(
        ImChannelType.QQ,
        {"app_id": "app", "app_secret": "secret"},
    )
    context = {"sender_id": "user"}

    # Act
    await adapter.send_message(
        binding,
        "hello",
        context,
        idempotency_key="stable-key",
    )
    await adapter.send_message(
        binding,
        "hello",
        context,
        idempotency_key="stable-key",
    )

    # Assert
    first_sequence = api.send_c2c_message.await_args_list[0].kwargs["msg_seq"]
    second_sequence = api.send_c2c_message.await_args_list[1].kwargs["msg_seq"]
    assert first_sequence == second_sequence


@pytest.mark.asyncio
async def test_forwards_idempotency_key_when_wechat_message_is_sent():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = SimpleNamespace(
        send_text_message=AsyncMock(return_value={"message_id": "wechat-message"}),
    )
    binding = _binding(
        ImChannelType.WEIXIN,
        {"bot_token": "token"},
    )

    # Act
    message_id = await adapter.send_message(
        binding,
        "hello",
        {"sender_id": "user"},
        idempotency_key="stable-key",
    )

    # Assert
    assert message_id == "wechat-message"
    assert (
        adapter._api.send_text_message.await_args.kwargs["idempotency_key"]
        == "stable-key"
    )


def test_treats_failed_result_as_error_when_assistant_output_is_partial():
    # Arrange
    session = SimpleNamespace(
        messages=[
            Message.create(MessageType.USER, {"text": "work"}),
            Message.create(MessageType.ASSISTANT, {"text": "partial"}),
            Message.create(
                MessageType.RESULT,
                {"is_error": True, "text": "MODEL_NOT_ALLOWED"},
            ),
        ]
    )

    # Act
    response = ImChannelApplicationService._extract_response_after(session, 0)
    result_error = ImChannelApplicationService._extract_result_error_after(session, 0)

    # Assert
    assert response == ""
    assert result_error == "MODEL_NOT_ALLOWED"
