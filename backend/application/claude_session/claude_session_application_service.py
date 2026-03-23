from __future__ import annotations

from typing import Any

from domain.session.acl.claude_session_manager import ClaudeSessionManager


class ClaudeSessionApplicationService:

    def __init__(self, session_manager: ClaudeSessionManager) -> None:
        self._session_manager = session_manager

    def list_claude_sessions(
        self,
        directory: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List Claude Code sessions."""
        return self._session_manager.list_claude_sessions(
            directory=directory,
            limit=limit,
        )

    def rename_claude_session(
        self,
        session_id: str,
        title: str,
        directory: str | None = None,
    ) -> None:
        """Rename a Claude Code session."""
        self._session_manager.rename_claude_session(
            session_id=session_id,
            title=title,
            directory=directory,
        )

    def delete_claude_session(
        self,
        session_id: str,
        directory: str | None = None,
    ) -> bool:
        """Delete a Claude Code session's JSONL file."""
        return self._session_manager.delete_claude_session(
            session_id=session_id,
            directory=directory,
        )
