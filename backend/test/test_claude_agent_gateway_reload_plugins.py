from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from infr.client.claude_agent_gateway import ClaudeAgentGateway


def _gateway_with_session(
    session_id: str = "session-1",
    cwd: str = "/workspace/project",
    *,
    send_control: AsyncMock | None = None,
    disconnect: AsyncMock | None = None,
) -> tuple[ClaudeAgentGateway, AsyncMock]:
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")
    control = send_control or AsyncMock(return_value={"plugins": [], "commands": [], "error_count": 0})
    client = type(
        "Client",
        (),
        {
            "_query": type("Query", (), {"_send_control_request": control})(),
            "disconnect": disconnect or AsyncMock(),
        },
    )()
    gateway._clients[session_id] = client
    gateway._session_cwds[session_id] = cwd
    return gateway, control


@pytest.mark.asyncio
async def test_sends_reload_plugins_control_request_when_session_matches_cwd() -> None:
    # Arrange
    gateway, send_control = _gateway_with_session()

    # Act
    count = await gateway.reload_plugins_by_cwd("/workspace/project")

    # Assert
    assert count == 1
    send_control.assert_awaited_once_with({"subtype": "reload_plugins"}, timeout=30.0)
    assert "session-1" in gateway._clients


@pytest.mark.asyncio
async def test_disconnects_idle_session_when_reload_plugins_control_request_fails() -> None:
    # Arrange
    send_control = AsyncMock(side_effect=RuntimeError("control request timeout"))
    gateway, _ = _gateway_with_session(send_control=send_control)
    client = gateway._clients["session-1"]
    gateway._event_pumps["session-1"] = type("Pump", (), {"close": AsyncMock()})()

    # Act
    count = await gateway.reload_plugins_by_cwd("/workspace/project")

    # Assert
    assert count == 1
    assert "session-1" not in gateway._clients
    client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_skips_reload_when_no_session_matches_cwd() -> None:
    # Arrange
    gateway, send_control = _gateway_with_session(cwd="/workspace/other")

    # Act
    count = await gateway.reload_plugins_by_cwd("/workspace/project")

    # Assert
    assert count == 0
    send_control.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedules_reload_when_session_query_is_active() -> None:
    # Arrange
    gateway, send_control = _gateway_with_session()
    gateway._active_sessions.add("session-1")

    # Act
    count = await gateway.reload_plugins_by_cwd("/workspace/project")

    # Assert
    assert count == 1
    send_control.assert_not_awaited()
    assert "session-1" in gateway._clients
    pending = gateway._pending_plugin_reload_tasks.get("session-1")
    assert pending is not None
    assert not pending.done()
    pending.cancel()


@pytest.mark.asyncio
async def test_keeps_busy_session_connected_when_reload_is_deferred() -> None:
    # Arrange
    send_control = AsyncMock(side_effect=RuntimeError("control request timeout"))
    gateway, _ = _gateway_with_session(send_control=send_control)
    gateway._active_sessions.add("session-1")
    client = gateway._clients["session-1"]

    # Act
    count = await gateway.reload_plugins_by_cwd("/workspace/project")

    # Assert
    assert count == 1
    assert "session-1" in gateway._clients
    client.disconnect.assert_not_awaited()
    send_control.assert_not_awaited()
    pending = gateway._pending_plugin_reload_tasks.get("session-1")
    assert pending is not None
    pending.cancel()


@pytest.mark.asyncio
async def test_reschedules_instead_of_disconnecting_when_reload_fails_during_query() -> None:
    # Arrange
    send_control = AsyncMock(side_effect=RuntimeError("control request timeout"))
    gateway, _ = _gateway_with_session(send_control=send_control)
    client = gateway._clients["session-1"]
    gateway._active_sessions.add("session-1")

    # Act
    result = await gateway._reload_plugins_now("session-1", client)

    # Assert
    assert result is True
    assert "session-1" in gateway._clients
    client.disconnect.assert_not_awaited()
    pending = gateway._pending_plugin_reload_tasks.get("session-1")
    assert pending is not None
    pending.cancel()


@pytest.mark.asyncio
async def test_defers_reload_when_session_control_lock_is_held() -> None:
    # Arrange
    gateway, send_control = _gateway_with_session()
    lock = gateway._client_operation_lock("session-1")
    await lock.acquire()

    try:
        # Act
        count = await gateway.reload_plugins_by_cwd("/workspace/project")
    finally:
        lock.release()

    # Assert
    assert count == 1
    send_control.assert_not_awaited()
    assert "session-1" in gateway._clients
    pending = gateway._pending_plugin_reload_tasks.get("session-1")
    assert pending is not None
    pending.cancel()


@pytest.mark.asyncio
async def test_reloads_after_busy_session_becomes_idle() -> None:
    # Arrange
    gateway, send_control = _gateway_with_session()
    gateway._active_sessions.add("session-1")

    # Act
    count = await gateway.reload_plugins_by_cwd("/workspace/project")
    pending = gateway._pending_plugin_reload_tasks["session-1"]
    gateway._active_sessions.discard("session-1")
    await pending

    # Assert
    assert count == 1
    send_control.assert_awaited_once_with({"subtype": "reload_plugins"}, timeout=30.0)
    assert "session-1" in gateway._clients


@pytest.mark.asyncio
async def test_disconnects_after_deferred_reload_fails_when_idle() -> None:
    # Arrange
    send_control = AsyncMock(side_effect=RuntimeError("control request timeout"))
    gateway, _ = _gateway_with_session(send_control=send_control)
    gateway._active_sessions.add("session-1")
    client = gateway._clients["session-1"]
    gateway._event_pumps["session-1"] = type("Pump", (), {"close": AsyncMock()})()

    # Act
    await gateway.reload_plugins_by_cwd("/workspace/project")
    pending = gateway._pending_plugin_reload_tasks["session-1"]
    gateway._active_sessions.discard("session-1")
    await pending

    # Assert
    assert "session-1" not in gateway._clients
    client.disconnect.assert_awaited_once()
