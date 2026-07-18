from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from domain.project.model.project import Project
from domain.session.model.session import Session


class TranscriptReaderError(Exception):
    """Base error raised while reading a Claude transcript."""


class TranscriptNotFoundError(TranscriptReaderError):
    """The requested transcript does not exist."""


class TranscriptUnreadableError(TranscriptReaderError):
    """The requested transcript cannot be read."""


class TranscriptAccessError(TranscriptReaderError):
    """The requested path violates the project or session boundary."""


class InvalidTranscriptCursorError(TranscriptReaderError):
    """The cursor is invalid for the current transcript."""


@dataclass(frozen=True)
class TranscriptWarning:
    byte_offset: int
    message: str


@dataclass(frozen=True)
class TranscriptPage:
    records: tuple[dict[str, Any], ...]
    next_cursor: int
    has_more: bool
    incomplete_tail: bool
    warnings: tuple[TranscriptWarning, ...] = ()


class TranscriptReader(ABC):
    @abstractmethod
    def read(
        self,
        project: Project,
        session: Session,
        *,
        transcript_path: str | None = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> TranscriptPage:
        """Read complete JSONL records using a byte cursor."""
        ...
