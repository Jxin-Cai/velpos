from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from domain.session.model.session import Session
from domain.team_task.model.team_task import TeamTask
from domain.team_task.model.team_task_status import TeamTaskStatus
from application.team_task.prompt_builder import build_worker_prompt
from application.team_task.team_hooks import create_worker_hooks, NotifyImFn
from application.team_task.trace_file_manager import TraceFileManager
from domain.shared.business_exception import BusinessException

if TYPE_CHECKING:
    from application.agent.agent_application_service import AgentApplicationService
    from domain.project.repository.project_repository import ProjectRepository
    from domain.session.repository.session_repository import SessionRepository
    from domain.team_task.repository.team_task_repository import TeamTaskRepository
    from infr.client.claude_agent_gateway import ClaudeAgentGateway
    from infr.client.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

WORKER_OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Concise summary of what was accomplished"},
            "files_changed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files created or modified",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Any issues, warnings, or concerns encountered",
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Suggested follow-up actions",
            },
        },
        "required": ["summary"],
    },
}


class TeamCoordinatorService:

    def __init__(
        self,
        project_repository: "ProjectRepository",
        session_repository: "SessionRepository",
        team_task_repository: "TeamTaskRepository",
        claude_agent_gateway: "ClaudeAgentGateway",
        connection_manager: "ConnectionManager",
        notify_im_fn: NotifyImFn | None = None,
        agent_application_service: "AgentApplicationService | None" = None,
    ) -> None:
        self._project_repo = project_repository
        self._session_repo = session_repository
        self._task_repo = team_task_repository
        self._gateway = claude_agent_gateway
        self._connection_manager = connection_manager
        self._notify_im_fn = notify_im_fn
        self._agent_service = agent_application_service

    async def dispatch_task(
        self,
        main_project_id: str,
        coordinator_session_id: str,
        target_role: str,
        prompt: str,
        context: str = "",
        parent_task_id: str = "",
        depth: int = 0,
        trace_id: str = "",
    ) -> str:
        """Dispatch a task to a team member. Blocks until the worker finishes."""
        project = await self._project_repo.find_by_id(main_project_id)
        if not project or project.project_type != "team":
            raise BusinessException(f"Project {main_project_id} is not a team project")

        config = project.team_config
        mode = config.get("mode", "delegation")

        member = self._find_member_by_role(config, target_role)
        if not member:
            raise BusinessException(f"No team member with role '{target_role}' found")

        target_project_id = member.get("project_id", "")
        target_project = await self._project_repo.find_by_id(target_project_id)
        if not target_project:
            raise BusinessException(f"Target project '{target_project_id}' not found")

        # Load agent for this step if configured
        step_agent_id = member.get("agent_id", "")
        step_agent_lang = member.get("language", "en")
        if step_agent_id and self._agent_service:
            current = target_project.get_current_agent()
            if not current or current.get("id") != step_agent_id:
                target_project = await self._agent_service.load_agent(
                    project_id=target_project_id,
                    agent_id=step_agent_id,
                    language=step_agent_lang,
                    project_repository=self._project_repo,
                )
                logger.info(
                    "Loaded agent %s for project %s (team step role=%s)",
                    step_agent_id, target_project_id, target_role,
                )
            target_project.lock_agent(task_id="pending")
            await self._project_repo.save(target_project)

        # Determine pipeline step for delegation mode
        pipeline_step = -1
        if mode == "delegation":
            for i, step in enumerate(config.get("pipeline", [])):
                if step.get("role") == target_role:
                    pipeline_step = i
                    break

        # Create TeamTask
        task = TeamTask.create(
            main_project_id=main_project_id,
            coordinator_session_id=coordinator_session_id,
            target_project_id=target_project_id,
            target_role=target_role,
            prompt=prompt,
            context=context,
            parent_task_id=parent_task_id,
            depth=depth,
            pipeline_step=pipeline_step,
            trace_id=trace_id,
        )
        await self._task_repo.save(task)

        # Update agent lock with real task_id
        if step_agent_id and self._agent_service:
            target_project.lock_agent(task_id=task.task_id)
            await self._project_repo.save(target_project)

        # Broadcast task created event
        await self._broadcast_team_event(main_project_id, coordinator_session_id, {
            "event": "team_task_created",
            "task": task.to_timeline_entry(),
        })

        # Record task in trace file
        if trace_id:
            await TraceFileManager.add_task_to_trace(
                project_dir=project.dir_path,
                trace_id=trace_id,
                task_entry={
                    "task_id": task.task_id,
                    "target_role": target_role,
                    "target_project_id": target_project_id,
                    "worker_session_id": "",
                    "prompt": prompt,
                    "context": context,
                    "pipeline_step": pipeline_step,
                    "depth": depth,
                    "parent_task_id": parent_task_id,
                    "status": "pending",
                    "started_at": datetime.now().isoformat(),
                    "result_summary": "",
                    "result_data": {},
                    "files_changed": [],
                    "error_message": "",
                },
            )

        # Create worker session
        role_label = member.get("role_label", target_role)
        worker_model = config.get("model", "claude-sonnet-4-6")
        worker_session = Session.create(
            model=worker_model,
            project_id=target_project_id,
            project_dir=target_project.dir_path,
            team_task_id=task.task_id,
        )
        worker_session.rename(f"[Team] {role_label}: {prompt[:40]}")
        await self._session_repo.save(worker_session)

        worker_session_id = worker_session.session_id
        task.start(worker_session_id)
        await self._task_repo.save(task)

        # Update trace with worker session id
        if trace_id:
            await TraceFileManager.update_task_in_trace(
                project_dir=project.dir_path,
                trace_id=trace_id,
                task_id=task.task_id,
                updates={"worker_session_id": worker_session_id, "status": "running"},
            )

        # Broadcast task running event
        await self._broadcast_team_event(main_project_id, coordinator_session_id, {
            "event": "team_task_running",
            "task": task.to_timeline_entry(),
        })

        # Build worker prompt
        trace_file_path = ""
        if trace_id:
            trace_file_path = TraceFileManager.trace_path(project.dir_path, trace_id)
        worker_prompt = build_worker_prompt(
            task_prompt=prompt,
            context=context,
            role=target_role,
            role_label=role_label,
            trace_file_path=trace_file_path,
        )

        # Determine MCP servers for worker
        worker_mcp = {}
        if mode == "collaboration":
            max_depth = config.get("max_depth", 5)
            if depth < max_depth:
                from infr.client.team_mcp_server import create_team_worker_mcp
                worker_mcp_server = create_team_worker_mcp(self, worker_session_id)
                worker_mcp = {"team_worker": worker_mcp_server}

        # Execute worker via gateway
        max_turns = config.get("worker_max_turns", 50)
        max_budget = config.get("worker_max_budget_usd", 1.0)
        file_checkpointing = config.get("file_checkpointing", True)

        worker_hooks = create_worker_hooks(
            task_id=task.task_id,
            worker_session_id=worker_session_id,
            role=target_role,
            notify_im_fn=self._notify_im_fn,
        )

        try:
            result_text, result_data = await self._execute_worker(
                worker_session_id=worker_session_id,
                model=worker_model,
                prompt=worker_prompt,
                cwd=target_project.dir_path,
                mcp_servers=worker_mcp,
                max_turns=max_turns,
                max_budget_usd=max_budget,
                output_format=WORKER_OUTPUT_FORMAT,
                hooks=worker_hooks,
                enable_file_checkpointing=file_checkpointing,
            )

            task.complete(result_text, result_data=result_data)
            await self._task_repo.save(task)

            # Update trace with completion data
            if trace_id:
                await TraceFileManager.update_task_in_trace(
                    project_dir=project.dir_path,
                    trace_id=trace_id,
                    task_id=task.task_id,
                    updates={
                        "status": "completed",
                        "completed_at": datetime.now().isoformat(),
                        "duration_ms": task.duration_ms,
                        "result_summary": result_text[:500],
                        "result_data": result_data,
                        "files_changed": result_data.get("files_changed", []),
                    },
                )

            await self._broadcast_team_event(main_project_id, coordinator_session_id, {
                "event": "team_task_completed",
                "task": task.to_timeline_entry(),
            })

            return result_text

        except asyncio.CancelledError:
            error_msg = "Task cancelled"
            task.cancel()
            await self._task_repo.save(task)

            if trace_id:
                await TraceFileManager.update_task_in_trace(
                    project_dir=project.dir_path,
                    trace_id=trace_id,
                    task_id=task.task_id,
                    updates={
                        "status": "cancelled",
                        "completed_at": datetime.now().isoformat(),
                        "error_message": error_msg,
                    },
                )

            await self._broadcast_team_event(main_project_id, coordinator_session_id, {
                "event": "team_task_failed",
                "task": task.to_timeline_entry(),
            })

            raise

        except Exception as e:
            error_msg = str(e)[:500]
            task.fail(error_msg)
            await self._task_repo.save(task)

            # Update trace with failure data
            if trace_id:
                await TraceFileManager.update_task_in_trace(
                    project_dir=project.dir_path,
                    trace_id=trace_id,
                    task_id=task.task_id,
                    updates={
                        "status": "failed",
                        "completed_at": datetime.now().isoformat(),
                        "error_message": error_msg,
                    },
                )

            await self._broadcast_team_event(main_project_id, coordinator_session_id, {
                "event": "team_task_failed",
                "task": task.to_timeline_entry(),
            })

            raise

        finally:
            # Unload agent and unlock project after task finishes
            if step_agent_id and self._agent_service:
                try:
                    tp = await self._project_repo.find_by_id(target_project_id)
                    if tp and tp.is_locked_by_task(task.task_id):
                        tp.unlock_agent()
                        await self._project_repo.save(tp)
                        await self._agent_service.unload_agent(
                            project_id=target_project_id,
                            project_repository=self._project_repo,
                        )
                        logger.info(
                            "Unloaded agent %s from project %s (team step role=%s)",
                            step_agent_id, target_project_id, target_role,
                        )
                except Exception:
                    logger.warning(
                        "Failed to unload agent %s from project %s",
                        step_agent_id, target_project_id,
                        exc_info=True,
                    )

    async def dispatch_batch(
        self,
        main_project_id: str,
        coordinator_session_id: str,
        tasks_input: list[dict],
        trace_id: str = "",
    ) -> list[str]:
        """Dispatch multiple tasks in parallel with semaphore-limited concurrency."""
        project = await self._project_repo.find_by_id(main_project_id)
        if not project or project.project_type != "team":
            raise BusinessException(f"Project {main_project_id} is not a team project")

        config = project.team_config
        max_concurrent = config.get("max_concurrent", 2)
        semaphore = asyncio.Semaphore(max(1, max_concurrent))

        async def run_one(t: dict) -> str:
            role = t.get("role", "")
            prompt = t.get("prompt", "")
            context = t.get("context", "")
            if not role or not prompt:
                return f"[{role or '?'}] Error: role and prompt required"
            async with semaphore:
                try:
                    return await self.dispatch_task(
                        main_project_id=main_project_id,
                        coordinator_session_id=coordinator_session_id,
                        target_role=role,
                        prompt=prompt,
                        context=context,
                        trace_id=trace_id,
                    )
                except Exception as e:
                    return f"[{role}] Failed: {e}"

        return list(await asyncio.gather(*[run_one(t) for t in tasks_input]))

    async def _execute_worker(
        self,
        worker_session_id: str,
        model: str,
        prompt: str,
        cwd: str,
        mcp_servers: dict | None = None,
        max_turns: int = 50,
        max_budget_usd: float = 1.0,
        output_format: dict | None = None,
        hooks: dict | None = None,
        enable_file_checkpointing: bool = False,
    ) -> tuple[str, dict]:
        """Execute a worker session and collect the result."""
        result_text = ""
        last_assistant_text = ""

        async for msg_dict in self._gateway.connect(
            session_id=worker_session_id,
            model=model,
            prompt=prompt,
            cwd=cwd,
            sdk_session_id="",
            system_prompt=None,
            mcp_servers=mcp_servers,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
            output_format=output_format,
            hooks=hooks,
            enable_file_checkpointing=enable_file_checkpointing,
        ):
            msg_type = msg_dict.get("message_type")
            if msg_type == "result":
                content = msg_dict.get("content", {})
                result_text = content.get("text", "")
                if content.get("is_error"):
                    raise RuntimeError(f"Worker error: {result_text}")
            elif msg_type == "assistant":
                blocks = msg_dict.get("content", {}).get("blocks", [])
                for block in blocks:
                    if block.get("type") == "text":
                        last_assistant_text = block.get("text", "")

        # Prefer result text, fallback to last assistant message
        final = result_text or last_assistant_text
        if not final:
            final = "(Worker produced no output)"

        # Try parsing structured output
        result_data = {}
        if output_format and final:
            try:
                parsed = json.loads(final)
                if isinstance(parsed, dict):
                    result_data = parsed
                    final = parsed.get("summary", final)
            except (json.JSONDecodeError, TypeError):
                pass

        # Clean up connection
        self._gateway.schedule_idle_disconnect(worker_session_id, delay=30)

        return final, result_data

    async def handle_help_request(
        self,
        worker_session_id: str,
        question: str,
        target_role: str,
    ) -> str:
        """Handle a worker's help request (collaboration mode).

        Routes the question to the appropriate team member via a new dispatch.
        """
        session = await self._session_repo.find_by_id(worker_session_id)
        if not session or not session.team_task_id:
            raise BusinessException("Worker session has no associated team task")

        task = await self._task_repo.find_by_id(session.team_task_id)
        if not task:
            raise BusinessException("Team task not found for worker")

        project = await self._project_repo.find_by_id(task.main_project_id)
        if not project:
            raise BusinessException("Team project not found")

        config = project.team_config
        max_depth = config.get("max_depth", 5)

        if task.depth + 1 >= max_depth:
            return (
                f"Cannot route help request: maximum nesting depth ({max_depth}) reached. "
                "Please proceed with your best judgment based on available information."
            )

        # Mark the current task as waiting for help
        task.wait_for_help()
        await self._task_repo.save(task)

        await self._broadcast_team_event(task.main_project_id, task.coordinator_session_id, {
            "event": "team_task_help_requested",
            "task": task.to_timeline_entry(),
            "question": question,
            "target_role": target_role,
        })

        # Dispatch to target role
        try:
            answer = await self.dispatch_task(
                main_project_id=task.main_project_id,
                coordinator_session_id=task.coordinator_session_id,
                target_role=target_role,
                prompt=question,
                context=f"This is a help request from the {task.target_role} worker.",
                parent_task_id=task.task_id,
                depth=task.depth + 1,
                trace_id=task.trace_id,
            )
        except Exception as e:
            answer = f"Help request failed: {e}"

        # Resume the original task
        task.resume_from_help()
        await self._task_repo.save(task)

        return answer

    async def get_tasks_status(self, coordinator_session_id: str) -> str:
        """Get a formatted status text of all tasks for a coordinator session."""
        tasks = await self._task_repo.find_by_coordinator(coordinator_session_id)
        if not tasks:
            return "No tasks dispatched yet."

        lines = [f"## Task Status ({len(tasks)} tasks)\n"]
        for t in tasks:
            status_icon = {
                TeamTaskStatus.PENDING: "⏳",
                TeamTaskStatus.RUNNING: "🔄",
                TeamTaskStatus.COMPLETED: "✅",
                TeamTaskStatus.FAILED: "❌",
                TeamTaskStatus.CANCELLED: "🚫",
                TeamTaskStatus.WAITING_FOR_HELP: "💬",
            }.get(t.status, "?")

            line = f"- {status_icon} [{t.target_role}] {t.prompt[:60]}"
            if t.status == TeamTaskStatus.COMPLETED and t.result_summary:
                line += f"\n  Result: {t.result_summary[:100]}"
            elif t.status == TeamTaskStatus.FAILED and t.error_message:
                line += f"\n  Error: {t.error_message[:100]}"
            if t.duration_ms:
                line += f" ({t.duration_ms / 1000:.1f}s)"
            lines.append(line)

        return "\n".join(lines)

    async def get_team_timeline(self, coordinator_session_id: str) -> list[dict]:
        """Get the timeline of team tasks for a coordinator session."""
        tasks = await self._task_repo.find_by_coordinator(coordinator_session_id)
        return [t.to_timeline_entry() for t in tasks]

    async def get_linked_sessions(self, coordinator_session_id: str) -> list[dict]:
        """Get all worker sessions linked to a coordinator session."""
        tasks = await self._task_repo.find_by_coordinator(coordinator_session_id)
        session_ids = [t.worker_session_id for t in tasks if t.worker_session_id]

        results = []
        for sid in session_ids:
            session = await self._session_repo.find_by_id(sid)
            if session:
                task = next((t for t in tasks if t.worker_session_id == sid), None)
                waiting_for_input = self._gateway.is_waiting_for_user_input(sid)
                agent_state = self._gateway.get_state(sid)
                task_status = task.status.value if task else ""
                results.append({
                    "session_id": sid,
                    "name": session.name,
                    "project_id": session.project_id,
                    "status": session.status.value,
                    "agent_state": agent_state,
                    "waiting_for_input": waiting_for_input,
                    "display_status": self._worker_display_status(
                        session.status.value,
                        task_status,
                        waiting_for_input,
                    ),
                    "role": task.target_role if task else "",
                    "task_status": task_status,
                })
        return results

    @staticmethod
    def _worker_display_status(
        session_status: str,
        task_status: str,
        waiting_for_input: bool,
    ) -> str:
        if waiting_for_input:
            return "waiting_input"
        if task_status in {"completed", "failed", "cancelled"}:
            return task_status
        if session_status == "running" or task_status in {"running", "waiting_for_help"}:
            return "running"
        return session_status or "idle"

    async def cancel_team_session(self, coordinator_session_id: str) -> None:
        """Cancel all running tasks for a coordinator session."""
        tasks = await self._task_repo.find_running_by_coordinator(coordinator_session_id)
        for task in tasks:
            task.cancel()
            await self._task_repo.save(task)
            if task.worker_session_id:
                try:
                    await self._gateway.interrupt(task.worker_session_id)
                except Exception:
                    logger.warning(
                        "Failed to interrupt worker session %s",
                        task.worker_session_id,
                    )

    async def delete_team_session(self, coordinator_session_id: str) -> list[str]:
        """Delete all worker sessions associated with a coordinator session.

        Returns list of deleted worker session IDs.
        """
        tasks = await self._task_repo.find_by_coordinator(coordinator_session_id)
        deleted_ids = []
        for task in tasks:
            if task.worker_session_id:
                worker = await self._session_repo.find_by_id(task.worker_session_id)
                if worker:
                    try:
                        await self._gateway.disconnect(task.worker_session_id)
                    except Exception:
                        logger.debug("Disconnect failed for worker session=%s", task.worker_session_id, exc_info=True)
                    await self._session_repo.remove(task.worker_session_id)
                    await self._gateway.cleanup_session(task.worker_session_id)
                    deleted_ids.append(task.worker_session_id)
            await self._task_repo.remove(task.task_id)
        return deleted_ids

    def _find_member_by_role(self, config: dict, role: str) -> dict | None:
        """Find a team member config by role."""
        mode = config.get("mode", "delegation")
        members = config.get("pipeline" if mode == "delegation" else "members", [])
        for m in members:
            if m.get("role") == role:
                return m
        return None

    async def get_worker_context(self, worker_session_id: str) -> dict:
        """Get coordinator info for a worker session (for breadcrumb navigation)."""
        session = await self._session_repo.find_by_id(worker_session_id)
        if not session or not session.team_task_id:
            return {}

        task = await self._task_repo.find_by_id(session.team_task_id)
        if not task:
            return {}

        project = await self._project_repo.find_by_id(task.main_project_id)
        return {
            "coordinator_session_id": task.coordinator_session_id,
            "team_project_id": task.main_project_id,
            "team_project_name": project.name if project else "",
            "role": task.target_role,
        }

    async def _broadcast_team_event(
        self,
        project_id: str,
        coordinator_session_id: str,
        data: dict[str, Any],
    ) -> None:
        """Broadcast a team event to global WS and coordinator session."""
        payload = {**data, "project_id": project_id, "coordinator_session_id": coordinator_session_id}
        await self._connection_manager.broadcast_global(payload)
