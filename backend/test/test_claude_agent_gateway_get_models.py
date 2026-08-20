from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from infr.client.claude_agent_gateway import ClaudeAgentGateway


@pytest.mark.asyncio
async def test_returns_models_when_first_reads_are_empty(monkeypatch) -> None:
    # Arrange
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")
    reads = [
        [],
        [{"value": "claude-sonnet-4", "displayName": "Sonnet"}],
    ]

    async def fake_temp() -> list[dict]:
        return reads.pop(0) if reads else []

    gateway._read_models_from_temp_client = fake_temp  # type: ignore[method-assign]
    gateway._read_models_from_existing_clients = AsyncMock(return_value=[])  # type: ignore[method-assign]
    monkeypatch.setattr("infr.client.claude_agent_gateway.asyncio.sleep", AsyncMock())

    # Act
    models = await gateway.get_models()

    # Assert
    assert models[0]["value"] == "claude-sonnet-4"
    assert models[0]["context_window"] > 0


@pytest.mark.asyncio
async def test_refetches_models_from_config_on_every_call(monkeypatch) -> None:
    # Arrange
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")
    reads = [
        [{"value": "claude-opus-4", "displayName": "Opus"}],
        [{"value": "claude-sonnet-4", "displayName": "Sonnet"}],
    ]

    async def fake_temp() -> list[dict]:
        return reads.pop(0)

    gateway._read_models_from_temp_client = fake_temp  # type: ignore[method-assign]
    gateway._read_models_from_existing_clients = AsyncMock(return_value=[])  # type: ignore[method-assign]
    monkeypatch.setattr("infr.client.claude_agent_gateway.asyncio.sleep", AsyncMock())

    # Act
    first = await gateway.get_models()
    second = await gateway.get_models()

    # Assert
    assert first[0]["value"] == "claude-opus-4"
    assert second[0]["value"] == "claude-sonnet-4"


@pytest.mark.asyncio
async def test_falls_back_to_existing_client_when_temp_client_empty(monkeypatch) -> None:
    # Arrange
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")
    gateway._read_models_from_temp_client = AsyncMock(return_value=[])  # type: ignore[method-assign]
    gateway._read_models_from_existing_clients = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"value": "claude-haiku-4", "displayName": "Haiku"}],
    )
    monkeypatch.setattr("infr.client.claude_agent_gateway.asyncio.sleep", AsyncMock())

    # Act
    models = await gateway.get_models()

    # Assert
    assert models[0]["value"] == "claude-haiku-4"
