from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import BinaryIO

from domain.project.model.project import Project
from domain.session.acl.transcript_reader import (
    InvalidTranscriptCursorError,
    TranscriptAccessError,
    TranscriptNotFoundError,
    TranscriptPage,
    TranscriptReader,
    TranscriptUnreadableError,
    TranscriptWarning,
)
from domain.session.model.session import Session

logger = logging.getLogger(__name__)


class ClaudeTranscriptReader(TranscriptReader):
    def __init__(self, claude_dir: Path | None = None) -> None:
        self._claude_dir = (claude_dir or Path.home() / ".claude").resolve()

    def read(
        self,
        project: Project,
        session: Session,
        *,
        transcript_path: str | None = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> TranscriptPage:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if cursor < 0:
            raise InvalidTranscriptCursorError("cursor must not be negative")

        path = self._resolve_transcript(project, session, transcript_path)
        try:
            file_size = path.stat().st_size
            transcript = path.open("rb")
        except FileNotFoundError as exc:
            raise TranscriptNotFoundError(f"transcript not found: {path}") from exc
        except PermissionError as exc:
            raise TranscriptUnreadableError(f"transcript is unreadable: {path}") from exc

        with transcript:
            if cursor > file_size:
                raise InvalidTranscriptCursorError(
                    "cursor is beyond the end of the transcript"
                )
            self._validate_cursor(transcript, cursor)
            return self._read_page(transcript, path, cursor, limit, file_size)

    def _resolve_transcript(
        self,
        project: Project,
        session: Session,
        transcript_path: str | None,
    ) -> Path:
        if session.project_id != project.id:
            raise TranscriptAccessError("session does not belong to the current project")
        # Team/card executions keep the parent Project aggregate but run in a
        # dedicated workspace. Claude keys its transcript directory from the
        # session's actual working directory, not from the parent project root.
        project_dir = Path(session.project_dir or project.dir_path).expanduser().resolve()
        if not session.sdk_session_id:
            raise TranscriptAccessError("session has no Claude SDK session id")

        project_key = str(project_dir).replace(os.sep, "-")
        project_root = self._claude_dir / "projects" / project_key
        main_path = project_root / f"{session.sdk_session_id}.jsonl"
        candidate = Path(transcript_path).expanduser() if transcript_path else main_path
        if not candidate.is_absolute():
            candidate = project_root / candidate

        self._reject_lexical_escape_or_symlink(project_root, candidate)
        resolved_root = project_root.resolve()
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(resolved_root):
            raise TranscriptAccessError("transcript path escapes the current project")

        resolved_main = main_path.resolve(strict=False)
        relative = resolved.relative_to(resolved_root)
        is_main = resolved == resolved_main
        is_subagent = (
            len(relative.parts) == 3
            and relative.parts[0] == session.sdk_session_id
            and relative.parts[1] == "subagents"
            and relative.name.startswith("agent-")
            and relative.suffix == ".jsonl"
        )
        if not (is_main or is_subagent):
            raise TranscriptAccessError(
                "transcript is not the current session or one of its subagents"
            )
        return resolved

    @staticmethod
    def _reject_lexical_escape_or_symlink(project_root: Path, candidate: Path) -> None:
        absolute_root = Path(os.path.abspath(project_root))
        absolute_candidate = Path(os.path.abspath(candidate))
        if not absolute_candidate.is_relative_to(absolute_root):
            raise TranscriptAccessError("transcript path escapes the current project")

        current = absolute_root
        for part in absolute_candidate.relative_to(absolute_root).parts:
            current /= part
            if current.is_symlink():
                raise TranscriptAccessError("symlink transcript paths are not allowed")

    @staticmethod
    def _validate_cursor(transcript: BinaryIO, cursor: int) -> None:
        if cursor == 0:
            return
        transcript.seek(cursor - 1)
        if transcript.read(1) != b"\n":
            raise InvalidTranscriptCursorError("cursor is not on a line boundary")

    @staticmethod
    def _read_page(
        transcript: BinaryIO,
        path: Path,
        cursor: int,
        limit: int,
        file_size: int,
    ) -> TranscriptPage:
        records: list[dict[str, object]] = []
        warnings: list[TranscriptWarning] = []
        incomplete_tail = False
        transcript.seek(cursor)
        next_cursor = cursor

        while len(records) < limit:
            line_offset = transcript.tell()
            line = transcript.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                incomplete_tail = True
                break
            next_cursor = transcript.tell()
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("transcript record must be a JSON object")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                warnings.append(TranscriptWarning(line_offset, str(exc)))
                logger.warning(
                    "invalid transcript line",
                    extra={"transcript_path": str(path), "byte_offset": line_offset},
                )
                continue
            records.append(value)

        return TranscriptPage(
            records=tuple(records),
            next_cursor=next_cursor,
            has_more=next_cursor < file_size and not incomplete_tail,
            incomplete_tail=incomplete_tail,
            warnings=tuple(warnings),
        )


FileTranscriptReader = ClaudeTranscriptReader
