from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ClaudeSessionManager(ABC):

    @abstractmethod
    def list_claude_sessions(
        self,
        directory: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List Claude Code sessions from ~/.claude/projects/.

        Args:
            directory: Project directory to filter by. If None, lists all.
            limit: Maximum number of sessions to return.

        Returns:
            List of session info dicts sorted by last_modified descending.
        """
        ...

    @abstractmethod
    def rename_claude_session(
        self,
        session_id: str,
        title: str,
        directory: str | None = None,
    ) -> None:
        """Rename a Claude Code session.

        Args:
            session_id: UUID of the Claude session.
            title: New session title.
            directory: Project directory path.
        """
        ...

    @abstractmethod
    def delete_claude_session(
        self,
        session_id: str,
        directory: str | None = None,
    ) -> bool:
        """Delete a Claude Code session's JSONL file.

        Args:
            session_id: UUID of the Claude session.
            directory: Project directory path.

        Returns:
            True if the file was found and deleted, False otherwise.
        """
        ...

    @abstractmethod
    def delete_all_sessions_in_dir(
        self,
        directory: str,
    ) -> int:
        """Delete ALL Claude Code session JSONL files for a project directory.

        Used during project deletion to prevent orphaned CC sessions from
        being re-discovered on next page refresh.

        Args:
            directory: Project directory path.

        Returns:
            Number of JSONL files deleted.
        """
        ...

    @abstractmethod
    def get_claude_session_messages(
        self,
        session_id: str,
        directory: str | None = None,
    ) -> list:
        """Get messages from a Claude Code session.

        Args:
            session_id: UUID of the Claude session.
            directory: Project directory path.

        Returns:
            List of SessionMessage objects from SDK.
        """
        ...
