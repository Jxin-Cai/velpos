from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class ScheduledTask:
    id: str
    project_id: str
    session_id: str
    channel_id: str
    name: str
    prompt: str
    cron_expr: str
    enabled: bool = True
    auto_unbind_after_run: bool = True
    delete_session_on_success: bool = False
    next_run_time: datetime | None = None
    created_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        project_id: str,
        session_id: str,
        name: str,
        prompt: str,
        cron_expr: str,
        enabled: bool = True,
        channel_id: str = "",
        auto_unbind_after_run: bool = True,
        delete_session_on_success: bool = False,
    ) -> ScheduledTask:
        task = cls(
            id=uuid.uuid4().hex[:8],
            project_id=project_id,
            session_id=session_id,
            channel_id=channel_id.strip(),
            name=name.strip() or "Scheduled task",
            prompt=prompt,
            cron_expr=cron_expr.strip() or "*/30 * * * *",
            enabled=enabled,
            auto_unbind_after_run=auto_unbind_after_run,
            delete_session_on_success=delete_session_on_success,
            next_run_time=None,
            created_time=datetime.now(),
        )
        task.schedule_next()
        return task

    def update(
        self,
        name: str | None = None,
        prompt: str | None = None,
        cron_expr: str | None = None,
        enabled: bool | None = None,
        session_id: str | None = None,
        channel_id: str | None = None,
        auto_unbind_after_run: bool | None = None,
        delete_session_on_success: bool | None = None,
    ) -> None:
        if name is not None:
            self.name = name.strip() or self.name
        if prompt is not None:
            self.prompt = prompt
        if cron_expr is not None:
            self.cron_expr = cron_expr.strip() or self.cron_expr
        if enabled is not None:
            self.enabled = enabled
        if session_id is not None:
            self.session_id = session_id.strip()
        if channel_id is not None:
            self.channel_id = channel_id.strip()
        if auto_unbind_after_run is not None:
            self.auto_unbind_after_run = auto_unbind_after_run
        if delete_session_on_success is not None:
            self.delete_session_on_success = delete_session_on_success
        self.schedule_next()

    def schedule_next(self, now: datetime | None = None) -> None:
        self.next_run_time = self._next_time(now or datetime.now()) if self.enabled else None

    def mark_triggered(self, now: datetime | None = None) -> None:
        self.schedule_next(now or datetime.now())

    def _next_time(self, now: datetime) -> datetime:
        parts = self.cron_expr.split()
        if len(parts) != 5:
            return now + timedelta(minutes=30)
        minute, hour, _dom, _month, dow = parts
        if minute.startswith("*/"):
            try:
                step = max(int(minute[2:]), 1)
            except ValueError:
                step = 30
            return now + timedelta(minutes=step)
        if minute == "*":
            return now + timedelta(minutes=1)
        try:
            target_minute = int(minute)
        except ValueError:
            return now + timedelta(minutes=30)
        if hour.startswith("*/"):
            try:
                step = max(int(hour[2:]), 1)
            except ValueError:
                step = 1
            candidate = now.replace(second=0, microsecond=0, minute=target_minute)
            if candidate <= now:
                candidate += timedelta(hours=1)
            while candidate <= now:
                candidate += timedelta(hours=step)
            return candidate
        if hour == "*":
            candidate = now.replace(second=0, microsecond=0, minute=target_minute)
            if candidate <= now:
                candidate += timedelta(hours=1)
            return candidate
        try:
            target_hour = int(hour)
        except ValueError:
            return now + timedelta(minutes=30)
        candidate = now.replace(second=0, microsecond=0, hour=target_hour, minute=target_minute)
        if dow != "*":
            try:
                target_weekday = int(dow)
            except ValueError:
                return now + timedelta(minutes=30)
            days_ahead = (target_weekday - candidate.weekday()) % 7
            candidate += timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7 if dow != "*" else 1)
        return candidate


@dataclass
class ScheduledTaskRun:
    id: str
    task_id: str
    status: str
    started_time: datetime = field(default_factory=datetime.now)
    ended_time: datetime | None = None
    result_session_id: str = ""
    error_message: str = ""

    @classmethod
    def start(cls, task_id: str) -> ScheduledTaskRun:
        return cls(id=uuid.uuid4().hex[:8], task_id=task_id, status="running", started_time=datetime.now())

    def complete(self, result_session_id: str) -> None:
        self.status = "succeeded"
        self.result_session_id = result_session_id
        self.ended_time = datetime.now()

    def fail(self, error_message: str) -> None:
        self.status = "failed"
        self.error_message = error_message[:500]
        self.ended_time = datetime.now()
