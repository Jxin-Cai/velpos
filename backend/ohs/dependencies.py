from __future__ import annotations

import asyncio
import logging

from domain.shared.async_utils import safe_create_task

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from application.agent.agent_application_service import AgentApplicationService
from application.git.git_application_service import GitApplicationService
from application.channel_profile.channel_profile_application_service import (
    ChannelProfileApplicationService,
)
from application.claude_session.claude_session_application_service import (
    ClaudeSessionApplicationService,
)
from application.command.command_application_service import CommandApplicationService
from application.im_binding.im_channel_application_service import ImChannelApplicationService
from application.plugin.plugin_application_service import PluginApplicationService
from application.project.project_application_service import ProjectApplicationService
from application.session.session_application_service import SessionApplicationService
from application.settings.settings_application_service import SettingsApplicationService
from application.terminal.terminal_application_service import TerminalApplicationService
from infr.client.claude_agent_gateway import ClaudeAgentGateway
from infr.client.claude_command_gateway import ClaudeCommandGateway
from infr.client.claude_plugin_manager import ClaudePluginManager
from infr.client.claude_session_manager import ClaudeSessionManagerImpl
from infr.client.connection_manager import ConnectionManager
from infr.client.im_api_gateway import ImApiGateway
from infr.client.im_ws_client import ImWsClient
from infr.client.settings_file_service import SettingsFileService
from infr.client.terminal_executor import TerminalExecutor
from infr.config.database import get_async_session
from infr.config.im_config import ImConfig
from infr.im.lark.lark_adapter import LARK_CHANNEL_SPEC, LarkAdapter
from infr.im.openim.openim_adapter import OPENIM_CHANNEL_SPEC, OpenImAdapter, OpenImStubAdapter
from infr.im.qq.qq_adapter import QQ_CHANNEL_SPEC, QqAdapter
from infr.im.qq.qq_api import QqApiClient
from infr.im.qq.qq_ws_client import QqWsClient
from infr.im.weixin.weixin_adapter import WEIXIN_CHANNEL_SPEC, WeixinAdapter
from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl
from infr.repository.channel_profile_repository_impl import ChannelProfileRepositoryImpl
from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
from infr.repository.project_repository_impl import ProjectRepositoryImpl
from infr.repository.session_repository_impl import SessionRepositoryImpl
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.binding_status import BindingStatus

logger = logging.getLogger(__name__)

_connection_manager = ConnectionManager()
_claude_agent_gateway = ClaudeAgentGateway()


async def _broadcast_with_im(session_id: str, data: dict) -> None:
    """Broadcast to WS clients and forward user_choice_request to IM."""
    await _connection_manager.broadcast(session_id, data)
    # Also sync user_choice_request to IM so IM users can see and answer
    if data.get("event") == "user_choice_request":
        questions = data.get("questions", [])
        lines = ["[User Input Required]"]
        for i, q in enumerate(questions):
            lines.append(f"\n{q.get('question', '')}")
            for j, opt in enumerate(q.get("options", [])):
                label = opt.get("label", "")
                desc = opt.get("description", "")
                lines.append(f"  {j + 1}. {label}" + (f" - {desc}" if desc else ""))
        text = "\n".join(lines)
        safe_create_task(_on_assistant_response(session_id, text))


_claude_agent_gateway.set_broadcast_fn(_broadcast_with_im)
_claude_plugin_manager = ClaudePluginManager()
_claude_command_gateway = ClaudeCommandGateway()
_claude_session_manager = ClaudeSessionManagerImpl()
_settings_file_service = SettingsFileService()
_terminal_executor = TerminalExecutor()

_im_config = ImConfig()
_im_api_gateway: ImApiGateway | None = (
    ImApiGateway(config=_im_config) if _im_config.enabled else None
)
_im_ws_client: ImWsClient | None = (
    ImWsClient(config=_im_config) if _im_config.enabled else None
)

# ── IM Channel Registry ──
_im_channel_registry = ImChannelRegistry()

# Register OpenIM adapter (real adapter when config enabled, stub otherwise)
if _im_config.enabled and _im_api_gateway is not None and _im_ws_client is not None:
    _im_channel_registry.register(
        OPENIM_CHANNEL_SPEC,
        lambda: OpenImAdapter(im_gateway=_im_api_gateway, im_ws_gateway=_im_ws_client),
    )
else:
    _im_channel_registry.register(OPENIM_CHANNEL_SPEC, OpenImStubAdapter)

# Register Lark IM adapter (singleton — WS listener lives on this instance)
_lark_adapter = LarkAdapter()
_im_channel_registry.register(LARK_CHANNEL_SPEC, lambda: _lark_adapter)

# Register QQ adapter (server-managed with shared WS + API clients)
_qq_api_client = QqApiClient()
_qq_ws_client = QqWsClient(api_client=_qq_api_client)
_im_channel_registry.register(
    QQ_CHANNEL_SPEC,
    lambda: QqAdapter(ws_client=_qq_ws_client, api_client=_qq_api_client),
)

# Register WeChat adapter (singleton — manages per-channel poll loops internally)
_weixin_adapter = WeixinAdapter()
_im_channel_registry.register(WEIXIN_CHANNEL_SPEC, lambda: _weixin_adapter)


async def _is_session_im_bound(session_id: str) -> bool:
    """Check if a session has an active IM binding (for idle disconnect protection)."""
    from infr.config.database import async_session_factory

    try:
        async with async_session_factory() as db_session:
            repo = ImBindingRepositoryImpl(db_session)
            binding = await repo.find_by_session_id(session_id)
            return binding is not None and binding.binding_status == BindingStatus.BOUND
    except Exception:
        logger.warning("Failed to check IM binding for session %s", session_id, exc_info=True)
        return False


_claude_agent_gateway.set_is_im_bound_fn(_is_session_im_bound)


async def _on_assistant_response(session_id: str, content: str) -> None:
    """Forward assistant response to bound IM channel (outbound sync)."""
    from infr.config.database import async_session_factory

    last_err = None
    for attempt in range(3):
        try:
            async with async_session_factory() as db_session:
                svc = ImChannelApplicationService(
                    registry=_im_channel_registry,
                    binding_repo=ImBindingRepositoryImpl(db_session),
                    init_repo=ChannelInitRepositoryImpl(db_session),
                )
                await svc.sync_outbound(session_id, content)
                await db_session.commit()
            return
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))

    logger.warning(
        "Outbound IM sync failed for session %s after 3 attempts",
        session_id, exc_info=last_err,
    )
    await _connection_manager.broadcast(session_id, {
        "type": "error",
        "message": "IM message sync failed, the message may not have been delivered to the IM channel.",
    })


async def _on_user_message(session_id: str, content: str) -> None:
    """Forward user message from Web UI to bound IM channel (outbound sync)."""
    from infr.config.database import async_session_factory

    last_err = None
    for attempt in range(3):
        try:
            async with async_session_factory() as db_session:
                svc = ImChannelApplicationService(
                    registry=_im_channel_registry,
                    binding_repo=ImBindingRepositoryImpl(db_session),
                    init_repo=ChannelInitRepositoryImpl(db_session),
                )
                await svc.sync_outbound(session_id, f"[Web User]\n{content}")
                await db_session.commit()
            return
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))

    logger.warning(
        "User message IM sync failed for session %s after 3 attempts",
        session_id, exc_info=last_err,
    )
    await _connection_manager.broadcast(session_id, {
        "type": "error",
        "message": "IM message sync failed, your message may not have been delivered to the IM channel.",
    })


async def _im_unbind_for_session(session_id: str) -> None:
    """Best-effort IM unbind before session deletion."""
    from infr.config.database import async_session_factory

    try:
        async with async_session_factory() as db_session:
            svc = ImChannelApplicationService(
                registry=_im_channel_registry,
                binding_repo=ImBindingRepositoryImpl(db_session),
                init_repo=ChannelInitRepositoryImpl(db_session),
            )
            await svc.unbind(session_id)
            await db_session.commit()
    except Exception:
        logger.warning(
            "IM unbind failed for session %s", session_id, exc_info=True,
        )


async def get_session_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SessionApplicationService:
    repository = SessionRepositoryImpl(db_session)
    project_repo = ProjectRepositoryImpl(db_session)
    return SessionApplicationService(
        session_repository=repository,
        claude_agent_gateway=_claude_agent_gateway,
        connection_manager=_connection_manager,
        claude_session_manager=_claude_session_manager,
        on_assistant_response=_on_assistant_response,
        on_user_message=_on_user_message,
        project_repository=project_repo,
        im_unbind_fn=_im_unbind_for_session,
    )


def get_connection_manager() -> ConnectionManager:
    return _connection_manager


def get_plugin_application_service() -> PluginApplicationService:
    return PluginApplicationService(plugin_manager=_claude_plugin_manager)


def get_command_application_service() -> CommandApplicationService:
    return CommandApplicationService(command_gateway=_claude_command_gateway)


def get_claude_session_application_service() -> ClaudeSessionApplicationService:
    return ClaudeSessionApplicationService(session_manager=_claude_session_manager)


def get_im_config() -> ImConfig:
    return _im_config


async def get_channel_profile_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> ChannelProfileApplicationService:
    profile_repository = ChannelProfileRepositoryImpl(db_session)
    return ChannelProfileApplicationService(
        profile_repository=profile_repository,
        settings_file_gateway=_settings_file_service,
    )


def get_settings_application_service() -> SettingsApplicationService:
    return SettingsApplicationService(
        settings_file_gateway=_settings_file_service,
    )


def get_claude_agent_gateway() -> ClaudeAgentGateway:
    return _claude_agent_gateway


def get_terminal_application_service() -> TerminalApplicationService:
    return TerminalApplicationService(
        terminal_gateway=_terminal_executor,
    )


def get_im_channel_registry() -> ImChannelRegistry:
    return _im_channel_registry


def get_lark_adapter() -> LarkAdapter:
    return _lark_adapter


def get_weixin_adapter() -> WeixinAdapter:
    return _weixin_adapter


def get_qq_ws_client() -> QqWsClient:
    return _qq_ws_client


def get_im_api_gateway() -> ImApiGateway | None:
    return _im_api_gateway


def get_im_ws_client() -> ImWsClient | None:
    return _im_ws_client


def get_create_session_service_factory():
    return _create_session_service


async def get_im_channel_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> ImChannelApplicationService:
    binding_repo = ImBindingRepositoryImpl(db_session)
    init_repo = ChannelInitRepositoryImpl(db_session)
    return ImChannelApplicationService(
        registry=_im_channel_registry,
        binding_repo=binding_repo,
        init_repo=init_repo,
        session_service_factory=_create_session_service,
        connection_manager=_connection_manager,
        get_pending_request_context_fn=_claude_agent_gateway.get_pending_request_context,
        resolve_user_response_fn=_claude_agent_gateway.resolve_user_response,
    )


async def _create_session_service(
    db_session: AsyncSession | None = None,
) -> SessionApplicationService:
    """Create a SessionApplicationService.

    If *db_session* is provided it is reused (request-scoped lifecycle).
    Otherwise a new ``AsyncSession`` is created — the caller is responsible
    for committing and closing it via ``service._session_repository._session``.
    """
    if db_session is None:
        from infr.config.database import async_session_factory
        db_session = async_session_factory()
        logger.debug("_create_session_service: created standalone DB session (caller must manage lifecycle)")

    return SessionApplicationService(
        session_repository=SessionRepositoryImpl(db_session),
        claude_agent_gateway=_claude_agent_gateway,
        connection_manager=_connection_manager,
        claude_session_manager=_claude_session_manager,
        project_repository=ProjectRepositoryImpl(db_session),
        im_unbind_fn=_im_unbind_for_session,
    )


async def get_project_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> ProjectApplicationService:
    project_repo = ProjectRepositoryImpl(db_session)
    session_repo = SessionRepositoryImpl(db_session)
    return ProjectApplicationService(
        project_repository=project_repo,
        session_repository=session_repo,
        session_service_factory=_create_session_service,
        connection_manager=_connection_manager,
    )


_git_application_service = GitApplicationService()


def get_git_application_service() -> GitApplicationService:
    return _git_application_service


def get_agent_application_service() -> AgentApplicationService:
    return AgentApplicationService(plugin_manager=_claude_plugin_manager)


async def get_project_repository(
    db_session: AsyncSession = Depends(get_async_session),
) -> ProjectRepositoryImpl:
    return ProjectRepositoryImpl(db_session)
