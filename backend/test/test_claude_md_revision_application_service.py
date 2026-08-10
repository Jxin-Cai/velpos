from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from application.memory.claude_md_revision_application_service import (
    ClaudeMdRevisionApplicationService,
)
from domain.memory.model.claude_md_revision import ClaudeMdRevision
from domain.memory.model.claude_md_revision_event import ClaudeMdRevisionEvent
from domain.memory.model.claude_md_revision_state import ClaudeMdRevisionState
from domain.project.model.project import Project


class InMemoryClaudeMdRevisionRepository:
    def __init__(self, revisions: list[ClaudeMdRevision]) -> None:
        self.revisions = {revision.id: revision for revision in revisions}
        self.events: list[ClaudeMdRevisionEvent] = []
        self.saved_ids: list[str] = []

    async def find_by_id(self, revision_id: str) -> ClaudeMdRevision | None:
        return self.revisions.get(revision_id)

    async def find_by_project_id(self, project_id: str) -> list[ClaudeMdRevision]:
        return [revision for revision in self.revisions.values() if revision.project_id == project_id]

    async def save(self, revision: ClaudeMdRevision) -> None:
        self.revisions[revision.id] = revision
        self.saved_ids.append(revision.id)

    async def save_event(self, event: ClaudeMdRevisionEvent) -> None:
        self.events.append(event)


class InMemoryProjectRepository:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.saved_projects: list[Project] = []

    async def find_by_dir_path(self, dir_path: str) -> Project | None:
        return self.project if self.project.dir_path == dir_path else None

    async def save(self, project: Project) -> None:
        self.project = project
        self.saved_projects.append(project)


def _revision(
    revision_id: str,
    project_id: str,
    version_no: int,
    state: ClaudeMdRevisionState,
    content: str,
    base_revision_id: str = "",
    base_file_hash: str = "",
) -> ClaudeMdRevision:
    now = datetime.now()
    return ClaudeMdRevision.reconstitute(
        id=revision_id,
        project_id=project_id,
        version_no=version_no,
        state=state,
        content=content,
        content_hash=ClaudeMdRevision.hash_content(content),
        base_revision_id=base_revision_id,
        base_file_hash=base_file_hash,
        created_by="test",
        created_time=now,
        applied_time=now if state == ClaudeMdRevisionState.APPLIED else None,
    )


@pytest.mark.asyncio
async def test_leaves_only_new_revision_applied_when_multiple_historical_revisions_are_applied(
    tmp_path: Path,
) -> None:
    # Arrange
    project = Project.reconstitute(
        id="project-1",
        name="Project",
        dir_path=str(tmp_path),
        agents={},
    )
    current_content = "existing instructions"
    (tmp_path / "CLAUDE.md").write_text(current_content, encoding="utf-8")
    current_hash = ClaudeMdRevision.hash_content(current_content)
    old_revision_one = _revision("old-001", project.id, 1, ClaudeMdRevisionState.APPLIED, "old one")
    old_revision_two = _revision("old-002", project.id, 2, ClaudeMdRevisionState.APPLIED, "old two")
    new_revision = _revision(
        "new-003",
        project.id,
        3,
        ClaudeMdRevisionState.APPROVED,
        "new instructions",
        base_revision_id=old_revision_two.id,
        base_file_hash=current_hash,
    )
    revision_repository = InMemoryClaudeMdRevisionRepository(
        [old_revision_one, old_revision_two, new_revision]
    )
    project_repository = InMemoryProjectRepository(project)
    service = ClaudeMdRevisionApplicationService(revision_repository, project_repository)

    # Act
    result = await service.apply(
        revision_id=new_revision.id,
        project_dir=str(tmp_path),
        expected_base_revision_id=old_revision_two.id,
        expected_file_hash=current_hash,
    )

    # Assert
    assert result.conflict is False
    assert [
        revision.id
        for revision in revision_repository.revisions.values()
        if revision.state == ClaudeMdRevisionState.APPLIED
    ] == [new_revision.id]
    assert revision_repository.revisions[old_revision_one.id].state == ClaudeMdRevisionState.SUPERSEDED
    assert revision_repository.revisions[old_revision_two.id].state == ClaudeMdRevisionState.SUPERSEDED
    superseded_events = [
        event
        for event in revision_repository.events
        if event.to_state == ClaudeMdRevisionState.SUPERSEDED.value
    ]
    assert {event.revision_id for event in superseded_events} == {
        old_revision_one.id,
        old_revision_two.id,
    }
    assert project.active_claude_md_revision_id == new_revision.id


def test_supersedes_applied_revision_when_supersede_is_called() -> None:
    # Arrange
    revision = _revision(
        "applied-001",
        "project-1",
        1,
        ClaudeMdRevisionState.APPLIED,
        "instructions",
    )

    # Act
    revision.supersede()

    # Assert
    assert revision.state == ClaudeMdRevisionState.SUPERSEDED
