from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any


class TraceFileManager:

    _locks: dict[str, asyncio.Lock] = {}
    _locks_guard = asyncio.Lock()
    _MAX_LOCKS = 200

    @classmethod
    async def _get_lock(cls, trace_id: str) -> asyncio.Lock:
        async with cls._locks_guard:
            if trace_id not in cls._locks:
                if len(cls._locks) >= cls._MAX_LOCKS:
                    stale = [k for k, v in cls._locks.items() if not v.locked()]
                    for k in stale[:len(cls._locks) - cls._MAX_LOCKS + 1]:
                        del cls._locks[k]
                cls._locks[trace_id] = asyncio.Lock()
            return cls._locks[trace_id]

    @classmethod
    async def _release_lock(cls, trace_id: str) -> None:
        async with cls._locks_guard:
            lock = cls._locks.get(trace_id)
            if lock and not lock.locked():
                cls._locks.pop(trace_id, None)

    @staticmethod
    def trace_dir(project_dir: str) -> str:
        return os.path.join(project_dir, ".velpos", "traces")

    @staticmethod
    def trace_path(project_dir: str, trace_id: str) -> str:
        return os.path.join(project_dir, ".velpos", "traces", f"{trace_id}.json")

    @classmethod
    async def create_trace(
        cls,
        project_dir: str,
        trace_id: str,
        requirement: str,
        coordinator_session_id: str,
        project_id: str,
    ) -> str:
        lock = await cls._get_lock(trace_id)
        async with lock:
            trace_data = {
                "trace_id": trace_id,
                "requirement": requirement,
                "coordinator_session_id": coordinator_session_id,
                "project_id": project_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "status": "running",
                "call_chain": [],
                "artifacts": [],
            }
            path = cls.trace_path(project_dir, trace_id)
            await asyncio.to_thread(cls._write_json, path, trace_data)
            return path

    @classmethod
    async def add_task_to_trace(
        cls,
        project_dir: str,
        trace_id: str,
        task_entry: dict[str, Any],
    ) -> None:
        lock = await cls._get_lock(trace_id)
        async with lock:
            data = await asyncio.to_thread(
                cls._read_json, cls.trace_path(project_dir, trace_id),
            )
            if data is None:
                return
            data["call_chain"].append(task_entry)
            data["updated_at"] = datetime.now().isoformat()
            await asyncio.to_thread(
                cls._write_json, cls.trace_path(project_dir, trace_id), data,
            )

    @classmethod
    async def update_task_in_trace(
        cls,
        project_dir: str,
        trace_id: str,
        task_id: str,
        updates: dict[str, Any],
    ) -> None:
        lock = await cls._get_lock(trace_id)
        async with lock:
            data = await asyncio.to_thread(
                cls._read_json, cls.trace_path(project_dir, trace_id),
            )
            if data is None:
                return
            for entry in data["call_chain"]:
                if entry.get("task_id") == task_id:
                    entry.update(updates)
                    break
            data["updated_at"] = datetime.now().isoformat()
            cls._rebuild_artifacts(data)
            await asyncio.to_thread(
                cls._write_json, cls.trace_path(project_dir, trace_id), data,
            )

    @classmethod
    async def complete_trace(
        cls,
        project_dir: str,
        trace_id: str,
    ) -> None:
        lock = await cls._get_lock(trace_id)
        async with lock:
            data = await asyncio.to_thread(
                cls._read_json, cls.trace_path(project_dir, trace_id),
            )
            if data is None:
                return
            data["status"] = "completed"
            data["updated_at"] = datetime.now().isoformat()
            cls._rebuild_artifacts(data)
            await asyncio.to_thread(
                cls._write_json, cls.trace_path(project_dir, trace_id), data,
            )
        await cls._release_lock(trace_id)

    @classmethod
    async def fail_trace(
        cls,
        project_dir: str,
        trace_id: str,
    ) -> None:
        lock = await cls._get_lock(trace_id)
        async with lock:
            data = await asyncio.to_thread(
                cls._read_json, cls.trace_path(project_dir, trace_id),
            )
            if data is None:
                return
            data["status"] = "failed"
            data["updated_at"] = datetime.now().isoformat()
            await asyncio.to_thread(
                cls._write_json, cls.trace_path(project_dir, trace_id), data,
            )
        await cls._release_lock(trace_id)

    @classmethod
    async def read_trace(
        cls,
        project_dir: str,
        trace_id: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            cls._read_json, cls.trace_path(project_dir, trace_id),
        )

    @classmethod
    async def list_traces(cls, project_dir: str) -> list[dict[str, Any]]:
        trace_directory = cls.trace_dir(project_dir)
        if not os.path.isdir(trace_directory):
            return []

        summaries: list[dict[str, Any]] = []
        for filename in sorted(os.listdir(trace_directory), reverse=True):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(trace_directory, filename)
            data = await asyncio.to_thread(cls._read_json, path)
            if data is None:
                continue
            summaries.append({
                "trace_id": data.get("trace_id", ""),
                "requirement": data.get("requirement", "")[:120],
                "status": data.get("status", ""),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "task_count": len(data.get("call_chain", [])),
                "artifact_count": len(data.get("artifacts", [])),
            })
        return summaries

    @staticmethod
    def _rebuild_artifacts(data: dict[str, Any]) -> None:
        seen: set[str] = set()
        artifacts: list[str] = []
        for entry in data.get("call_chain", []):
            for f in entry.get("files_changed", []):
                if f not in seen:
                    seen.add(f)
                    artifacts.append(f)
        data["artifacts"] = artifacts

    @staticmethod
    def _write_json(path: str, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_json(path: str) -> dict[str, Any] | None:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
