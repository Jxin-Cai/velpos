from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.run_query_command import RunQueryCommand
from application.session.session_application_service import SessionApplicationService
from domain.project.repository.project_repository import ProjectRepository
from domain.scheduler.model.scheduled_task import ScheduledTask, ScheduledTaskRun
from domain.scheduler.repository.scheduled_task_repository import ScheduledTaskRepository
from domain.session.acl.connection_manager import ConnectionManager
from domain.session.service.message_conversion_service import MessageConversionService
from domain.shared.async_utils import safe_create_task
from domain.shared.business_exception import BusinessException


class SchedulerApplicationService:

    def __init__(
        self,
        repository: ScheduledTaskRepository,
        project_repository: ProjectRepository,
        session_service_factory: Callable[..., Awaitable[SessionApplicationService]],
        connection_manager: ConnectionManager,
        notify_im_fn: Callable[[str, str], Awaitable[None]] | None = None,
        bind_im_fn: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None,
        unbind_im_fn: Callable[[str], Awaitable[None]] | None = None,
        save_run_fn: Callable[[ScheduledTaskRun], Awaitable[None]] | None = None,
    ) -> None:
        self._repository = repository
        self._project_repository = project_repository
        self._session_service_factory = session_service_factory
        self._connection_manager = connection_manager
        self._notify_im_fn = notify_im_fn
        self._bind_im_fn = bind_im_fn
        self._unbind_im_fn = unbind_im_fn
        self._save_run_fn = save_run_fn

    async def list_tasks(self, project_id: str = "") -> list[dict[str, Any]]:
        tasks = await self._repository.find_all()
        if project_id:
            tasks = [task for task in tasks if task.project_id == project_id]
        result = []
        for task in tasks:
            runs = await self._repository.find_runs_by_task_id(task.id)
            result.append({**self.task_to_dict(task), "runs": [self.run_to_dict(run) for run in runs]})
        return result

    async def create_task(
        self,
        project_id: str,
        session_id: str,
        name: str,
        prompt: str,
        cron_expr: str,
        enabled: bool = True,
        channel_id: str = "",
        auto_unbind_after_run: bool = True,
        delete_session_on_success: bool = False,
        execution_mode: str = "new_session",
        prompt_mode: str = "prompt",
        skill_name: str = "",
    ) -> ScheduledTask:
        self._validate_content(prompt_mode, prompt, skill_name)
        self._validate_execution_mode(execution_mode, session_id)
        self._validate_cron_expr(cron_expr)
        if project_id:
            project = await self._project_repository.find_by_id(project_id)
            if project is None:
                raise BusinessException("Project not found")
        if execution_mode == "existing_session":
            await self._validate_existing_session(session_id, project_id)
        task = ScheduledTask.create(
            project_id,
            session_id.strip(),
            name,
            prompt,
            cron_expr,
            enabled,
            channel_id=channel_id,
            auto_unbind_after_run=auto_unbind_after_run,
            delete_session_on_success=delete_session_on_success,
            execution_mode=execution_mode,
            prompt_mode=prompt_mode,
            skill_name=skill_name,
        )
        await self._repository.save(task)
        return task

    async def update_task(
        self,
        task_id: str,
        session_id: str | None = None,
        name: str | None = None,
        prompt: str | None = None,
        cron_expr: str | None = None,
        enabled: bool | None = None,
        channel_id: str | None = None,
        auto_unbind_after_run: bool | None = None,
        delete_session_on_success: bool | None = None,
        execution_mode: str | None = None,
        prompt_mode: str | None = None,
        skill_name: str | None = None,
    ) -> ScheduledTask:
        if cron_expr is not None:
            self._validate_cron_expr(cron_expr)
        task = await self._get_task(task_id)
        resolved_execution_mode = task.execution_mode if execution_mode is None else execution_mode
        resolved_session_id = task.session_id if session_id is None else session_id
        resolved_prompt_mode = task.prompt_mode if prompt_mode is None else prompt_mode
        resolved_prompt = task.prompt if prompt is None else prompt
        resolved_skill_name = task.skill_name if skill_name is None else skill_name
        self._validate_execution_mode(resolved_execution_mode, resolved_session_id)
        self._validate_content(resolved_prompt_mode, resolved_prompt, resolved_skill_name)
        if resolved_execution_mode == "existing_session":
            await self._validate_existing_session(resolved_session_id, task.project_id)
        task.update(
            session_id=session_id,
            name=name,
            prompt=prompt,
            cron_expr=cron_expr,
            enabled=enabled,
            channel_id=channel_id,
            auto_unbind_after_run=auto_unbind_after_run,
            delete_session_on_success=delete_session_on_success,
            execution_mode=execution_mode,
            prompt_mode=prompt_mode,
            skill_name=skill_name,
        )
        await self._repository.save(task)
        return task

    async def delete_task(self, task_id: str) -> None:
        removed = await self._repository.remove(task_id)
        if not removed:
            raise BusinessException("Scheduled task not found")

    async def run_now(self, task_id: str) -> ScheduledTaskRun:
        task = await self._get_task(task_id)
        run = await self._execute_task(task)
        task.mark_triggered(datetime.now())
        await self._repository.save(task)
        return run

    async def run_due_tasks(self, now: datetime | None = None) -> list[ScheduledTaskRun]:
        due_tasks = await self._repository.find_due(now or datetime.now())
        runs = []
        for task in due_tasks:
            run = await self._execute_task(task)
            task.mark_triggered(datetime.now())
            await self._repository.save(task)
            runs.append(run)
        return runs

    async def _execute_task(self, task: ScheduledTask) -> ScheduledTaskRun:
        run = ScheduledTaskRun.start(task.id)
        await self._repository.save_run(run)
        await self._repository.commit()
        service: SessionApplicationService | None = None
        try:
            service = await self._session_service_factory()
            project_dir = ""
            if task.project_id:
                project = await self._project_repository.find_by_id(task.project_id)
                project_dir = project.dir_path if project else ""
            created_new_session = task.execution_mode == "new_session"
            if created_new_session:
                session = await service.create_session(CreateSessionCommand(
                    model=os.getenv("DEFAULT_MODEL", "default"),
                    project_id=task.project_id,
                    project_dir=project_dir,
                    name=f"[Scheduled] {task.name}",
                ))
            else:
                session = await service.get_session(task.session_id)
                if task.project_id and session.project_id != task.project_id:
                    raise BusinessException("Selected session does not belong to this project")
            notify_session_id = session.session_id if task.channel_id else ""
            if task.channel_id:
                await self._bind_im(session.session_id, task.channel_id)
            await self._connection_manager.broadcast_global({
                "event": "scheduled_session_created",
                "task_id": task.id,
                "project_id": task.project_id,
                "session_id": session.session_id,
                "created": created_new_session,
            })
            if notify_session_id:
                await self._notify_im(
                    notify_session_id,
                    self._build_start_message(task, session.session_id),
                )
            safe_create_task(
                self._run_task_query(
                    service,
                    task,
                    run,
                    session.session_id,
                    notify_session_id,
                    created_new_session,
                )
            )
        except Exception as exc:
            run.fail(str(exc))
            await self._repository.save_run(run)
            await self._repository.commit()
            if service is not None:
                await service.close()
        return run

    async def _run_task_query(
        self,
        service: SessionApplicationService,
        task: ScheduledTask,
        run: ScheduledTaskRun,
        result_session_id: str,
        notify_session_id: str,
        created_new_session: bool,
    ) -> None:
        succeeded = False
        try:
            await service.submit_query(
                RunQueryCommand(
                    session_id=result_session_id,
                    prompt=self._build_execution_prompt(task),
                )
            )
            session = await service.get_session(result_session_id)
            assistant_text = MessageConversionService.extract_assistant_text(session.messages)
            if notify_session_id:
                await self._notify_im(
                    notify_session_id,
                    self._build_result_message(task, result_session_id, assistant_text),
                )
            run.complete(result_session_id)
            succeeded = True
        except Exception as exc:
            run.fail(str(exc))
            if notify_session_id:
                await self._notify_im(
                    notify_session_id,
                    self._build_failure_message(task, result_session_id, str(exc)),
                )
        finally:
            try:
                await self._save_run(run)
            finally:
                try:
                    if task.auto_unbind_after_run and task.channel_id:
                        await self._unbind_im(result_session_id)
                    if succeeded and created_new_session and task.delete_session_on_success:
                        await service.delete_session(result_session_id)
                finally:
                    await service.close()

    async def _save_run(self, run: ScheduledTaskRun) -> None:
        if self._save_run_fn is not None:
            await self._save_run_fn(run)
            return
        await self._repository.save_run(run)
        await self._repository.commit()

    async def _notify_im(self, session_id: str, content: str) -> None:
        if not session_id or not content or self._notify_im_fn is None:
            return
        await self._notify_im_fn(session_id, content)

    async def _bind_im(self, session_id: str, channel_id: str) -> None:
        if not session_id or not channel_id or self._bind_im_fn is None:
            return
        await self._bind_im_fn(session_id, channel_id)

    async def _unbind_im(self, session_id: str) -> None:
        if not session_id or self._unbind_im_fn is None:
            return
        await self._unbind_im_fn(session_id)

    @staticmethod
    def _build_start_message(task: ScheduledTask, result_session_id: str) -> str:
        return (
            f"[Scheduled Task Started]\n"
            f"Task: {task.name}\n"
            f"Execution session: {result_session_id}\n\n"
            f"{SchedulerApplicationService._build_execution_prompt(task)}"
        )

    @staticmethod
    def _build_result_message(task: ScheduledTask, result_session_id: str, assistant_text: str) -> str:
        summary = (assistant_text or "Task finished. Open the execution session for full details.").strip()
        if len(summary) > 1200:
            summary = summary[:1200].rstrip() + "..."
        return (
            f"[Scheduled Task Result]\n"
            f"Task: {task.name}\n"
            f"Execution session: {result_session_id}\n\n"
            f"{summary}"
        )

    @staticmethod
    def _build_failure_message(task: ScheduledTask, result_session_id: str, error_message: str) -> str:
        detail = (error_message or "Unknown error").strip()
        if len(detail) > 500:
            detail = detail[:500].rstrip() + "..."
        return (
            f"[Scheduled Task Failed]\n"
            f"Task: {task.name}\n"
            f"Execution session: {result_session_id}\n\n"
            f"{detail}"
        )

    async def _get_task(self, task_id: str) -> ScheduledTask:
        task = await self._repository.find_by_id(task_id)
        if task is None:
            raise BusinessException("Scheduled task not found")
        return task

    async def _validate_existing_session(self, session_id: str, project_id: str) -> None:
        service = await self._session_service_factory()
        try:
            session = await service.get_session(session_id.strip())
            if project_id and session.project_id != project_id:
                raise BusinessException("Selected session does not belong to this project")
        finally:
            await service.close()

    @staticmethod
    def _validate_execution_mode(execution_mode: str, session_id: str) -> None:
        if execution_mode not in {"new_session", "existing_session"}:
            raise BusinessException("Execution mode is invalid")
        if execution_mode == "existing_session" and not session_id.strip():
            raise BusinessException("Select a session to reuse")

    @staticmethod
    def _validate_content(prompt_mode: str, prompt: str, skill_name: str) -> None:
        if prompt_mode not in {"prompt", "skill"}:
            raise BusinessException("Prompt mode is invalid")
        if prompt_mode == "prompt" and not prompt.strip():
            raise BusinessException("Scheduled task prompt is required")
        if prompt_mode == "skill" and not skill_name.strip():
            raise BusinessException("Select a skill to invoke")

    @staticmethod
    def _build_execution_prompt(task: ScheduledTask) -> str:
        prompt = task.prompt.strip()
        if task.prompt_mode != "skill":
            return prompt
        invocation = f"/{task.skill_name.strip()}"
        return f"{invocation} {prompt}".strip()

    @staticmethod
    def _validate_cron_expr(cron_expr: str) -> None:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise BusinessException("Schedule time is invalid")

        def valid_number(value: str, min_value: int, max_value: int) -> bool:
            return value.isdigit() and min_value <= int(value) <= max_value

        def valid_step(value: str, min_value: int, max_value: int) -> bool:
            return value.startswith("*/") and value[2:].isdigit() and min_value <= int(value[2:]) <= max_value

        minute, hour, dom, month, dow = parts
        if not (minute == "*" or valid_number(minute, 0, 59) or valid_step(minute, 1, 59)):
            raise BusinessException("Schedule minute is invalid")
        if not (hour == "*" or valid_number(hour, 0, 23) or valid_step(hour, 1, 23)):
            raise BusinessException("Schedule hour is invalid")
        if dom != "*":
            raise BusinessException("Day-of-month schedules are not supported yet")
        if month != "*":
            raise BusinessException("Month schedules are not supported yet")
        if not (dow == "*" or valid_number(dow, 0, 6)):
            raise BusinessException("Schedule weekday is invalid")

    @staticmethod
    def task_to_dict(task: ScheduledTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "project_id": task.project_id,
            "session_id": task.session_id,
            "channel_id": task.channel_id,
            "name": task.name,
            "prompt": task.prompt,
            "cron_expr": task.cron_expr,
            "execution_mode": task.execution_mode,
            "prompt_mode": task.prompt_mode,
            "skill_name": task.skill_name,
            "enabled": task.enabled,
            "auto_unbind_after_run": task.auto_unbind_after_run,
            "delete_session_on_success": task.delete_session_on_success,
            "next_run_time": task.next_run_time.isoformat() if task.next_run_time else None,
            "created_time": task.created_time.isoformat(),
        }

    @staticmethod
    def run_to_dict(run: ScheduledTaskRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "task_id": run.task_id,
            "status": run.status,
            "started_time": run.started_time.isoformat(),
            "ended_time": run.ended_time.isoformat() if run.ended_time else None,
            "result_session_id": run.result_session_id,
            "error_message": run.error_message,
        }
