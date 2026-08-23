from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import InboundMessage, OutboundMessage
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


def _lark_client(**message_methods) -> SimpleNamespace:
    return SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(message=SimpleNamespace(**message_methods)),
        )
    )


def _lark_response(message_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        success=lambda: True,
        data=SimpleNamespace(message_id=message_id),
    )


@pytest.mark.asyncio
async def test_forwards_idempotency_key_when_lark_message_is_sent():
    # Arrange
    adapter = LarkAdapter()
    create = AsyncMock(return_value=_lark_response("lark-message"))
    adapter._get_sdk_client = Mock(return_value=_lark_client(acreate=create))
    binding = _binding(
        ImChannelType.LARK,
        {"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )

    # Act
    receipt = await adapter.send(
        binding,
        OutboundMessage.of_text("hello", idempotency_key="stable-key"),
    )

    # Assert
    assert receipt.external_message_id == "lark-message"
    request = create.await_args.args[0]
    assert request.body.uuid == str(uuid.uuid5(uuid.NAMESPACE_URL, "stable-key"))


@pytest.mark.asyncio
async def test_does_not_fallback_when_lark_reply_outcome_is_ambiguous():
    # Arrange
    adapter = LarkAdapter()
    reply = AsyncMock(side_effect=TimeoutError("timed out"))
    create = AsyncMock()
    adapter._get_sdk_client = Mock(
        return_value=_lark_client(areply=reply, acreate=create)
    )
    binding = _binding(
        ImChannelType.LARK,
        {"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )

    # Act / Assert
    with pytest.raises(TimeoutError):
        await adapter.send(
            binding,
            OutboundMessage.of_text(
                "hello",
                route=ChannelRoute(reply_to_message_id="source-message"),
                idempotency_key="stable-key",
            ),
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_falls_back_when_lark_reply_is_explicitly_rejected():
    # Arrange
    adapter = LarkAdapter()
    reply = AsyncMock(side_effect=LarkApiError("message expired"))
    create = AsyncMock(return_value=_lark_response("fallback-message"))
    adapter._get_sdk_client = Mock(
        return_value=_lark_client(areply=reply, acreate=create)
    )
    binding = _binding(
        ImChannelType.LARK,
        {"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )

    # Act
    receipt = await adapter.send(
        binding,
        OutboundMessage.of_text(
            "hello",
            route=ChannelRoute(reply_to_message_id="source-message"),
            idempotency_key="stable-key",
        ),
    )

    # Assert
    assert receipt.external_message_id == "fallback-message"


@pytest.mark.asyncio
async def test_uses_stable_sequence_when_qq_message_is_retried():
    # Arrange
    api = SimpleNamespace(
        send_c2c_message=AsyncMock(return_value={"id": "qq-message"}),
    )
    adapter = QqAdapter(SimpleNamespace(), api)
    binding = _binding(ImChannelType.QQ, {"app_id": "app", "app_secret": "secret"})
    message = OutboundMessage.of_text(
        "hello",
        route=ChannelRoute(sender_id="user"),
        idempotency_key="stable-key",
    )

    # Act
    await adapter.send(binding, message)
    await adapter.send(binding, message)

    # Assert
    first_sequence = api.send_c2c_message.await_args_list[0].kwargs["msg_seq"]
    second_sequence = api.send_c2c_message.await_args_list[1].kwargs["msg_seq"]
    assert first_sequence == second_sequence


@pytest.mark.asyncio
async def test_forwards_idempotency_key_when_wechat_message_is_sent():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = SimpleNamespace(
        send_text_message=AsyncMock(return_value="wechat-message"),
    )
    binding = _binding(ImChannelType.WEIXIN, {"bot_token": "token"})

    # Act
    receipt = await adapter.send(
        binding,
        OutboundMessage.of_text(
            "hello",
            route=ChannelRoute(sender_id="user"),
            idempotency_key="stable-key",
        ),
    )

    # Assert
    assert receipt.external_message_id == "wechat-message"
    assert (
        adapter._api.send_text_message.await_args.kwargs["idempotency_key"]
        == "stable-key"
    )


@pytest.mark.asyncio
async def test_reports_configuration_error_when_inbound_context_factory_is_missing():
    # Arrange
    service = ImChannelApplicationService(
        registry=Mock(),
        binding_repo=Mock(),
        init_repo=Mock(),
    )
    binding = _binding(ImChannelType.WEIXIN, {"bot_token": "token"})
    inbound = InboundMessage(
        channel_id="channel1",
        channel_type=ImChannelType.WEIXIN.value,
        external_message_id="message1",
        route=ChannelRoute(sender_id="user"),
    )

    # Act / Assert
    with pytest.raises(
        RuntimeError,
        match="requires a session service context factory",
    ):
        await service._execute_inbound(
            binding,
            inbound,
            "source-message",
            inbound.route,
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
