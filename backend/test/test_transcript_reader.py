from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from domain.project.model.project import Project
from domain.session.acl.transcript_reader import (
    InvalidTranscriptCursorError,
    TranscriptAccessError,
    TranscriptNotFoundError,
)
from domain.session.model.session import Session
from infr.client.transcript_reader import ClaudeTranscriptReader


def _project_root(claude_dir: Path, project_dir: Path) -> Path:
    key = str(project_dir.resolve()).replace("/", "-")
    root = claude_dir / "projects" / key
    root.mkdir(parents=True)
    return root


def _project(project_dir: Path) -> Project:
    return cast(Project, SimpleNamespace(id="project-1", dir_path=str(project_dir)))


def _session(project_dir: Path, sdk_session_id: str = "session") -> Session:
    return cast(
        Session,
        SimpleNamespace(
            project_id="project-1",
            project_dir=str(project_dir),
            sdk_session_id=sdk_session_id,
        ),
    )


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"".join(json.dumps(record).encode() + b"\n" for record in records)
    )


def test_returns_records_when_main_transcript_is_valid(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = _project_root(claude_dir, project_dir) / "session.jsonl"
    _write_records(transcript, [{"type": "user"}, {"type": "assistant"}])

    page = ClaudeTranscriptReader(claude_dir).read(
        _project(project_dir), _session(project_dir), limit=10
    )

    assert page.records == ({"type": "user"}, {"type": "assistant"})
    assert page.next_cursor == transcript.stat().st_size
    assert page.has_more is False


def test_returns_records_when_session_uses_dedicated_execution_workspace(
    tmp_path: Path,
) -> None:
    # Arrange
    project_dir = tmp_path / "project"
    execution_dir = tmp_path / "team-agent" / "executions" / "execution-1"
    project_dir.mkdir()
    execution_dir.mkdir(parents=True)
    claude_dir = tmp_path / ".claude"
    transcript = _project_root(claude_dir, execution_dir) / "session.jsonl"
    _write_records(transcript, [{"type": "assistant"}])

    # Act
    page = ClaudeTranscriptReader(claude_dir).read(
        _project(project_dir),
        _session(execution_dir),
    )

    # Assert
    assert page.records == ({"type": "assistant"},)


def test_rejects_session_when_project_id_does_not_match(tmp_path: Path) -> None:
    # Arrange
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    session = cast(
        Session,
        SimpleNamespace(
            project_id="another-project",
            project_dir=str(project_dir),
            sdk_session_id="session",
        ),
    )

    # Act / Assert
    with pytest.raises(TranscriptAccessError):
        ClaudeTranscriptReader(tmp_path / ".claude").read(
            _project(project_dir),
            session,
        )


def test_returns_records_when_subagent_belongs_to_session(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = (
        _project_root(claude_dir, project_dir)
        / "session"
        / "subagents"
        / "agent-worker.jsonl"
    )
    _write_records(transcript, [{"agent": True}])

    page = ClaudeTranscriptReader(claude_dir).read(
        _project(project_dir),
        _session(project_dir),
        transcript_path=str(transcript),
    )

    assert page.records == ({"agent": True},)


def test_returns_next_cursor_when_limit_is_reached(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = _project_root(claude_dir, project_dir) / "session.jsonl"
    _write_records(transcript, [{"n": 1}, {"n": 2}, {"n": 3}])
    reader = ClaudeTranscriptReader(claude_dir)

    first = reader.read(_project(project_dir), _session(project_dir), limit=2)
    second = reader.read(
        _project(project_dir),
        _session(project_dir),
        cursor=first.next_cursor,
        limit=2,
    )

    assert first.records == ({"n": 1}, {"n": 2})
    assert first.has_more is True
    assert second.records == ({"n": 3},)
    assert second.has_more is False


def test_retries_partial_tail_when_line_is_completed(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = _project_root(claude_dir, project_dir) / "session.jsonl"
    complete = b'{"n": 1}\n'
    transcript.write_bytes(complete + b'{"n":')
    reader = ClaudeTranscriptReader(claude_dir)

    first = reader.read(_project(project_dir), _session(project_dir))
    with transcript.open("ab") as stream:
        stream.write(b"2}\n")
    second = reader.read(
        _project(project_dir),
        _session(project_dir),
        cursor=first.next_cursor,
    )

    assert first.records == ({"n": 1},)
    assert first.next_cursor == len(complete)
    assert first.incomplete_tail is True
    assert second.records == ({"n": 2},)


def test_warns_and_continues_when_complete_line_is_invalid(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = _project_root(claude_dir, project_dir) / "session.jsonl"
    transcript.write_bytes(b'{"n": 1}\nnot-json\n{"n": 2}\n')

    with caplog.at_level(logging.WARNING):
        page = ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir), _session(project_dir)
        )

    assert page.records == ({"n": 1}, {"n": 2})
    assert len(page.warnings) == 1
    assert "invalid transcript line" in caplog.text


def test_rejects_path_when_relative_path_traverses_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    _project_root(claude_dir, project_dir)

    with pytest.raises(TranscriptAccessError):
        ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir),
            _session(project_dir),
            transcript_path="../other.jsonl",
        )


def test_rejects_path_when_transcript_belongs_to_another_project(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    other_project = tmp_path / "other-project"
    project_dir.mkdir()
    other_project.mkdir()
    claude_dir = tmp_path / ".claude"
    _project_root(claude_dir, project_dir)
    other = _project_root(claude_dir, other_project) / "session.jsonl"
    _write_records(other, [{"secret": True}])

    with pytest.raises(TranscriptAccessError):
        ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir),
            _session(project_dir),
            transcript_path=str(other),
        )


def test_rejects_path_when_subagent_belongs_to_another_session(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = (
        _project_root(claude_dir, project_dir)
        / "other-session"
        / "subagents"
        / "agent-worker.jsonl"
    )
    _write_records(transcript, [{"secret": True}])

    with pytest.raises(TranscriptAccessError):
        ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir),
            _session(project_dir),
            transcript_path=str(transcript),
        )


def test_rejects_path_when_transcript_is_symlink(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    root = _project_root(claude_dir, project_dir)
    target = root / "session.jsonl"
    _write_records(target, [{"n": 1}])
    link = root / "session" / "subagents" / "agent-link.jsonl"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)

    with pytest.raises(TranscriptAccessError):
        ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir),
            _session(project_dir),
            transcript_path=str(link),
        )


def test_raises_explicit_error_when_transcript_is_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    _project_root(claude_dir, project_dir)

    with pytest.raises(TranscriptNotFoundError):
        ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir), _session(project_dir)
        )


def test_rejects_cursor_when_not_at_line_boundary(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = tmp_path / ".claude"
    transcript = _project_root(claude_dir, project_dir) / "session.jsonl"
    _write_records(transcript, [{"n": 1}])

    with pytest.raises(InvalidTranscriptCursorError):
        ClaudeTranscriptReader(claude_dir).read(
            _project(project_dir), _session(project_dir), cursor=2
        )
