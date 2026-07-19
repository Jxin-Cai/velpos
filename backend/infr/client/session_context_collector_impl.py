import mimetypes
from pathlib import Path
from collections.abc import Iterable, Iterator
from typing import Any

from domain.session.model.message import Message
from domain.session.repository.session_repository import SessionRepository
from domain.team.acl.session_context_collector import (
    SessionArtifact,
    SessionContext,
    SessionContextCollector,
)


class SessionContextCollectorImpl(SessionContextCollector):
    _ARTIFACT_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
    _MAX_SUMMARY_CHARS = 24_000

    def __init__(self, session_repository: SessionRepository) -> None:
        self._session_repository = session_repository

    async def collect(self, session_id: str) -> SessionContext:
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        return SessionContext(
            summary=self._build_summary(session.messages),
            source_session_id=session.session_id,
            sdk_session_id=session.sdk_session_id,
            artifacts=self._collect_artifacts(session.messages, session.project_dir),
        )

    @classmethod
    def _build_summary(cls, messages: Iterable[Message]) -> str:
        text_parts = []
        for message in messages:
            text = cls._extract_text(message.content)
            if text:
                text_parts.append(f"### {message.message_type.value}\n{text}")
        summary = "\n\n".join(text_parts)
        if len(summary) <= cls._MAX_SUMMARY_CHARS:
            return summary
        return "[较早的会话内容已截断]\n\n" + summary[-cls._MAX_SUMMARY_CHARS:]

    @classmethod
    def _collect_artifacts(
        cls,
        messages: Iterable[Message],
        project_dir: str,
    ) -> tuple[SessionArtifact, ...]:
        if not project_dir:
            return ()
        workspace = Path(project_dir).expanduser().resolve()
        artifacts: dict[str, SessionArtifact] = {}
        for message in messages:
            for tool_name, raw_path in cls._iter_artifact_tool_paths(message.content):
                candidate = Path(raw_path).expanduser()
                resolved = (workspace / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
                if not resolved.is_relative_to(workspace) or not resolved.is_file():
                    continue
                path = str(resolved)
                media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
                artifacts[path] = SessionArtifact(
                    path=path,
                    description=f"由 {tool_name} 工具生成或修改",
                    artifact_type=media_type,
                )
        # Claude's persisted assistant message may only contain the rendered
        # text, while the actual Write/Edit tool input is intentionally not
        # retained. The execution workspace is the source of truth for those
        # files, so include its user-created files as handoff artifacts too.
        for candidate in workspace.rglob("*"):
            if (
                not candidate.is_file()
                or candidate.is_symlink()
                or candidate.name == "CLAUDE.md"
                or any(part in {".claude", ".velpos"} for part in candidate.relative_to(workspace).parts)
            ):
                continue
            path = str(candidate.resolve())
            artifacts.setdefault(
                path,
                SessionArtifact(
                    path=path,
                    description="前序 Agent 执行目录中的产物",
                    artifact_type=mimetypes.guess_type(path)[0] or "application/octet-stream",
                ),
            )
        return tuple(artifacts[path] for path in sorted(artifacts))

    @classmethod
    def _iter_artifact_tool_paths(cls, value: Any) -> Iterator[tuple[str, str]]:
        if isinstance(value, list):
            for item in value:
                yield from cls._iter_artifact_tool_paths(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("type") == "tool_use" and value.get("name") in cls._ARTIFACT_TOOLS:
            tool_input = value.get("input")
            if isinstance(tool_input, dict):
                raw_path = tool_input.get("file_path") or tool_input.get("path")
                if isinstance(raw_path, str) and raw_path.strip():
                    yield str(value["name"]), raw_path
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                yield from cls._iter_artifact_tool_paths(nested)

    @classmethod
    def _extract_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(
                text for item in content if (text := cls._extract_text(item))
            )
        if not isinstance(content, dict):
            return ""

        direct_text = content.get("text") or content.get("content")
        if direct_text is not None:
            return cls._extract_text(direct_text)

        return "\n".join(
            text
            for key in ("message", "result", "data")
            if key in content and (text := cls._extract_text(content[key]))
        )
