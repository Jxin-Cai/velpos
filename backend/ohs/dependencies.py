from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncContextManager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from application.agent.agent_application_service import AgentApplicationService
from application.agent.agent_template_application_service import AgentTemplateApplicationService
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
from application.im_binding.im_channel_facade import ImChannelFacade
from application.message.attachment_application_service import AttachmentApplicationService
from application.evolution.evolution_application_service import EvolutionApplicationService
from application.memory.claude_md_revision_application_service import ClaudeMdRevisionApplicationService
from application.memory.memory_file_application_service import MemoryFileApplicationService
from application.memory.project_memory_application_service import ProjectMemoryApplicationService
from application.memory.rule_file_application_service import RuleFileApplicationService
from application.market.mcp_market_application_service import McpMarketApplicationService
from application.market.skill_market_application_service import SkillMarketApplicationService
from application.plugin.plugin_application_service import PluginApplicationService
from application.project.plugin_init_application_service import PluginInitApplicationService
from application.project.project_application_service import ProjectApplicationService
from application.project.workspace_application_service import WorkspaceApplicationService
from application.scheduler.scheduler_application_service import SchedulerApplicationService
from application.session.session_application_service import SessionApplicationService
from application.session.session_branch_application_service import SessionBranchApplicationService
from application.session.session_run_timeline_service import SessionRunTimelineService
from application.session.session_timeline_event_service import SessionTimelineEventService
from application.settings.settings_application_service import SettingsApplicationService
from application.terminal.terminal_application_service import TerminalApplicationService
from application.usage.usage_governance_application_service import UsageGovernanceApplicationService
from infr.client.claude_agent_gateway import ClaudeAgentGateway
from infr.client.claude_command_gateway import ClaudeCommandGateway
from infr.client.claude_plugin_manager import ClaudePluginManager
from infr.client.claude_session_manager import ClaudeSessionManagerImpl
from infr.client.connection_manager import ConnectionManager
from infr.client.settings_file_service import SettingsFileService
from infr.client.terminal_executor import TerminalExecutor
from infr.config.database import get_async_session
from infr.config.im_config import ImConfig
from infr.im.builtin_channels import register_builtin_channels
from infr.im.channel_provider import ChannelBuildContext
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
from infr.repository.session_timeline_event_repository_impl import SessionTimelineEventRepositoryImpl
from infr.repository.session_execution_lock import acquire_session_execution_lock
from infr.repository.session_snapshot_repository_impl import SessionSnapshotRepositoryImpl
from infr.repository.usage_governance_repository_impl import UsageGovernanceRepositoryImpl
from infr.storage.attachment_storage_gateway import AttachmentStorageGateway
from infr.workspace.workspace_root_resolver_impl import WorkspaceRootResolverImpl
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_type import ImChannelType
from ohs.session_event_coordinator import SessionEventCoordinator
from ohs.im_delivery_coordinator import ImDeliveryCoordinator
from ohs.im_delivery_monitor import ImDeliveryMonitor

logger = logging.getLogger(__name__)

_workspace_root_resolver = WorkspaceRootResolverImpl()
_connection_manager = ConnectionManager()
_claude_agent_gateway = ClaudeAgentGateway()
_claude_plugin_manager = ClaudePluginManager()
_claude_command_gateway = ClaudeCommandGateway()
_claude_session_manager = ClaudeSessionManagerImpl()
_settings_file_service = SettingsFileService()
_terminal_executor = TerminalExecutor()

_im_config = ImConfig()

# ── IM Channel Registry ──
# 渠道装配细节全部封装在各渠道包的 provider 中; 新增渠道只需要在
# infr/im/builtin_channels.py 的清单里追加一行, 组合根保持不变。
_im_channel_registry = ImChannelRegistry()
register_builtin_channels(
    _im_channel_registry,
    ChannelBuildContext(im_config=_im_config),
)

_im_channel_facade = ImChannelFacade(_im_channel_registry)
_im_delivery_coordinator = ImDeliveryCoordinator(
    _im_channel_registry,
    broadcast_fn=_connection_manager.broadcast,
)
_im_delivery_monitor = ImDeliveryMonitor(
    wake_inbox=_im_delivery_coordinator.wake_inbox,
    wake_outbox=_im_delivery_coordinator.wake_outbox,
)


#: 允许从渠道临时目录搬进会话工作区的附件来源.
#: 渠道适配器下载入站媒体时会把自己的 channel_type 写进 ``source``;
#: ``feishu`` 是飞书品牌下的历史别名, 一并接受。
_IM_ATTACHMENT_SOURCES: frozenset[str] = frozenset(
    {channel.value for channel in ImChannelType} | {"feishu"}
)


async def _stage_inbound_attachments(
    session: Any,
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    project_dir = str(getattr(session, "project_dir", "") or "")
    if not project_dir:
        return attachments

    project_root = Path(project_dir).resolve()
    storage = AttachmentStorageGateway()

    def stage() -> list[dict[str, Any]]:
        staged: list[dict[str, Any]] = []
        for attachment in attachments:
            item = dict(attachment)
            raw_path = str(item.get("path") or "")
            if not raw_path:
                staged.append(item)
                continue

            source = Path(raw_path).expanduser().resolve()
            if source == project_root or project_root in source.parents:
                item["path"] = source.relative_to(project_root).as_posix()
                staged.append(item)
                continue

            if str(item.get("source") or "").lower() not in _IM_ATTACHMENT_SOURCES:
                staged.append(item)
                continue

            filename = str(
                item.get("filename")
                or item.get("name")
                or source.name
                or "attachment.bin"
            )
            stored_path, digest = storage.stage_file(
                project_dir,
                session.session_id,
                filename,
                str(source),
            )
            item.update(
                {
                    "filename": filename,
                    "path": Path(stored_path).relative_to(project_root).as_posix(),
                    "sha256": str(item.get("sha256") or digest),
                }
            )
            staged.append(item)
        return staged

    return await asyncio.to_thread(stage)

# ── Session Event Coordinator (broadcast, IM sync, audit, timeline, usage) ──
_session_coordinator = SessionEventCoordinator(
    connection_manager=_connection_manager,
    im_channel_registry=_im_channel_registry,
    enqueue_im_fn=_im_delivery_coordinator.enqueue_outbound,
)
_claude_agent_gateway.set_broadcast_fn(_session_coordinator.broadcast_with_im)
_claude_agent_gateway.set_is_im_bound_fn(_session_coordinator.is_session_im_bound)
_claude_agent_gateway.set_persist_pending_request_context_fn(_session_coordinator.persist_pending_request_context)
_connection_manager.register_broadcast_hook(_session_coordinator.timeline_broadcast_hook)


# ── Trace Collector (observability spans) ──
from application.session.trace_collector import TraceCollector
from infr.repository.execution_ledger_event_repository_impl import ExecutionLedgerEventRepositoryImpl
from infr.repository.trace_span_repository_impl import TraceSpanRepositoryImpl


@asynccontextmanager
async def _trace_persistence_scope():
    from infr.config.database import async_session_factory
    async with async_session_factory() as db_session:
        yield (
            TraceSpanRepositoryImpl(db_session),
            ExecutionLedgerEventRepositoryImpl(db_session),
        )


def _create_trace_collector() -> TraceCollector:
    return TraceCollector(
        persistence_factory=_trace_persistence_scope,
        broadcast_fn=_connection_manager.broadcast,
    )


_trace_collector = _create_trace_collector()


async def _im_bind_for_session(session_id: str, channel_id: str) -> dict:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        svc = ImChannelApplicationService(
            registry=_im_channel_registry,
            binding_repo=ImBindingRepositoryImpl(db_session),
            init_repo=ChannelInitRepositoryImpl(db_session),
            session_service_factory=_create_session_service,
            connection_manager=_connection_manager,
            accept_inbound_fn=_im_delivery_coordinator.accept_inbound,
            enqueue_outbound_fn=_im_delivery_coordinator.enqueue_outbound,
            stage_inbound_attachments_fn=_stage_inbound_attachments,
            commit_unit_of_work=db_session.commit,
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
                commit_unit_of_work=db_session.commit,
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


async def _cleanup_branch_group(group_id: str) -> None:
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        repo = SessionBranchRepositoryImpl(db_session)
        await repo.remove_by_group_id(group_id)
        await db_session.commit()


async def get_session_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SessionApplicationService:
    return await _create_session_service(db_session)


async def get_session_branch_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SessionBranchApplicationService:
    return SessionBranchApplicationService(
        session_repository=SessionRepositoryImpl(db_session),
        branch_repository=SessionBranchRepositoryImpl(db_session),
        snapshot_repository=SessionSnapshotRepositoryImpl(db_session),
        delete_session_fn=_delete_session_for_branch,
        session_service_factory=_create_session_service,
        connection_manager=_connection_manager,
        cleanup_branch_group_fn=_cleanup_branch_group,
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
        notify_im_fn=_session_coordinator.on_assistant_response,
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
        claude_agent_gateway=_claude_agent_gateway,
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


def get_im_channel_facade() -> ImChannelFacade:
    return _im_channel_facade


def get_im_delivery_coordinator() -> ImDeliveryCoordinator:
    return _im_delivery_coordinator


def get_im_delivery_monitor() -> ImDeliveryMonitor:
    return _im_delivery_monitor


def get_session_event_coordinator() -> SessionEventCoordinator:
    return _session_coordinator


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
        accept_inbound_fn=_im_delivery_coordinator.accept_inbound,
        enqueue_outbound_fn=_im_delivery_coordinator.enqueue_outbound,
        stage_inbound_attachments_fn=_stage_inbound_attachments,
        session_service_context_factory=_session_service_context,
        binding_context_factory=_binding_repos_context,
        commit_unit_of_work=db_session.commit,
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
        on_assistant_response=_session_coordinator.on_assistant_response,
        on_user_message=_session_coordinator.on_user_message,
        on_query_finished=_im_delivery_coordinator.release_deferred_inbox,
        project_repository=ProjectRepositoryImpl(db_session),
        im_unbind_fn=_im_unbind_for_session,
        audit_event_repository=SessionAuditEventRepositoryImpl(db_session),
        audit_event_recorder=_session_coordinator.record_audit_event,
        usage_recorder=_session_coordinator.record_usage_ledger,
        timeline_service=SessionRunTimelineService(
            repository=SessionRunStepRepositoryImpl(db_session),
            connection_manager=_connection_manager,
        ),
        timeline_event_service=SessionTimelineEventService(
            repository=SessionTimelineEventRepositoryImpl(db_session),
            connection_manager=_connection_manager,
        ),
        trace_collector=_trace_collector,
        session_service_factory=_create_session_service,
        execution_lock_factory=acquire_session_execution_lock,
    )


@asynccontextmanager
async def _session_websocket_service_context() -> AsyncIterator[
    tuple[SessionApplicationService, AttachmentApplicationService]
]:
    """Provide short-lived DB-backed services for one WebSocket operation.

    FastAPI yield dependencies stay alive until a WebSocket disconnects.  A
    session obtained through that dependency therefore retains its first
    checked-out connection for the entire lifetime of a long-lived socket.
    WebSocket handlers use this context once for the initial snapshot and once
    per action instead, so every transaction returns its connection to the
    pool while the socket is idle.
    """
    from infr.config.database import async_session_factory

    async with async_session_factory() as db_session:
        service = await _create_session_service(db_session)
        attachment_service = AttachmentApplicationService(
            attachment_repository=AttachmentRepositoryImpl(db_session),
            project_repository=ProjectRepositoryImpl(db_session),
            storage_gateway=AttachmentStorageGateway(),
        )
        try:
            yield service, attachment_service
            # AttachmentApplicationService deliberately flushes attachment
            # records; commit the operation scope so the record is durable.
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise
        finally:
            # SessionApplicationService may replace its repository session
            # after a transient connection failure.  Closing the service here
            # covers both the original and any replacement AsyncSession.
            await service.close()


def get_create_session_websocket_service_context_factory() -> Callable[
    [], AsyncContextManager[tuple[SessionApplicationService, AttachmentApplicationService]]
]:
    """Return the managed service-scope factory used by session WebSockets."""
    return _session_websocket_service_context


@asynccontextmanager
async def _session_service_context():
    """Provide a SessionApplicationService with its own managed DB session."""
    from infr.config.database import async_session_factory
    async with async_session_factory() as db_session:
        svc = await _create_session_service(db_session)
        yield svc


@asynccontextmanager
async def _binding_repos_context():
    """Provide (ImBindingRepository, ChannelInitRepository) with their own managed DB session."""
    from infr.config.database import async_session_factory
    async with async_session_factory() as db_session:
        yield ImBindingRepositoryImpl(db_session), ChannelInitRepositoryImpl(db_session)
        await db_session.commit()


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
    revision_service = _create_revision_service(db_session)
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
    return _create_revision_service(db_session)


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
        workspace_root_resolver=_workspace_root_resolver,
    )


async def get_workspace_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> WorkspaceApplicationService:
    project_repo = ProjectRepositoryImpl(db_session)
    return WorkspaceApplicationService(
        project_repository=project_repo,
    )


async def get_plugin_init_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> PluginInitApplicationService:
    project_repo = ProjectRepositoryImpl(db_session)
    return PluginInitApplicationService(
        project_repository=project_repo,
        session_service_factory=_create_session_service,
    )


_git_application_service = GitApplicationService()
_memory_file_application_service = MemoryFileApplicationService()
_rule_file_application_service = RuleFileApplicationService()


def _create_revision_service(db_session: AsyncSession) -> ClaudeMdRevisionApplicationService:
    return ClaudeMdRevisionApplicationService(
        revision_repository=ClaudeMdRevisionRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
    )


def get_git_application_service() -> GitApplicationService:
    return _git_application_service


def get_memory_file_application_service() -> MemoryFileApplicationService:
    return _memory_file_application_service


def get_rule_file_application_service() -> RuleFileApplicationService:
    return _rule_file_application_service


async def get_agent_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> AgentApplicationService:
    from infr.client.agent_asset_installer_impl import FilesystemAgentAssetInstaller
    from infr.repository.agent_template_repository_impl import AgentTemplateRepositoryImpl
    from infr.repository.mcp_server_entry_repository_impl import McpServerEntryRepositoryImpl
    from infr.repository.skill_entry_repository_impl import SkillEntryRepositoryImpl
    revision_service = _create_revision_service(db_session)
    return AgentApplicationService(
        plugin_manager=_claude_plugin_manager,
        claude_md_revision_service=revision_service,
        agent_template_repository=AgentTemplateRepositoryImpl(db_session),
        mcp_entry_repository=McpServerEntryRepositoryImpl(db_session),
        skill_entry_repository=SkillEntryRepositoryImpl(db_session),
        asset_installer=FilesystemAgentAssetInstaller(),
    )


async def get_project_repository(
    db_session: AsyncSession = Depends(get_async_session),
) -> ProjectRepositoryImpl:
    return ProjectRepositoryImpl(db_session)



def get_trace_collector() -> TraceCollector:
    return _trace_collector


async def get_trace_span_repository(
    db_session: AsyncSession = Depends(get_async_session),
) -> TraceSpanRepositoryImpl:
    return TraceSpanRepositoryImpl(db_session)


async def get_execution_ledger_event_repository(
    db_session: AsyncSession = Depends(get_async_session),
) -> ExecutionLedgerEventRepositoryImpl:
    return ExecutionLedgerEventRepositoryImpl(db_session)


async def get_llm_request_query_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> "LlmRequestQueryService":
    from application.session.llm_request_query_service import LlmRequestQueryService

    return LlmRequestQueryService(ExecutionLedgerEventRepositoryImpl(db_session))


async def get_execution_trace_query_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> "ExecutionTraceQueryService":
    from application.session.execution_trace_query_service import ExecutionTraceQueryService
    from infr.client.transcript_reader import ClaudeTranscriptReader

    return ExecutionTraceQueryService(
        session_repository=SessionRepositoryImpl(db_session),
        project_repository=ProjectRepositoryImpl(db_session),
        trace_span_repository=TraceSpanRepositoryImpl(db_session),
        transcript_reader=ClaudeTranscriptReader(),
    )


def get_workspace_root_resolver() -> WorkspaceRootResolverImpl:
    return _workspace_root_resolver


async def get_agent_template_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> AgentTemplateApplicationService:
    from infr.repository.agent_template_repository_impl import AgentTemplateRepositoryImpl
    return AgentTemplateApplicationService(AgentTemplateRepositoryImpl(db_session))


_mcp_marketplace_catalog = None
_skill_marketplace_catalog = None


def _get_mcp_marketplace_catalog():
    # Module-level singleton so the catalog's TTL cache survives across requests.
    global _mcp_marketplace_catalog
    if _mcp_marketplace_catalog is None:
        from infr.client.cline_mcp_catalog_impl import ClineMcpMarketplaceCatalog
        _mcp_marketplace_catalog = ClineMcpMarketplaceCatalog()
    return _mcp_marketplace_catalog


def _get_skill_marketplace_catalog():
    global _skill_marketplace_catalog
    if _skill_marketplace_catalog is None:
        from infr.client.skillsmp_catalog_impl import SkillsmpCatalog
        _skill_marketplace_catalog = SkillsmpCatalog()
    return _skill_marketplace_catalog


async def get_mcp_market_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> McpMarketApplicationService:
    from infr.repository.mcp_server_entry_repository_impl import McpServerEntryRepositoryImpl
    return McpMarketApplicationService(
        McpServerEntryRepositoryImpl(db_session),
        marketplace_catalog=_get_mcp_marketplace_catalog(),
    )


async def get_skill_market_application_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> SkillMarketApplicationService:
    from infr.repository.skill_entry_repository_impl import SkillEntryRepositoryImpl
    return SkillMarketApplicationService(
        SkillEntryRepositoryImpl(db_session),
        marketplace_catalog=_get_skill_marketplace_catalog(),
    )
