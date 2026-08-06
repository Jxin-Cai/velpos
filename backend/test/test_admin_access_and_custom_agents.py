from __future__ import annotations

import hashlib
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from application.agent.agent_application_service import AgentApplicationService
from application.auth.auth_application_service import AuthApplicationService
from domain.agent.model.agent_template import AgentTemplate
from domain.project.model.project import Project
from domain.shared.business_exception import BusinessException
from domain.user.model.user import User, UserRole
from infr.client.claude_plugin_manager import ClaudePluginManager
from ohs.http.admin_plugin_router import AddMarketplaceRequest
from ohs.ws import session_ws


def _custom_template() -> AgentTemplate:
    return AgentTemplate.create(
        id="custom-agent-id",
        name_en="Custom reviewer",
        name_zh="自定义审查员",
        description_en="Reviews changes",
        description_zh="审查变更",
        category="custom",
        emoji="🔎",
        color="#123456",
        prompt_en="Review the code carefully.",
        prompt_zh="仔细审查代码。",
        created_by=1,
        plugins_config=None,
    )


@pytest.mark.asyncio
async def test_applies_database_prompt_when_custom_agent_is_loaded() -> None:
    # Arrange
    template_repository = SimpleNamespace(
        find_by_id=AsyncMock(return_value=_custom_template()),
    )
    revision = SimpleNamespace(
        id="revision-id",
        base_revision_id="base-id",
        base_file_hash="file-hash",
    )
    revision_service = SimpleNamespace(
        create_draft=AsyncMock(return_value=revision),
        propose=AsyncMock(return_value=revision),
        approve=AsyncMock(return_value=revision),
        apply=AsyncMock(return_value=SimpleNamespace(conflict=False)),
    )
    project = Project.reconstitute(
        id="project-id",
        name="Project",
        dir_path="/tmp/project",
        agents={},
    )
    project_repository = SimpleNamespace(
        find_by_id=AsyncMock(return_value=project),
        save=AsyncMock(),
    )
    service = AgentApplicationService(
        claude_md_revision_service=revision_service,
        agent_template_repository=template_repository,
    )

    # Act
    loaded = await service.load_agent(
        "project-id",
        "custom-agent-id",
        "zh",
        project_repository,
    )

    # Assert
    assert loaded.get_current_agent() == {"id": "custom-agent-id", "language": "zh"}
    revision_service.create_draft.assert_awaited_once_with(
        project_dir="/tmp/project",
        content="仔细审查代码。",
        created_by="agent",
    )


@pytest.mark.asyncio
async def test_rejects_login_when_account_is_disabled() -> None:
    # Arrange
    repository = SimpleNamespace()
    service = AuthApplicationService(
        repository,
        jwt_secret="test-secret-for-password-hashing",
        jwt_expire_minutes=60,
        mode="pro",
    )
    user = User.reconstitute(
        id=2,
        username="disabled",
        display_name="Disabled",
        role=UserRole.MEMBER,
        hashed_password=service._hash_password("password"),
        created_at=datetime.now(),
        is_active=False,
    )
    repository.find_by_username = AsyncMock(return_value=user)

    # Act
    with pytest.raises(BusinessException) as exc_info:
        await service.login("disabled", "password")

    # Assert
    assert exc_info.value.code == "ACCOUNT_DISABLED"


@pytest.mark.asyncio
async def test_upgrades_password_hash_when_legacy_user_logs_in() -> None:
    # Arrange
    jwt_secret = "test-secret-for-password-hashing"
    password = "password"
    legacy_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        jwt_secret[:16].encode(),
        100_000,
    ).hex()
    user = User.reconstitute(
        id=2,
        username="legacy-user",
        display_name="Legacy User",
        role=UserRole.MEMBER,
        hashed_password=legacy_hash,
        created_at=datetime.now(),
    )
    repository = SimpleNamespace(
        find_by_username=AsyncMock(return_value=user),
        save=AsyncMock(return_value=user),
    )
    service = AuthApplicationService(
        repository,
        jwt_secret=jwt_secret,
        jwt_expire_minutes=60,
        mode="pro",
    )

    # Act
    logged_in_user, _ = await service.login("legacy-user", password)

    # Assert
    assert logged_in_user.hashed_password.startswith("$2b$")
    repository.save.assert_awaited_once_with(logged_in_user)


@pytest.mark.asyncio
async def test_rejects_terminal_websocket_when_user_is_not_admin(monkeypatch) -> None:
    # Arrange
    member = User.reconstitute(
        id=2,
        username="member",
        display_name="Member",
        role=UserRole.MEMBER,
        hashed_password="hash",
        created_at=datetime.now(),
    )
    monkeypatch.setattr(
        session_ws,
        "authenticate_websocket_user",
        AsyncMock(return_value=member),
    )
    websocket = SimpleNamespace(close=AsyncMock(), accept=AsyncMock())
    terminal_service = SimpleNamespace(create_pty=AsyncMock())

    # Act
    await session_ws.terminal_websocket_endpoint(websocket, terminal_service)

    # Assert
    websocket.close.assert_awaited_once_with(code=4003)
    terminal_service.create_pty.assert_not_awaited()


@pytest.mark.asyncio
async def test_passes_token_through_process_environment_when_private_marketplace_is_added(
    monkeypatch,
) -> None:
    # Arrange
    manager = object.__new__(ClaudePluginManager)
    captured: dict[str, object] = {}

    async def capture_cli(
        args: list[str],
        cwd: str,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        captured.update(args=args, cwd=cwd, extra_env=extra_env)
        return "OK"

    monkeypatch.setattr(manager, "_run_cli", capture_cli)

    # Act
    await manager.add_marketplace("https://git.example.com/team/plugins.git", "secret-token")

    # Assert
    assert captured["extra_env"]["GIT_CONFIG_VALUE_0"] == "Authorization: Bearer secret-token"
    assert "secret-token" not in captured["args"]


@pytest.mark.asyncio
async def test_returns_selected_marketplace_plugins_when_multiple_markets_are_cached(
    monkeypatch,
) -> None:
    # Arrange
    manager = object.__new__(ClaudePluginManager)
    monkeypatch.setattr(
        manager,
        "_read_available_plugins",
        lambda: [
            {"name": "reviewer", "marketplace": "team-market"},
            {"name": "designer", "marketplace": "other-market"},
        ],
    )

    # Act
    plugins = await manager.list_marketplace_plugins("team-market")

    # Assert
    assert plugins == [{"name": "reviewer", "marketplace": "team-market"}]


@pytest.mark.asyncio
async def test_passes_token_through_process_environment_when_private_marketplace_is_refreshed(
    monkeypatch,
) -> None:
    # Arrange
    manager = object.__new__(ClaudePluginManager)
    captured: dict[str, object] = {}

    async def capture_cli(
        args: list[str],
        cwd: str,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        captured.update(args=args, cwd=cwd, extra_env=extra_env)
        return "OK"

    monkeypatch.setattr(manager, "_run_cli", capture_cli)

    # Act
    await manager.update_marketplace("private-market", "refresh-token")

    # Assert
    assert captured["extra_env"] == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": "Authorization: Bearer refresh-token",
    }


def test_rejects_embedded_credentials_when_marketplace_source_contains_user_info() -> None:
    # Arrange
    source = "https://secret-token@git.example.com/team/plugins.git"

    # Act
    with pytest.raises(ValidationError):
        AddMarketplaceRequest(source=source)

    # Assert is performed by the exception context.
