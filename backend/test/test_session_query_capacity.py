from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.session_query_engine import SessionQueryEngine


def _engine() -> SessionQueryEngine:
    return SessionQueryEngine(
        session_repository=Mock(),
        claude_agent_gateway=Mock(mark_active=Mock(), mark_idle=Mock()),
        connection_manager=SimpleNamespace(broadcast=AsyncMock()),
        recorder=SimpleNamespace(record_audit_event=AsyncMock()),
        stream_consumer=Mock(),
        save_session_fn=AsyncMock(),
        reconnect_db_session_fn=AsyncMock(),
        accept_or_reject_sdk_session_id_fn=AsyncMock(),
        resolve_resume_sdk_session_id_fn=AsyncMock(),
        refresh_context_usage_fn=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_limits_parallel_queries_when_capacity_is_configured(monkeypatch):
    # Arrange
    monkeypatch.setenv("SESSION_MAX_CONCURRENT_QUERIES", "3")
    SessionQueryEngine._query_semaphore = None
    engine = _engine()
    active = 0
    peak_active = 0

    async def run_query(_command):
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0.02)
        active -= 1

    engine.run_claude_query = run_query
    commands = [SimpleNamespace(session_id=f"session-{index}") for index in range(9)]

    # Act
    await asyncio.gather(*(engine.submit_query(command) for command in commands))

    # Assert
    assert peak_active == 3


def test_uses_safe_default_when_capacity_is_invalid(monkeypatch):
    # Arrange
    monkeypatch.setenv("SESSION_MAX_CONCURRENT_QUERIES", "invalid")

    # Act
    capacity = SessionQueryEngine._configured_query_capacity()

    # Assert
    assert capacity == 8
