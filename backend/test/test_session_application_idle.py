from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.session_application_service import SessionApplicationService


def _create_service(session: Mock, gateway: SimpleNamespace) -> SessionApplicationService:
    service = SessionApplicationService.__new__(SessionApplicationService)
    service._session_repository = SimpleNamespace(find_by_id=AsyncMock(return_value=session))
    service._claude_agent_gateway = gateway
    service._save_session = AsyncMock()
    service._trace_collector = None
    return service


def _create_running_session() -> Mock:
    return Mock(is_running=True, complete_query=Mock(), fail_query=Mock())


@pytest.mark.asyncio
async def test_keeps_query_running_when_process_alive_and_gateway_inactive() -> None:
    session = _create_running_session()
    gateway = SimpleNamespace(
        is_active=Mock(return_value=False),
        is_connected=Mock(return_value=True),
        is_process_alive=Mock(return_value=True),
    )
    service = _create_service(session, gateway)

    await service.ensure_session_idle("session-1")

    session.complete_query.assert_not_called()
    session.fail_query.assert_not_called()
    service._save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_keeps_query_running_when_waiting_for_permission() -> None:
    session = _create_running_session()
    gateway = SimpleNamespace(
        is_active=Mock(return_value=False),
        is_connected=Mock(return_value=True),
        is_process_alive=Mock(return_value=True),
        is_waiting_for_user_input=Mock(return_value=True),
    )
    service = _create_service(session, gateway)

    await service.ensure_session_idle("session-1")

    session.complete_query.assert_not_called()
    session.fail_query.assert_not_called()
    service._save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_fails_stale_running_query_when_process_dead_and_gateway_inactive() -> None:
    session = _create_running_session()
    gateway = SimpleNamespace(
        is_active=Mock(return_value=False),
        is_connected=Mock(return_value=True),
        is_process_alive=Mock(return_value=False),
    )
    service = _create_service(session, gateway)

    await service.ensure_session_idle("session-1")

    session.fail_query.assert_called_once_with()
    session.complete_query.assert_not_called()
    service._save_session.assert_awaited_once_with(session, commit=True)
