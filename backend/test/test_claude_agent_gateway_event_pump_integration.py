from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from infr.client.claude_agent_gateway import ClaudeAgentGateway
from infr.client.claude_event_pump import ClaudeConnectionEventPump


class _PersistentClient:
    def __init__(self) -> None:
        self._messages: asyncio.Queue[object] = asyncio.Queue()
        self.queries: list[str] = []
        self.receive_invocations = 0

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_messages(self) -> AsyncIterator[object]:
        self.receive_invocations += 1
        while True:
            yield await self._messages.get()

    async def emit_result(self, text: str) -> None:
        await self._messages.put({
            "type": "result",
            "result": text,
            "is_error": False,
            "usage": {},
            "session_id": "sdk-session",
        })


@pytest.mark.asyncio
async def test_reuses_single_event_reader_across_query_turns() -> None:
    # Arrange
    gateway = ClaudeAgentGateway(cli_path="/bin/true")
    client = _PersistentClient()
    pump = ClaudeConnectionEventPump(
        "session-1",
        client,
        phase_changed=lambda phase: gateway._on_turn_phase_changed("session-1", phase),
        result_settle_seconds=0,
    )
    gateway._clients["session-1"] = client
    gateway._event_pumps["session-1"] = pump
    pump.start()

    # Act
    first = asyncio.create_task(_collect_query(gateway, "first"))
    await _wait_for_query_count(client, 1)
    await client.emit_result("first-result")
    first_messages = await asyncio.wait_for(first, timeout=1)

    second = asyncio.create_task(_collect_query(gateway, "second"))
    await _wait_for_query_count(client, 2)
    await client.emit_result("second-result")
    second_messages = await asyncio.wait_for(second, timeout=1)
    await pump.close()

    # Assert
    assert client.receive_invocations == 1
    assert [first_messages[-1]["content"]["text"], second_messages[-1]["content"]["text"]] == [
        "first-result",
        "second-result",
    ]


async def _collect_query(gateway: ClaudeAgentGateway, prompt: str) -> list[dict]:
    return [
        message
        async for message in gateway._execute_query("session-1", gateway._clients["session-1"], prompt)
    ]


async def _wait_for_query_count(client: _PersistentClient, expected: int) -> None:
    for _ in range(100):
        if len(client.queries) >= expected:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"Query count did not reach {expected}")
