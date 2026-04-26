from __future__ import annotations

from typing import Any

from application.memory.claude_md_revision_application_service import ClaudeMdRevisionApplicationService
from domain.evolution.model.evolution_proposal import EvolutionProposal
from domain.evolution.repository.evolution_proposal_repository import EvolutionProposalRepository
from domain.project.repository.project_repository import ProjectRepository
from domain.session.model.message_type import MessageType
from domain.session.repository.session_repository import SessionRepository
from domain.shared.business_exception import BusinessException


class EvolutionApplicationService:

    def __init__(
        self,
        proposal_repository: EvolutionProposalRepository,
        session_repository: SessionRepository,
        project_repository: ProjectRepository,
        claude_md_revision_service: ClaudeMdRevisionApplicationService,
    ) -> None:
        self._proposal_repository = proposal_repository
        self._session_repository = session_repository
        self._project_repository = project_repository
        self._claude_md_revision_service = claude_md_revision_service

    async def extract_lessons(
        self,
        project_id: str = "",
        project_dir: str = "",
        session_id: str = "",
        limit: int = 80,
    ) -> dict[str, Any]:
        project_id = await self._resolve_project_id(project_id, project_dir)
        sessions = []
        if session_id:
            session = await self._session_repository.find_by_id(session_id)
            if session is None:
                raise BusinessException("Session not found")
            sessions = [session]
            project_id = project_id or session.project_id
        elif project_id and hasattr(self._session_repository, "find_by_project_id"):
            sessions = await self._session_repository.find_by_project_id(project_id)  # type: ignore[attr-defined]
        else:
            sessions = await self._session_repository.find_all()

        lessons = self._extract_from_sessions(sessions[: max(1, min(limit, 200))])
        proposal = EvolutionProposal.create(project_id, session_id, lessons)
        await self._proposal_repository.save(proposal)
        return {"proposal": self.proposal_to_dict(proposal), "lessons": lessons}

    async def create_claude_md_proposal(
        self,
        proposal_id: str,
        project_dir: str,
        lessons: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        proposal = await self._get_proposal(proposal_id)
        selected_lessons = lessons if lessons is not None else proposal.extracted_lessons
        current = await self._claude_md_revision_service.read_current(project_dir)
        current_content = current.get("content", "")
        active_revision = current.get("active_revision") or {}
        next_content = self._merge_lessons(current_content, selected_lessons)
        revision = await self._claude_md_revision_service.create_draft(
            project_dir=project_dir,
            content=next_content,
            base_revision_id=active_revision.get("id", ""),
            created_by="evolution",
        )
        proposal.extracted_lessons = list(selected_lessons)
        proposal.attach_revision(revision.id)
        await self._proposal_repository.save(proposal)
        return {"proposal": self.proposal_to_dict(proposal), "revision": self._revision_to_dict(revision)}

    async def list_proposals(self, project_id: str = "", project_dir: str = "") -> list[dict[str, Any]]:
        project_id = await self._resolve_project_id(project_id, project_dir)
        if not project_id:
            return []
        proposals = await self._proposal_repository.find_by_project_id(project_id)
        return [self.proposal_to_dict(item) for item in proposals]

    async def approve(self, proposal_id: str) -> dict[str, Any]:
        proposal = await self._get_proposal(proposal_id)
        proposal.approve()
        await self._proposal_repository.save(proposal)
        return self.proposal_to_dict(proposal)

    async def reject(self, proposal_id: str) -> dict[str, Any]:
        proposal = await self._get_proposal(proposal_id)
        proposal.reject()
        await self._proposal_repository.save(proposal)
        return self.proposal_to_dict(proposal)

    async def _resolve_project_id(self, project_id: str, project_dir: str) -> str:
        if project_id:
            return project_id
        if not project_dir:
            return ""
        project = await self._project_repository.find_by_dir_path(project_dir)
        return project.id if project else ""

    async def _get_proposal(self, proposal_id: str) -> EvolutionProposal:
        proposal = await self._proposal_repository.find_by_id(proposal_id)
        if proposal is None:
            raise BusinessException("Evolution proposal not found")
        return proposal

    @staticmethod
    def _extract_from_sessions(sessions) -> list[dict[str, Any]]:
        keywords = ("不要", "必须", "需要", "应该", "偏好", "继续", "修复", "问题", "约束", "规则", "不要再", "保留")
        lessons: list[dict[str, Any]] = []
        seen = set()
        for session in sessions:
            for index, message in enumerate(session.messages[-60:]):
                if message.message_type != MessageType.USER:
                    continue
                text = str(message.content.get("text", "")).strip()
                if not text or len(text) < 6:
                    continue
                if not any(keyword in text for keyword in keywords):
                    continue
                cleaned = " ".join(text.split())[:260]
                if cleaned in seen:
                    continue
                seen.add(cleaned)
                lessons.append({
                    "id": f"lesson-{len(lessons) + 1}",
                    "type": "feedback" if any(k in cleaned for k in ("不要", "偏好", "规则", "必须")) else "project",
                    "title": cleaned[:60],
                    "content": cleaned,
                    "source_session_id": session.session_id,
                    "source_message_index": index,
                })
                if len(lessons) >= 12:
                    return lessons
        if not lessons:
            lessons.append({
                "id": "lesson-1",
                "type": "project",
                "title": "总结当前会话经验",
                "content": "请结合最近会话补充可复用的项目协作规则，并在应用前由用户确认。",
                "source_session_id": "",
                "source_message_index": 0,
            })
        return lessons

    @staticmethod
    def _merge_lessons(content: str, lessons: list[dict[str, Any]]) -> str:
        bullets = []
        for lesson in lessons:
            text = str(lesson.get("content", "")).strip()
            if text:
                bullets.append(f"- {text}")
        section = "\n\n## Evolution Proposals\n\n" + "\n".join(bullets) + "\n"
        marker = "## Evolution Proposals"
        if marker not in content:
            return content.rstrip() + section
        head = content.split(marker, 1)[0].rstrip()
        return head + section

    @staticmethod
    def proposal_to_dict(proposal: EvolutionProposal) -> dict[str, Any]:
        return {
            "id": proposal.id,
            "project_id": proposal.project_id,
            "source_session_id": proposal.source_session_id,
            "state": proposal.state,
            "extracted_lessons": proposal.extracted_lessons,
            "proposed_claude_md_revision_id": proposal.proposed_claude_md_revision_id,
            "created_time": proposal.created_time.isoformat(),
            "updated_time": proposal.updated_time.isoformat(),
        }

    @staticmethod
    def _revision_to_dict(revision) -> dict[str, Any]:
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
