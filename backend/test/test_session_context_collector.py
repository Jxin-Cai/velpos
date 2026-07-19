from pathlib import Path

import pytest

from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from infr.client.session_context_collector_impl import SessionContextCollectorImpl


class _SessionRepositoryStub:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def find_by_id(self, session_id: str) -> Session | None:
        return self._session if session_id == self._session.session_id else None


@pytest.mark.asyncio
async def test_collects_sdk_session_and_written_files_when_session_has_artifacts(
    tmp_path: Path,
) -> None:
    # Arrange
    artifact = tmp_path / "result.md"
    artifact.write_text("done", encoding="utf-8")
    session = Session.create(project_dir=str(tmp_path))
    session.update_sdk_session_id("claude-session-123")
    session.add_message(Message.create(MessageType.USER, {"text": "Create the result"}))
    session.add_message(
        Message.create(
            MessageType.ASSISTANT,
            {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "result.md", "content": "done"},
                    },
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "not-an-artifact.md"},
                    },
                ]
            },
        )
    )
    collector = SessionContextCollectorImpl(_SessionRepositoryStub(session))

    # Act
    context = await collector.collect(session.session_id)

    # Assert
    assert context.source_session_id == session.session_id
    assert context.sdk_session_id == "claude-session-123"
    assert [item.path for item in context.artifacts] == [str(artifact)]


@pytest.mark.asyncio
async def test_collects_workspace_file_when_tool_input_is_not_persisted(
    tmp_path: Path,
) -> None:
    # Arrange
    artifact = tmp_path / "rendered-result.md"
    artifact.write_text("done", encoding="utf-8")
    session = Session.create(project_dir=str(tmp_path))
    collector = SessionContextCollectorImpl(_SessionRepositoryStub(session))

    # Act
    context = await collector.collect(session.session_id)

    # Assert
    assert [item.path for item in context.artifacts] == [str(artifact)]


@pytest.mark.asyncio
async def test_ignores_written_file_when_path_escapes_session_workspace(
    tmp_path: Path,
) -> None:
    # Arrange
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    session = Session.create(project_dir=str(workspace))
    session.add_message(
        Message.create(
            MessageType.ASSISTANT,
            {
                "content": [{
                    "type": "tool_use",
                    "name": "Write",
                    "input": {"file_path": str(outside)},
                }]
            },
        )
    )
    collector = SessionContextCollectorImpl(_SessionRepositoryStub(session))

    # Act
    context = await collector.collect(session.session_id)

    # Assert
    assert context.artifacts == ()
