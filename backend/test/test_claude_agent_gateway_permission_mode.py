from __future__ import annotations

import asyncio

import pytest

import infr.client.claude_agent_gateway as claude_agent_gateway_module
from infr.client.claude_agent_gateway import ClaudeAgentGateway


@pytest.mark.asyncio
async def test_enables_runtime_bypass_when_sdk_client_starts(monkeypatch) -> None:
    # Arrange
    captured_options: dict = {}

    class _OptionsStub:
        def __init__(self, **kwargs) -> None:
            captured_options.update(kwargs)

    class _ClientStub:
        def __init__(self, options) -> None:
            self.options = options

        async def connect(self) -> None:
            return None

    monkeypatch.setattr(claude_agent_gateway_module, "ClaudeAgentOptions", _OptionsStub)
    monkeypatch.setattr(claude_agent_gateway_module, "ClaudeSDKClient", _ClientStub)
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")

    # Act
    await gateway._try_connect(
        session_id="session-1",
        model="claude-sonnet-4-6",
        perm_mode="acceptEdits",
        cwd="/tmp/project",
        prev_sdk_sid=None,
    )

    # Assert
    assert captured_options["extra_args"] == {
        "allow-dangerously-skip-permissions": None,
    }


@pytest.mark.asyncio
async def test_propagates_cancellation_when_pending_permission_is_cancelled() -> None:
    # Arrange
    gateway = ClaudeAgentGateway(
        cli_path="/usr/local/bin/claude",
        permission_mode="acceptEdits",
    )

    async def broadcast(_session_id: str, _event: dict) -> None:
        return None

    gateway._broadcast_fn = broadcast
    callback = gateway._create_can_use_tool_callback("session-1")
    permission_task = asyncio.create_task(callback("Bash", {"command": "pwd"}, None))
    await asyncio.sleep(0)

    # Act
    cancelled = await gateway.cancel_pending_response("session-1")

    # Assert
    assert cancelled is True
    with pytest.raises(asyncio.CancelledError):
        await permission_task
