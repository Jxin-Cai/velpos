from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import list_sessions, rename_session, get_session_messages

from domain.session.acl.claude_session_manager import ClaudeSessionManager

logger = logging.getLogger(__name__)


class ClaudeSessionManagerImpl(ClaudeSessionManager):

    def list_claude_sessions(
        self,
        directory: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List Claude Code sessions from ~/.claude/projects/."""
        sessions = list_sessions(directory=directory, limit=limit)
        return [
            {
                "session_id": s.session_id,
                "summary": s.summary,
                "last_modified": s.last_modified,
                "file_size": s.file_size,
                "custom_title": s.custom_title,
                "first_prompt": s.first_prompt,
                "git_branch": s.git_branch,
                "cwd": s.cwd,
                "tag": s.tag,
                "created_at": s.created_at,
            }
            for s in sessions
        ]

    def rename_claude_session(
        self,
        session_id: str,
        title: str,
        directory: str | None = None,
    ) -> None:
        """Rename a Claude Code session by appending a custom-title entry."""
        logger.info("rename_claude_session: %s -> %s", session_id, title)
        rename_session(
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
        from claude_agent_sdk._internal.sessions import (
            _canonicalize_path,
            _find_project_dir,
            _get_projects_dir,
        )

        file_name = f"{session_id}.jsonl"

        if directory:
            canonical = _canonicalize_path(directory)
            proj_dir = _find_project_dir(canonical)
            if proj_dir is not None:
                jsonl_path = proj_dir / file_name
                if jsonl_path.exists():
                    try:
                        jsonl_path.unlink()
                        logger.info("已删除 CC 会话 JSONL: %s", jsonl_path)
                        return True
                    except OSError:
                        logger.warning("删除 CC 会话 JSONL 失败: %s", jsonl_path, exc_info=True)
                        return False

        # Fallback: search all project directories
        projects_dir = _get_projects_dir()
        try:
            for entry in projects_dir.iterdir():
                if not entry.is_dir():
                    continue
                jsonl_path = entry / file_name
                if jsonl_path.exists():
                    try:
                        jsonl_path.unlink()
                        logger.info("已删除 CC 会话 JSONL: %s", jsonl_path)
                        return True
                    except OSError:
                        logger.warning("删除 CC 会话 JSONL 失败: %s", jsonl_path, exc_info=True)
                        return False
        except OSError:
            pass

        return False

    def get_claude_session_messages(
        self,
        session_id: str,
        directory: str | None = None,
    ) -> list:
        """Get messages from a Claude Code session."""
        return get_session_messages(
            session_id=session_id,
            directory=directory,
        )

    def delete_all_sessions_in_dir(
        self,
        directory: str,
    ) -> int:
        """Delete ALL Claude Code session JSONL files for a project directory."""
        from claude_agent_sdk._internal.sessions import (
            _canonicalize_path,
            _find_project_dir,
        )

        canonical = _canonicalize_path(directory)
        proj_dir = _find_project_dir(canonical)
        if proj_dir is None or not proj_dir.is_dir():
            return 0

        count = 0
        try:
            for jsonl_path in proj_dir.glob("*.jsonl"):
                try:
                    jsonl_path.unlink()
                    count += 1
                    logger.info("已删除 CC 会话 JSONL: %s", jsonl_path)
                except OSError:
                    logger.warning("删除 CC 会话 JSONL 失败: %s", jsonl_path, exc_info=True)
        except OSError:
            logger.warning("遍历项目目录失败: %s", proj_dir, exc_info=True)

        return count
