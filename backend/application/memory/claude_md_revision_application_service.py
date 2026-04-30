from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from domain.memory.model.claude_md_revision import ClaudeMdRevision
from domain.memory.model.claude_md_revision_event import ClaudeMdRevisionEvent
from domain.memory.model.claude_md_revision_state import ClaudeMdRevisionState
from domain.memory.repository.claude_md_revision_repository import ClaudeMdRevisionRepository
from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException


@dataclass(frozen=True)
class ClaudeMdApplyResult:
    revision: ClaudeMdRevision
    conflict: bool
    current_file_hash: str


class ClaudeMdRevisionApplicationService:

    def __init__(
        self,
        revision_repository: ClaudeMdRevisionRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._revision_repository = revision_repository
        self._project_repository = project_repository

    async def read_current(self, project_dir: str) -> dict:
        project, claude_md_path = await self._resolve_project(project_dir)
        content = await self._read_file(claude_md_path)
        file_hash = ClaudeMdRevision.hash_content(content)
        active = await self._ensure_initial_revision(project, content, file_hash)
        versions = await self._revision_repository.find_by_project_id(project.id)
        return {
            "content": content,
            "file_hash": file_hash,
            "project_id": project.id,
            "active_revision": self._revision_to_dict(active),
            "versions": [self._revision_to_dict(v) for v in versions],
            "dirty": bool(project.claude_md_file_hash and project.claude_md_file_hash != file_hash),
        }

    async def list_versions(self, project_dir: str) -> list[ClaudeMdRevision]:
        project, claude_md_path = await self._resolve_project(project_dir)
        content = await self._read_file(claude_md_path)
        file_hash = ClaudeMdRevision.hash_content(content)
        await self._ensure_initial_revision(project, content, file_hash)
        return await self._revision_repository.find_by_project_id(project.id)

    async def create_draft(
        self,
        project_dir: str,
        content: str,
        base_revision_id: str = "",
        created_by: str = "user",
    ) -> ClaudeMdRevision:
        project, claude_md_path = await self._resolve_project(project_dir)
        current_content = await self._read_file(claude_md_path)
        current_hash = ClaudeMdRevision.hash_content(current_content)
        active = await self._ensure_initial_revision(project, current_content, current_hash)
        base_revision = await self._resolve_base_revision(base_revision_id, active)
        revision = ClaudeMdRevision.create_draft(
            project_id=project.id,
            version_no=await self._revision_repository.next_version_no(project.id),
            content=content,
            base_revision_id=base_revision.id,
            base_file_hash=current_hash,
            created_by=created_by,
        )
        await self._revision_repository.save(revision)
        await self._record_event(revision, "", revision.state.value)
        return revision

    async def update_revision(self, revision_id: str, content: str) -> ClaudeMdRevision:
        revision = await self._get_revision(revision_id)
        before = revision.state.value
        revision.update_content(content)
        if revision.state == ClaudeMdRevisionState.CONFLICTED:
            revision.reopen_as_draft()
        await self._revision_repository.save(revision)
        await self._record_event(revision, before, revision.state.value, {"action": "content_updated"})
        return revision

    async def propose(self, revision_id: str) -> ClaudeMdRevision:
        revision = await self._get_revision(revision_id)
        before = revision.state.value
        revision.propose()
        await self._revision_repository.save(revision)
        await self._record_event(revision, before, revision.state.value)
        return revision

    async def approve(self, revision_id: str) -> ClaudeMdRevision:
        revision = await self._get_revision(revision_id)
        before = revision.state.value
        revision.approve()
        await self._revision_repository.save(revision)
        await self._record_event(revision, before, revision.state.value)
        return revision

    async def reject(self, revision_id: str, reason: str = "") -> ClaudeMdRevision:
        revision = await self._get_revision(revision_id)
        before = revision.state.value
        revision.reject(reason)
        await self._revision_repository.save(revision)
        await self._record_event(revision, before, revision.state.value, {"reason": reason})
        return revision

    async def apply(
        self,
        revision_id: str,
        project_dir: str,
        expected_base_revision_id: str,
        expected_file_hash: str,
    ) -> ClaudeMdApplyResult:
        revision = await self._get_revision(revision_id)
        if revision.state not in {ClaudeMdRevisionState.DRAFT, ClaudeMdRevisionState.APPROVED}:
            raise BusinessException("Only draft or approved CLAUDE.md revisions can be applied")
        if revision.base_revision_id != expected_base_revision_id:
            raise BusinessException("Revision base does not match expected base")

        project, claude_md_path = await self._resolve_project(project_dir)
        if revision.project_id != project.id:
            raise BusinessException("Revision does not belong to the project")

        current_content = await self._read_file(claude_md_path)
        current_hash = ClaudeMdRevision.hash_content(current_content)
        if current_hash != expected_file_hash:
            before = revision.state.value
            revision.mark_conflicted()
            await self._revision_repository.save(revision)
            await self._record_event(
                revision,
                before,
                revision.state.value,
                {"expected_file_hash": expected_file_hash, "current_file_hash": current_hash},
            )
            return ClaudeMdApplyResult(revision=revision, conflict=True, current_file_hash=current_hash)

        await asyncio.to_thread(claude_md_path.write_text, revision.content, "utf-8")
        applied_hash = ClaudeMdRevision.hash_content(revision.content)
        before = revision.state.value
        revision.apply()
        project.update_claude_md_revision(revision.id, applied_hash)
        await self._revision_repository.save(revision)
        await self._project_repository.save(project)
        await self._record_event(revision, before, revision.state.value, {"file_hash": applied_hash})
        return ClaudeMdApplyResult(revision=revision, conflict=False, current_file_hash=applied_hash)

    async def delete_revision(self, revision_id: str) -> None:
        revision = await self._get_revision(revision_id)
        project = await self._project_repository.find_by_id(revision.project_id)
        removed = await self._revision_repository.remove(revision.id)
        if not removed:
            raise BusinessException("CLAUDE.md revision not found")
        if project and project.active_claude_md_revision_id == revision.id:
            fallback = await self._revision_repository.find_active_by_project_id(project.id)
            if fallback:
                project.update_claude_md_revision(fallback.id, fallback.content_hash)
            else:
                project.update_claude_md_revision("", "")
            await self._project_repository.save(project)

    async def diff_revision(self, revision_id: str) -> dict:
        revision = await self._get_revision(revision_id)
        base = await self._revision_repository.find_by_id(revision.base_revision_id) if revision.base_revision_id else None
        return {
            "base_content": base.content if base else "",
            "content": revision.content,
            "base_revision": self._revision_to_dict(base) if base else None,
            "revision": self._revision_to_dict(revision),
        }

    async def _resolve_project(self, project_dir: str) -> tuple[Project, Path]:
        project_path = Path(project_dir).expanduser().resolve()
        if not project_path.is_dir():
            raise BusinessException("Project directory not found")
        project = await self._project_repository.find_by_dir_path(str(project_path))
        if project is None:
            project = Project.create(project_path.name, str(project_path))
            await self._project_repository.save(project)
        claude_md_path = (project_path / "CLAUDE.md").resolve()
        if not claude_md_path.is_relative_to(project_path):
            raise BusinessException("Invalid CLAUDE.md path")
        return project, claude_md_path

    async def _ensure_initial_revision(
        self,
        project: Project,
        content: str,
        file_hash: str,
    ) -> ClaudeMdRevision:
        active = None
        if project.active_claude_md_revision_id:
            active = await self._revision_repository.find_by_id(project.active_claude_md_revision_id)
        if active is None:
            active = await self._revision_repository.find_active_by_project_id(project.id)
        if active is not None:
            return active

        initial = ClaudeMdRevision.create_initial(project.id, content, file_hash)
        project.update_claude_md_revision(initial.id, file_hash)
        await self._revision_repository.save(initial)
        await self._project_repository.save(project)
        await self._record_event(initial, "", initial.state.value, {"action": "initialized"})
        return initial

    async def _resolve_base_revision(
        self,
        base_revision_id: str,
        active: ClaudeMdRevision,
    ) -> ClaudeMdRevision:
        if not base_revision_id:
            return active
        base = await self._revision_repository.find_by_id(base_revision_id)
        if base is None:
            raise BusinessException("Base revision not found")
        return base

    async def _get_revision(self, revision_id: str) -> ClaudeMdRevision:
        revision = await self._revision_repository.find_by_id(revision_id)
        if revision is None:
            raise BusinessException("CLAUDE.md revision not found")
        return revision

    async def _record_event(
        self,
        revision: ClaudeMdRevision,
        from_state: str,
        to_state: str,
        payload: dict | None = None,
    ) -> None:
        await self._revision_repository.save_event(
            ClaudeMdRevisionEvent.create(
                revision_id=revision.id,
                from_state=from_state,
                to_state=to_state,
                payload=payload,
            )
        )

    @staticmethod
    async def _read_file(path: Path) -> str:
        if not path.exists() or not path.is_file():
            return ""
        return await asyncio.to_thread(path.read_text, "utf-8")

    @staticmethod
    def _revision_to_dict(revision: ClaudeMdRevision | None) -> dict | None:
        if revision is None:
            return None
        return {
            "id": revision.id,
            "project_id": revision.project_id,
            "version_no": revision.version_no,
            "state": revision.state.value,
            "content": revision.content,
            "content_hash": revision.content_hash,
            "base_revision_id": revision.base_revision_id,
            "base_file_hash": revision.base_file_hash,
            "created_by": revision.created_by,
            "created_time": revision.created_time.isoformat(),
            "proposed_time": revision.proposed_time.isoformat() if revision.proposed_time else None,
            "approved_time": revision.approved_time.isoformat() if revision.approved_time else None,
            "applied_time": revision.applied_time.isoformat() if revision.applied_time else None,
            "rejected_time": revision.rejected_time.isoformat() if revision.rejected_time else None,
            "reject_reason": revision.reject_reason,
        }
