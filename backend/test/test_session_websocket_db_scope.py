from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from infr.config import database
from ohs import dependencies
from ohs.ws.session_ws import router


class _AsyncSessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        return False


def _session_websocket_route():
    return next(route for route in router.routes if route.path == "/ws/{session_id}")


@pytest.mark.asyncio
async def test_commits_and_closes_websocket_db_scope_when_action_succeeds(monkeypatch) -> None:
    # Arrange
    db_session = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    service = SimpleNamespace(close=AsyncMock())
    factory = Mock(return_value=_AsyncSessionContext(db_session))
    create_service = AsyncMock(return_value=service)
    monkeypatch.setattr(database, "async_session_factory", factory)
    monkeypatch.setattr(dependencies, "_create_session_service", create_service)

    # Act
    async with dependencies._session_websocket_service_context() as (scoped_service, _):
        assert scoped_service is service

    # Assert
    db_session.commit.assert_awaited_once()
    db_session.rollback.assert_not_awaited()
    service.close.assert_awaited_once()
    create_service.assert_awaited_once_with(db_session)


@pytest.mark.asyncio
async def test_rolls_back_and_closes_websocket_db_scope_when_action_fails(monkeypatch) -> None:
    # Arrange
    db_session = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    service = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(
        database,
        "async_session_factory",
        Mock(return_value=_AsyncSessionContext(db_session)),
    )
    monkeypatch.setattr(
        dependencies,
        "_create_session_service",
        AsyncMock(return_value=service),
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match="action failed"):
        async with dependencies._session_websocket_service_context():
            raise RuntimeError("action failed")

    db_session.commit.assert_not_awaited()
    db_session.rollback.assert_awaited_once()
    service.close.assert_awaited_once()


def test_websocket_route_uses_managed_scope_instead_of_request_session() -> None:
    # Arrange
    route = _session_websocket_route()
    dependency_names = {dependency.call.__name__ for dependency in route.dependant.dependencies}
    request_scoped_service_dependencies = {
        "get_session_application_service",
        "get_attachment_application_service",
        "get_team_board_service",
    }

    # Act / Assert
    assert dependency_names.isdisjoint(request_scoped_service_dependencies)
    assert "get_create_session_websocket_service_context_factory" in dependency_names
