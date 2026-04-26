from __future__ import annotations

import asyncio
import logging

from domain.session.model.session_audit_event import SessionAuditEvent
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
from application.command_policy.command_policy_application_service import CommandPolicyApplicationService
from application.im_binding.im_channel_application_service import ImChannelApplicationService
from application.message.attachment_application_service import AttachmentApplicationService
from application.evolution.evolution_application_service import EvolutionApplicationService
from application.memory.claude_md_revision_application_service import ClaudeMdRevisionApplicationService
from application.memory.project_memory_application_service import ProjectMemoryApplicationService
from application.plugin.plugin_application_service import PluginApplicationService
from application.project.project_application_service import ProjectApplicationService
from application.scheduler.scheduler_application_service import SchedulerApplicationService
from application.session.session_application_service import SessionApplicationService
from application.session.session_branch_application_service import SessionBranchApplicationService
from application.session.session_run_timeline_service import SessionRunTimelineService
from application.settings.settings_application_service import SettingsApplicationService
from application.terminal.terminal_application_service import TerminalApplicationService
from application.usage.usage_governance_application_service import UsageGovernanceApplicationService
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
from infr.repository.attachment_repository_impl import AttachmentRepositoryImpl
from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl
from infr.repository.channel_profile_repository_impl import ChannelProfileRepositoryImpl
from infr.repository.claude_md_revision_repository_impl import ClaudeMdRevisionRepositoryImpl
from infr.repository.evolution_proposal_repository_impl import EvolutionProposalRepositoryImpl
from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
from infr.repository.project_command_policy_repository_impl import ProjectCommandPolicyRepositoryImpl
from infr.repository.project_memory_repository_impl import ProjectMemoryRepositoryImpl
from infr.repository.project_repository_impl import ProjectRepositoryImpl
from infr.repository.scheduled_task_repository_impl import ScheduledTaskRepositoryImpl
from infr.repository.session_audit_event_repository_impl import SessionAuditEventRepositoryImpl
from infr.repository.session_branch_repository_impl import SessionBranchRepositoryImpl
from infr.repository.session_repository_impl import SessionRepositoryImpl
from infr.repository.session_run_step_repository_impl import SessionRunStepRepositoryImpl
from infr.repository.session_snapshot_repository_impl import SessionSnapshotRepositoryImpl
from infr.repository.usage_governance_repository_impl import UsageGovernanceRepositoryImpl
from infr.storage.attachment_storage_gateway import AttachmentStorageGateway
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.binding_status import BindingStatus

logger = logging.getLogger(__name__)

_connection_manager = ConnectionManager()
_claude_agent_gateway = ClaudeAgentGateway()


async def _broadcast_with_im(session_id: str, data: dict) -> None:
    """Broadcast to WS clients and forward user_choice_request to IM."""
    await _connection_manager.broadcast(session_id, data)
    event = data.get("event")
    if event in {"permission_request", "user_choice_request"}:
        audit_type = "ask_user_question_requested" if event == "user_choice_request" else "permission_requested"
        try:
            await _record_session_audit_event(
                SessionAuditEvent.create(
                    session_id=session_id,
                    event_type=audit_type,
                    payload={"tool_name": data.get("tool_name", "")},
                )
            )
        except Exception:
            logger.warning("Failed to record pending request audit for session %s", session_id, exc_info=True)
    # Also sync user_choice_request to IM so IM users can see and answer
    if event == "user_choice_request":
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


async def _persist_pending_request_context(
    session_id: str,
    context: dict | None,
) -> None:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        repo = SessionRepositoryImpl(db_session)
        session = await repo.find_by_id(session_id)
        if session is None:
            return
        if context:
            session.update_pending_request_context(context)
        else:
            session.clear_pending_request_context()
        await repo.save(session)
        await db_session.commit()


_claude_agent_gateway.set_persist_pending_request_context_fn(_persist_pending_request_context)


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


async def _im_bind_for_session(session_id: str, channel_id: str) -> dict:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        svc = ImChannelApplicationService(
            registry=_im_channel_registry,
            binding_repo=ImBindingRepositoryImpl(db_session),
            init_repo=ChannelInitRepositoryImpl(db_session),
            session_service_factory=_create_session_service,
            connection_manager=_connection_manager,
        )
        result = await svc.bind(session_id, channel_id, {})
        await db_session.commit()
        return result


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


async def _save_scheduled_task_run(run) -> None:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        repo = ScheduledTaskRepositoryImpl(db_session)
        await repo.save_run(run)
        await db_session.commit()


async def _delete_session_for_branch(session_id: str) -> bool:
    service = await _create_session_service()
    try:
        return await service.delete_session(session_id)
    finally:
        await service.close()


async def _record_session_audit_event(event) -> None:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        repo = SessionAuditEventRepositoryImpl(db_session)
        await repo.save(event)
        await db_session.commit()


async def _record_usage_ledger(
    session_id: str,
    project_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> None:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        svc = UsageGovernanceApplicationService(
            repository=UsageGovernanceRepositoryImpl(db_session),
        )
        await svc.record_usage(
            session_id=session_id,
            project_id=project_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )
        await db_session.commit()


async def get_session_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SessionApplicationService:
    repository = SessionRepositoryImpl(db_session)
    project_repo = ProjectRepositoryImpl(db_session)
    audit_repo = SessionAuditEventRepositoryImpl(db_session)
    timeline_service = SessionRunTimelineService(
        repository=SessionRunStepRepositoryImpl(db_session),
        connection_manager=_connection_manager,
    )
    return SessionApplicationService(
        session_repository=repository,
        claude_agent_gateway=_claude_agent_gateway,
        connection_manager=_connection_manager,
        claude_session_manager=_claude_session_manager,
        on_assistant_response=_on_assistant_response,
        on_user_message=_on_user_message,
        project_repository=project_repo,
        im_unbind_fn=_im_unbind_for_session,
        audit_event_repository=audit_repo,
        audit_event_recorder=_record_session_audit_event,
        usage_recorder=_record_usage_ledger,
        timeline_service=timeline_service,
    )


async def get_session_branch_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SessionBranchApplicationService:
    return SessionBranchApplicationService(
        session_repository=SessionRepositoryImpl(db_session),
        branch_repository=SessionBranchRepositoryImpl(db_session),
        snapshot_repository=SessionSnapshotRepositoryImpl(db_session),
        delete_session_fn=_delete_session_for_branch,
    )


async def get_usage_governance_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> UsageGovernanceApplicationService:
    return UsageGovernanceApplicationService(
        repository=UsageGovernanceRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
    )


async def get_scheduler_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SchedulerApplicationService:
    return SchedulerApplicationService(
        repository=ScheduledTaskRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
        session_service_factory=_create_session_service,
        connection_manager=_connection_manager,
        notify_im_fn=_on_assistant_response,
        bind_im_fn=_im_bind_for_session,
        unbind_im_fn=_im_unbind_for_session,
        save_run_fn=_save_scheduled_task_run,
    )


def get_connection_manager() -> ConnectionManager:
    return _connection_manager


def get_plugin_application_service() -> PluginApplicationService:
    return PluginApplicationService(plugin_manager=_claude_plugin_manager)


def get_command_application_service() -> CommandApplicationService:
    return CommandApplicationService(command_gateway=_claude_command_gateway)


async def get_command_policy_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> CommandPolicyApplicationService:
    return CommandPolicyApplicationService(
        policy_repository=ProjectCommandPolicyRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
    )


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
        on_assistant_response=_on_assistant_response,
        on_user_message=_on_user_message,
        project_repository=ProjectRepositoryImpl(db_session),
        im_unbind_fn=_im_unbind_for_session,
        timeline_service=SessionRunTimelineService(
            repository=SessionRunStepRepositoryImpl(db_session),
            connection_manager=_connection_manager,
        ),
    )


async def get_session_run_timeline_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SessionRunTimelineService:
    return SessionRunTimelineService(
        repository=SessionRunStepRepositoryImpl(db_session),
        connection_manager=_connection_manager,
    )


async def get_evolution_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> EvolutionApplicationService:
    revision_service = ClaudeMdRevisionApplicationService(
        revision_repository=ClaudeMdRevisionRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
    )
    return EvolutionApplicationService(
        proposal_repository=EvolutionProposalRepositoryImpl(db_session),
        session_repository=SessionRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
        claude_md_revision_service=revision_service,
    )


async def get_attachment_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> AttachmentApplicationService:
    return AttachmentApplicationService(
        attachment_repository=AttachmentRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
        storage_gateway=AttachmentStorageGateway(),
    )


async def get_project_memory_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> ProjectMemoryApplicationService:
    return ProjectMemoryApplicationService(
        memory_repository=ProjectMemoryRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
    )


async def get_claude_md_revision_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> ClaudeMdRevisionApplicationService:
    return ClaudeMdRevisionApplicationService(
        revision_repository=ClaudeMdRevisionRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
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


async def get_agent_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> AgentApplicationService:
    revision_service = ClaudeMdRevisionApplicationService(
        revision_repository=ClaudeMdRevisionRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
    )
    return AgentApplicationService(
        plugin_manager=_claude_plugin_manager,
        claude_md_revision_service=revision_service,
    )


async def get_project_repository(
    db_session: AsyncSession = Depends(get_async_session),
) -> ProjectRepositoryImpl:
    return ProjectRepositoryImpl(db_session)
