import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.command.create_session_command import CreateSessionCommand
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


@pytest.mark.asyncio
async def test_skips_connection_prewarm_when_disabled_by_default(monkeypatch) -> None:
    # Arrange
    monkeypatch.delenv("CLAUDE_PREWARM_CONNECTIONS", raising=False)
    session = Mock(sdk_session_id="sdk-session")
    gateway = SimpleNamespace(
        is_connected=Mock(return_value=False),
        open_connection=AsyncMock(),
        schedule_idle_disconnect=Mock(),
    )
    service = _create_service(session, gateway)

    # Act
    await service.prewarm_connection("session-1")

    # Assert
    gateway.open_connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedules_idle_cleanup_when_connection_is_prewarmed(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    monkeypatch.setenv("CLAUDE_PREWARM_CONNECTIONS", "true")
    session = Mock(
        sdk_session_id="sdk-session",
        project_dir=str(tmp_path),
        model="test-model",
    )
    gateway = SimpleNamespace(
        is_connected=Mock(return_value=False),
        open_connection=AsyncMock(),
        schedule_idle_disconnect=Mock(),
    )
    service = _create_service(session, gateway)
    service._resolve_resume_sdk_session_id = AsyncMock(return_value="sdk-session")

    # Act
    await service.prewarm_connection("session-1")

    # Assert
    gateway.schedule_idle_disconnect.assert_called_once_with("session-1")


@pytest.mark.asyncio
async def test_keeps_context_empty_when_session_has_no_messages() -> None:
    # Arrange
    session = Mock(session_id="session-1", messages=[])
    gateway = SimpleNamespace(get_context_usage=AsyncMock(return_value={"total_tokens": 4096}))
    service = _create_service(session, gateway)

    # Act
    refreshed = await service._refresh_context_usage(session)

    # Assert
    assert refreshed is False
    gateway.get_context_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_send_hidden_query_when_session_is_created(tmp_path) -> None:
    # Arrange
    gateway = SimpleNamespace(
        set_permission_mode=AsyncMock(),
        open_fresh_connection=AsyncMock(),
        send_query=Mock(),
    )
    service = _create_service(Mock(), gateway)
    service._project_repository = None
    command = CreateSessionCommand(
        model="test-model",
        project_dir=str(tmp_path),
    )

    # Act
    await service.create_session(command)

    # Assert
    gateway.send_query.assert_not_called()


@pytest.mark.asyncio
async def test_creates_session_workspace_under_user_agents_when_project_is_missing(
    tmp_path,
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setenv("PROJECTS_ROOT_DIR", str(tmp_path / "velpos"))
    gateway = SimpleNamespace(
        set_permission_mode=AsyncMock(),
        open_fresh_connection=AsyncMock(),
    )
    service = _create_service(Mock(), gateway)
    service._project_repository = None
    command = CreateSessionCommand(
        model="test-model",
        name="scratch",
        user_id=42,
    )

    # Act
    session = await service.create_session(command)

    # Assert
    assert session.project_dir == str(tmp_path / "velpos" / "42" / "agents" / "scratch")


@pytest.mark.asyncio
async def test_invokes_delete_session_files_via_to_thread_when_project_dir_exists(
    monkeypatch,
) -> None:
    # Arrange
    delete_calls: list = []
    to_thread_funcs: list = []

    def sync_delete(sid, pdir, *, sdk_session_id):
        delete_calls.append((sid, pdir, sdk_session_id))

    async def fake_to_thread(func, *args, **kwargs):
        to_thread_funcs.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    session = Mock(
        session_id="session-1",
        project_dir="/some/project",
        sdk_session_id="sdk-abc",
    )
    gateway = SimpleNamespace(
        disconnect=AsyncMock(),
        cleanup_session=AsyncMock(),
        delete_session_files=sync_delete,
    )
    service = SessionApplicationService.__new__(SessionApplicationService)
    service._session_repository = SimpleNamespace(
        find_by_id=AsyncMock(return_value=session),
        remove=AsyncMock(return_value=True),
        commit=AsyncMock(),
    )
    service._claude_agent_gateway = gateway
    service._im_unbind_fn = None
    service._trace_collector = None
    service._query_engine = SimpleNamespace(cleanup_session_state=AsyncMock())

    # Act
    await service.delete_session("session-1")

    # Assert
    assert sync_delete in to_thread_funcs, (
        "delete_session_files was not dispatched via asyncio.to_thread"
    )
    assert delete_calls == [("session-1", "/some/project", "sdk-abc")]
