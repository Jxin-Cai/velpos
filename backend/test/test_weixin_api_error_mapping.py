"""微信 iLink 用 HTTP 200 回报业务失败, 静默吞掉就会表现为"消息不再发送"."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from domain.im_binding.acl.channel_errors import (
    ChannelAuthError,
    ChannelPermanentError,
    ChannelTransientError,
)
from infr.im.weixin.weixin_api import (
    WeixinApiClient,
    _raise_for_business_error,
    _raise_for_http_status,
)


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={},
        request=httpx.Request("POST", "https://example.com/ilink/bot/sendmessage"),
    )


@pytest.mark.asyncio
async def test_returns_message_id_when_wechat_accepts_the_message():
    # Arrange
    api = WeixinApiClient()
    api._post = AsyncMock(return_value={"message_id": "wechat-message"})

    # Act
    message_id = await api.send_text_message("token", "user1", "hello")

    # Assert
    assert message_id == "wechat-message"


@pytest.mark.asyncio
async def test_reports_transient_failure_when_message_id_is_missing():
    # Arrange
    api = WeixinApiClient()
    api._post = AsyncMock(return_value={"errcode": 0})

    # Act / Assert
    with pytest.raises(ChannelTransientError):
        await api.send_text_message("token", "user1", "hello")


def test_reports_auth_failure_when_bot_token_is_rejected():
    # Arrange / Act / Assert
    with pytest.raises(ChannelAuthError):
        _raise_for_business_error("sendmessage", {"errcode": 40001, "errmsg": "bad"})


def test_reports_transient_failure_when_wechat_rate_limits():
    # Arrange / Act / Assert
    with pytest.raises(ChannelTransientError):
        _raise_for_business_error("sendmessage", {"errcode": 45009})


def test_reports_permanent_failure_when_wechat_rejects_the_content():
    # Arrange / Act / Assert
    with pytest.raises(ChannelPermanentError):
        _raise_for_business_error("sendmessage", {"errcode": 40003})


def test_accepts_response_when_generic_code_field_is_present():
    # Arrange — ``code`` 不是微信的错误码约定, 不能据此判失败.

    # Act
    _raise_for_business_error("getupdates", {"code": 200, "msg": "ok"})

    # Assert — 未抛异常即通过.


def test_reports_auth_failure_when_http_status_is_unauthorized():
    # Arrange / Act / Assert
    with pytest.raises(ChannelAuthError):
        _raise_for_http_status("sendmessage", _response(401))


def test_reports_transient_failure_when_http_status_is_server_error():
    # Arrange / Act / Assert
    with pytest.raises(ChannelTransientError):
        _raise_for_http_status("sendmessage", _response(503))


def test_reports_permanent_failure_when_http_status_is_bad_request():
    # Arrange / Act / Assert
    with pytest.raises(ChannelPermanentError):
        _raise_for_http_status("sendmessage", _response(400))
