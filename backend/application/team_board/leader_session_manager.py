from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Awaitable, Callable

from application.session.command.create_session_command import CreateSessionCommand
from infr.client.claude_settings_env import resolve_default_model
from application.team_board.execution_dispatch import dispatch_execution_query
from application.team_board.team_workspace_helpers import ensure_agent_project
from domain.session.model.session_status import SessionStatus
from domain.shared.async_utils import KeyedLockPool, safe_create_task

if TYPE_CHECKING:
    from application.session.session_application_service import SessionApplicationService
    from domain.project.repository.project_repository import ProjectRepository
    from domain.session.model.session import Session
    from domain.team.model.agent_slot import AgentSlot
    from domain.team.model.team import Team
    from domain.team.repository.team_repository import TeamRepository

logger = logging.getLogger(__name__)

_DEFAULT_COMPACT_THRESHOLD_TOKENS = 150_000


def resolve_leader_api_base_url() -> str:
    """Return the loopback API URL injected into Leader coordination prompts."""
    raw_port = os.getenv(
        "VELPOS_PORT",
        os.getenv("SERVER_PORT", os.getenv("BACKEND_PORT", "8083")),
    )
    if not raw_port.isdigit() or not (1 <= int(raw_port) <= 65535):
        raise ValueError(
            f"Leader API port must be a decimal integer in 1..65535, got {raw_port!r}"
        )
    return f"http://localhost:{raw_port}"


class LeaderSessionManager:
    """Manages the Leader agent's persistent session lifecycle."""

    # Class-level pool shared by all instances in the process so that concurrent
    # calls from different cards targeting the same team are serialised.
    _team_lock_pool: KeyedLockPool = KeyedLockPool(max_size=200)

    def __init__(
        self,
        team_repo: TeamRepository,
        project_repo: ProjectRepository,
        session_service: SessionApplicationService,
        session_service_factory: Callable[[], Awaitable[SessionApplicationService]],
    ) -> None:
        self._team_repo = team_repo
        self._project_repo = project_repo
        self._session_service = session_service
        self._session_service_factory = session_service_factory

    # ── Public use cases ─────────────────────────────────────

    async def get_or_create_session(
        self,
        team: Team,
        leader_slot: AgentSlot,
    ) -> Session:
        """Return the Leader's persistent session, creating one if absent.

        Uses double-checked locking so that two cards simultaneously assigned
        to the same Leader cannot each create their own orphan session.
        """
        # Fast path: return without acquiring the lock when a session already
        # exists (the common case once the team is initialised).
        if team.leader_session_id:
            try:
                existing_session = await self._session_service.get_session(
                    team.leader_session_id
                )
                if existing_session.status is not SessionStatus.ERROR:
                    await self._restore_automation_permission(existing_session.session_id)
                    return existing_session
                logger.warning(
                    "[team=%s] Leader session %s is in ERROR state, creating new one",
                    team.id,
                    team.leader_session_id,
                )
            except Exception:
                logger.warning(
                    "[team=%s] Leader session %s not found, creating new one",
                    team.id,
                    team.leader_session_id,
                    exc_info=True,
                )

        # Slow path: serialise creation for this team.
        lock = await self._team_lock_pool.acquire(team.id)
        try:
            async with lock:
                # Re-read authoritative team state inside the lock so a second
                # concurrent caller sees the session created by the first.
                fresh_team = await self._team_repo.find_by_id(team.id)
                if fresh_team and fresh_team.leader_session_id:
                    try:
                        existing_session = await self._session_service.get_session(
                            fresh_team.leader_session_id
                        )
                        if existing_session.status is not SessionStatus.ERROR:
                            await self._restore_automation_permission(
                                existing_session.session_id
                            )
                            return existing_session
                        logger.warning(
                            "[team=%s] Leader session %s is still in ERROR state after re-read, "
                            "creating new one",
                            team.id,
                            fresh_team.leader_session_id,
                        )
                    except Exception:
                        logger.warning(
                            "[team=%s] Leader session %s not found after re-read, creating new one",
                            team.id,
                            fresh_team.leader_session_id,
                            exc_info=True,
                        )

                session = await self._create_leader_session(team, leader_slot)
                team.leader_session_id = session.session_id
                await self._team_repo.save(team)
                logger.info(
                    "[team=%s] Leader session created: %s",
                    team.id,
                    session.session_id,
                )
                return session
        finally:
            await self._team_lock_pool.unref(team.id)

    async def append_message(self, session_id: str, prompt: str) -> None:
        """Send a new query/message to the Leader's persistent session."""
        await dispatch_execution_query(self._session_service_factory, session_id, prompt)

    async def compact_if_needed(self, session_id: str) -> None:
        """Compact the Leader session if context exceeds the token threshold."""
        threshold = int(
            os.getenv("LEADER_COMPACT_THRESHOLD_TOKENS", str(_DEFAULT_COMPACT_THRESHOLD_TOKENS))
        )
        session = await self._session_service.get_session(session_id)
        if session.last_input_tokens >= threshold:
            logger.info(
                "[session=%s] Leader context (%d tokens) exceeds threshold (%d), compacting",
                session_id,
                session.last_input_tokens,
                threshold,
            )
            await self._session_service.compact_session(session_id)

    @staticmethod
    def build_coordination_context(team: Team) -> str:
        """Build authoritative runtime identifiers for every Leader request.

        Persistent SDK sessions can retain command text rendered before a backend
        port or team identifier changed. Repeating the current values in each
        assignment prevents stale session context from selecting an obsolete URL.
        """
        slot_lines = [
            (
                f"- slot_id=`{slot.id}`, name={slot.name}, role={slot.role}, "
                f"availability={slot.availability.value}, is_leader={slot.is_leader}"
            )
            for slot in team.agent_slots
        ]
        slots_section = "\n".join(slot_lines) if slot_lines else "- (no agents)"
        api_base_url = resolve_leader_api_base_url()
        return (
            "## 当前团队编排上下文（权威值）\n"
            f"- API Base URL: `{api_base_url}`\n"
            f"- Team ID: `{team.id}`\n"
            "- 以下值覆盖持久会话中缓存的旧端口、team 名称或 slot 信息。\n"
            "- Agent slots:\n"
            f"{slots_section}\n"
            "- 创建计划时直接使用上述 Team ID、卡片 ID 和非 Leader slot_id；"
            "无需先查询外部“团队协作服务”。"
        )

    # ── Private helpers ──────────────────────────────────────

    async def _create_leader_session(
        self,
        team: Team,
        leader_slot: AgentSlot,
    ) -> Session:
        agent_project = await ensure_agent_project(
            team.name,
            leader_slot,
            self._project_repo,
            team_project_id=team.project_id,
        )
        session_cmd = CreateSessionCommand(
            model=resolve_default_model(),
            project_id=agent_project.id,
            project_dir=leader_slot.workspace_ref,
            name=f"[{team.name}] Leader",
        )
        return await self._session_service.create_session(session_cmd)

    async def _inject_state_summary(self, session_id: str, prompt: str) -> None:
        try:
            await self.append_message(session_id, prompt)
        except Exception:
            logger.error(
                "[session=%s] Failed to inject team state summary into recovered Leader session",
                session_id,
                exc_info=True,
            )

    async def _restore_automation_permission(self, session_id: str) -> None:
        """Restore autonomous tool use lost when the backend process restarts."""
        await self._session_service.set_permission_mode(
            session_id,
            "bypassPermissions",
        )

    @staticmethod
    def _build_team_state_summary(team: Team) -> str:
        slot_lines: list[str] = []
        for slot in team.agent_slots:
            slot_lines.append(
                f"- {slot.name} (role={slot.role}, availability={slot.availability.value})"
            )
        slots_section = "\n".join(slot_lines) if slot_lines else "- (no agents)"
        return (
            "## Team State Recovery\n\n"
            f"Team: {team.name}\n"
            f"Team ID: {team.id}\n\n"
            "### Agent Slots\n"
            f"{slots_section}\n\n"
            "This is a recovered Leader session. The previous session encountered an error. "
            "Please continue coordinating team activities based on this state summary."
        )
