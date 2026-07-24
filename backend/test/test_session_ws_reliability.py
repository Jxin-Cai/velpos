from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from application.session.session_query_engine import QueueMessageOutcome

os.environ.setdefault("CLAUDE_CLI_PATH", "/usr/bin/true")

from ohs.ws.session_ws import _handle_send_prompt


def _context(session) -> SimpleNamespace:
    return SimpleNamespace(
        session_id="session1",
        websocket=SimpleNamespace(send_json=AsyncMock()),
        service=SimpleNamespace(
            get_session=AsyncMock(return_value=session),
            is_agent_connected=lambda _session_id: True,
            ensure_session_idle=AsyncMock(),
            queue_message=AsyncMock(return_value=QueueMessageOutcome.QUEUED),
        ),
        attachment_service=SimpleNamespace(
            save_base64_attachment=AsyncMock(),
        ),
        submit_query_background=AsyncMock(),
    )


def _session(messages: list[Message], *, is_running: bool) -> SimpleNamespace:
    return SimpleNamespace(
        name="regular session",
        messages=messages,
        is_running=is_running,
        project_id="project1",
        project_dir="/tmp/project",
    )


@pytest.mark.asyncio
async def test_does_not_resave_attachment_when_completed_prompt_is_retried():
    # Arrange
    user = Message.create(
        MessageType.USER,
        {
            "message_id": "message-1",
            "raw_prompt": "review",
            "text": "review\n\n[Attachment: report.txt path=/tmp/report.txt]",
            "attachments": [
                {
                    "filename": "report.txt",
                    "mime_type": "text/plain",
                    "path": "/tmp/report.txt",
                }
            ],
        },
    )
    result = Message.create(MessageType.RESULT, {"is_error": False})
    ctx = _context(_session([user, result], is_running=False))

    # Act
    await _handle_send_prompt(
        ctx,
        {
            "action": "send_prompt",
            "message_id": "message-1",
            "prompt": "review",
            "attachments": [
                {
                    "name": "report.txt",
                    "mime_type": "text/plain",
                    "data": "cmVwb3J0",
                }
            ],
        },
    )

    # Assert
    ctx.attachment_service.save_base64_attachment.assert_not_awaited()
    ctx.submit_query_background.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_queue_duplicate_when_original_prompt_is_running():
    # Arrange
    user = Message.create(
        MessageType.USER,
        {
            "message_id": "message-2",
            "raw_prompt": "continue",
            "text": "continue",
            "attachments": [],
        },
    )
    ctx = _context(_session([user], is_running=True))

    # Act
    await _handle_send_prompt(
        ctx,
        {
            "action": "send_prompt",
            "message_id": "message-2",
            "prompt": "continue",
        },
    )

    # Assert
    ctx.service.queue_message.assert_not_awaited()
    ctx.submit_query_background.assert_not_awaited()


@pytest.mark.asyncio
async def test_resumes_incomplete_prompt_when_session_is_idle():
    # Arrange
    attachments = [
        {
            "filename": "image.png",
            "mime_type": "image/png",
            "path": "/tmp/image.png",
        }
    ]
    user = Message.create(
        MessageType.USER,
        {
            "message_id": "message-3",
            "raw_prompt": "inspect",
            "text": "inspect\n\n[Image: /tmp/image.png]",
            "attachments": attachments,
        },
    )
    ctx = _context(_session([user], is_running=False))

    # Act
    await _handle_send_prompt(
        ctx,
        {
            "action": "send_prompt",
            "message_id": "message-3",
            "prompt": "inspect",
            "images": [{"name": "image.png", "data": "aW1hZ2U="}],
        },
    )
    await asyncio.sleep(0)

    # Assert
    submitted = ctx.submit_query_background.await_args.args[0]
    assert submitted.attachments == attachments
    assert submitted.image_paths == ["/tmp/image.png"]


@pytest.mark.asyncio
async def test_starts_prompt_when_running_status_is_stale_during_finalization():
    # Arrange
    ctx = _context(_session([], is_running=True))
    ctx.service.queue_message.return_value = QueueMessageOutcome.RUN_IMMEDIATELY

    # Act
    await _handle_send_prompt(
        ctx,
        {
            "action": "send_prompt",
            "message_id": "message-after-finish",
            "prompt": "next request",
        },
    )
    await asyncio.sleep(0)

    # Assert
    submitted = ctx.submit_query_background.await_args.args[0]
    assert submitted.client_message_id == "message-after-finish"
    ctx.websocket.send_json.assert_awaited_with({
        "event": "prompt_started",
        "message_id": "message-after-finish",
        "prompt": "next request",
        "image_count": 0,
        "attachments": [],
    })
