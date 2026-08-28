"""微信 iLink 会话生命周期 — notifystart/notifystop 与 stale token (-14) 恢复."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from domain.im_binding.acl.channel_errors import ChannelAuthError
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from infr.im.weixin.weixin_adapter import WeixinAdapter
from infr.im.weixin.weixin_api import (
    CHANNEL_VERSION,
    WeixinApiClient,
    _raise_for_business_error,
)


def _binding() -> ImBinding:
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
        config={"bot_token": "token"},
    )


def test_raises_auth_error_when_stale_token_reported_via_errcode():
    # Arrange
    payload = {"ret": -14, "errcode": -14, "errmsg": "session timeout"}

    # Act / Assert
    with pytest.raises(ChannelAuthError):
        _raise_for_business_error("getupdates", payload)


def test_raises_auth_error_when_stale_token_reported_via_ret_only():
    # Arrange — 服务端可能只带 ret 不带 errcode.
    payload = {"ret": -14, "errmsg": "session timeout"}

    # Act / Assert
    with pytest.raises(ChannelAuthError):
        _raise_for_business_error("getupdates", payload)


def test_accepts_response_when_ret_is_zero():
    # Arrange
    payload = {"ret": 0, "msgs": []}

    # Act / Assert — 不抛异常
    _raise_for_business_error("getupdates", payload)


@pytest.mark.asyncio
async def test_posts_notifystart_when_session_start_is_reported():
    # Arrange
    api = WeixinApiClient()
    api._post = AsyncMock(return_value={"ret": 0})

    # Act
    await api.notify_start("token")

    # Assert
    api._post.assert_awaited_once_with(
        "token",
        "msg/notifystart",
        {"base_info": {"channel_version": CHANNEL_VERSION}},
    )


@pytest.mark.asyncio
async def test_posts_notifystop_when_session_stop_is_reported():
    # Arrange
    api = WeixinApiClient()
    api._post = AsyncMock(return_value={"ret": 0})

    # Act
    await api.notify_stop("token")

    # Assert
    api._post.assert_awaited_once_with(
        "token",
        "msg/notifystop",
        {"base_info": {"channel_version": CHANNEL_VERSION}},
    )


@pytest.mark.asyncio
async def test_notifies_start_when_poll_loop_begins():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(notify_start=AsyncMock(return_value={"ret": 0}))
    binding = _binding()
    stop_event = asyncio.Event()
    stop_event.set()
    adapter._stop_events[binding.channel_id] = stop_event

    # Act
    await adapter._run_poll_loop(binding)

    # Assert
    adapter._api.notify_start.assert_awaited_once_with("token")


@pytest.mark.asyncio
async def test_retries_quickly_when_session_rebuild_succeeds(monkeypatch):
    # Arrange — 凭证被拒但 notifystart 重建成功, 应短退避快速恢复.
    adapter = WeixinAdapter()
    adapter._api = Mock(
        get_updates=AsyncMock(side_effect=ChannelAuthError("stale token")),
        notify_start=AsyncMock(return_value={"ret": 0}),
    )
    binding = _binding()
    stop_event = asyncio.Event()
    adapter._stop_events[binding.channel_id] = stop_event
    delays: list[float] = []

    async def record_delay(seconds: float) -> None:
        delays.append(seconds)
        stop_event.set()

    monkeypatch.setattr(
        "infr.im.weixin.weixin_adapter.asyncio.sleep", record_delay,
    )

    # Act
    await adapter._run_poll_loop(binding)

    # Assert
    assert delays == [5]


@pytest.mark.asyncio
async def test_notifies_stop_when_listening_stops():
    # Arrange
    adapter = WeixinAdapter()
    adapter._api = Mock(notify_stop=AsyncMock(return_value={"ret": 0}))

    # Act
    await adapter.stop_listening(_binding())

    # Assert
    adapter._api.notify_stop.assert_awaited_once_with("token")


@pytest.mark.asyncio
async def test_keeps_stop_flow_when_notifystop_fails():
    # Arrange — 下线上报失败不应阻断停止流程.
    adapter = WeixinAdapter()
    adapter._api = Mock(
        notify_stop=AsyncMock(side_effect=RuntimeError("network")),
    )

    # Act / Assert — 不抛异常
    await adapter.stop_listening(_binding())
