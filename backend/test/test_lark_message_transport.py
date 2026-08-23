from __future__ import annotations

import asyncio
import gc
import json
import sys
import threading
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.im_binding.im_channel_application_service import (
    ImChannelApplicationService,
)
from application.session.session_query_engine import SessionQueryEngine
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    MessageSegment,
    OutboundMessage,
    SegmentType,
)
from infr.im.lark.lark_adapter import (
    LarkAdapter,
    _segment_to_lark_message,
    _WsConnection,
)
from infr.im.lark.lark_message import (
    LarkMessageType,
    LarkOutboundMessage,
    parse_inbound_content,
)
from ohs.session_event_coordinator import SessionEventCoordinator


def _binding() -> ImBinding:
    return ImBinding.reconstitute(
        id="binding1",
        session_id="session1",
        im_user_id="",
        im_token="",
        binding_status=BindingStatus.BOUND,
        friend_user_id="",
        qr_code_data="",
        created_at=datetime.now(),
        channel_type=ImChannelType.LARK,
        channel_id="channel1",
        config={"app_id": "app", "app_secret": "secret", "open_id": "user"},
    )


def test_extracts_text_when_rich_text_is_received() -> None:
    # Arrange
    raw = json.dumps(
        {
            "zh_cn": {
                "title": "进度",
                "content": [[{"tag": "text", "text": "已经完成"}]],
            }
        }
    )

    # Act
    parsed = parse_inbound_content("post", raw)

    # Assert
    assert parsed.text == "进度\n已经完成"


def test_preserves_image_key_when_rich_text_contains_image() -> None:
    # Arrange
    raw = json.dumps(
        {
            "zh_cn": {
                "content": [[{"tag": "img", "image_key": "img-key"}]],
            }
        }
    )

    # Act
    parsed = parse_inbound_content("post", raw)

    # Assert
    assert parsed.resources == (("image", "img-key"),)


@pytest.mark.parametrize(
    "message_type",
    [
        "file",
        "audio",
        "media",
    ],
)
def test_preserves_file_key_when_media_is_received(
    message_type: str,
) -> None:
    # Arrange
    raw = json.dumps({"file_key": "file-key", "file_name": "sample.bin"})

    # Act
    parsed = parse_inbound_content(message_type, raw)

    # Assert
    assert parsed.resources == (("file", "file-key"),)


def test_extracts_readable_text_when_card_is_received() -> None:
    # Arrange
    raw = json.dumps(
        {
            "header": {"title": {"tag": "plain_text", "content": "审批"}},
            "elements": [{"tag": "markdown", "content": "请确认"}],
        }
    )

    # Act
    parsed = parse_inbound_content("interactive", raw)

    # Assert
    assert parsed.text == "审批\n请确认"


def test_encodes_card_when_interactive_message_is_created() -> None:
    # Arrange
    payload = LarkOutboundMessage(
        message_type=LarkMessageType.INTERACTIVE,
        content={"elements": [{"tag": "markdown", "content": "hello"}]},
    )

    # Act
    encoded = json.loads(payload.encoded_content())

    # Assert
    assert encoded["elements"][0]["content"] == "hello"


@pytest.mark.asyncio
async def test_sends_card_through_sdk_when_interactive_payload_is_provided() -> None:
    # Arrange
    create = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="card-message"),
        )
    )
    adapter = LarkAdapter()
    adapter._get_sdk_client = Mock(
        return_value=SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(message=SimpleNamespace(acreate=create)),
            )
        )
    )

    # Act
    receipt = await adapter.send(
        _binding(),
        OutboundMessage(
            segments=(
                MessageSegment.of_card(
                    {"elements": [{"tag": "markdown", "content": "hello"}]},
                ),
            ),
        ),
    )

    # Assert
    assert receipt.external_message_id == "card-message"


@pytest.mark.asyncio
async def test_uploads_image_before_sending_when_image_payload_is_provided(
    tmp_path,
) -> None:
    # Arrange
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    upload = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(image_key="image-key"),
        )
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="image-message"),
        )
    )
    client = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                image=SimpleNamespace(acreate=upload),
                message=SimpleNamespace(acreate=create),
            )
        )
    )
    adapter = LarkAdapter()
    adapter._get_sdk_client = Mock(return_value=client)

    # Act
    await adapter.send(
        _binding(),
        OutboundMessage(
            segments=(
                MessageSegment.of_media(
                    SegmentType.IMAGE, path=str(image_path), mime_type="image/png",
                ),
            ),
        ),
    )

    # Assert
    assert json.loads(create.await_args.args[0].body.content) == {
        "image_key": "image-key"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("segment_type", "expected_message_type"),
    [
        (SegmentType.FILE, "file"),
        (SegmentType.AUDIO, "audio"),
    ],
)
async def test_uploads_file_before_sending_when_file_payload_is_provided(
    tmp_path,
    segment_type: SegmentType,
    expected_message_type: str,
) -> None:
    # Arrange
    file_path = tmp_path / (
        "sample.opus" if segment_type is SegmentType.AUDIO else "sample.bin"
    )
    file_path.write_bytes(b"media")
    upload = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(file_key="file-key"),
        )
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="media-message"),
        )
    )
    adapter = LarkAdapter()
    adapter._get_sdk_client = Mock(
        return_value=SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(
                    file=SimpleNamespace(acreate=upload),
                    message=SimpleNamespace(acreate=create),
                )
            )
        )
    )

    # Act
    await adapter.send(
        _binding(),
        OutboundMessage(
            segments=(
                MessageSegment.of_media(segment_type, path=str(file_path)),
            ),
        ),
    )

    # Assert
    assert create.await_args.args[0].body.msg_type == expected_message_type


@pytest.mark.asyncio
async def test_sends_video_with_uploaded_cover_when_video_payload_is_provided(
    tmp_path,
) -> None:
    # Arrange
    video_path = tmp_path / "sample.mp4"
    cover_path = tmp_path / "cover.png"
    video_path.write_bytes(b"video")
    cover_path.write_bytes(b"cover")
    upload_file = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(file_key="video-key"),
        )
    )
    upload_image = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(image_key="cover-key"),
        )
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="video-message"),
        )
    )
    adapter = LarkAdapter()
    adapter._get_sdk_client = Mock(
        return_value=SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(
                    file=SimpleNamespace(acreate=upload_file),
                    image=SimpleNamespace(acreate=upload_image),
                    message=SimpleNamespace(acreate=create),
                )
            )
        )
    )

    # Act
    await adapter._send_one(
        _binding(),
        LarkOutboundMessage(
            message_type=LarkMessageType.MEDIA,
            file_path=str(video_path),
            image_path=str(cover_path),
        ),
        ChannelRoute(),
        "",
    )

    # Assert
    assert json.loads(create.await_args.args[0].body.content) == {
        "file_key": "video-key",
        "image_key": "cover-key",
        "file_name": "sample.mp4",
    }


@pytest.mark.asyncio
async def test_downloads_media_when_inbound_resource_is_received(
    tmp_path,
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    download = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            file=BytesIO(b"audio"),
            file_name="voice.opus",
        )
    )
    client = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                message_resource=SimpleNamespace(aget=download),
            )
        )
    )
    adapter = LarkAdapter()

    # Act
    attachment = await adapter._download_message_resource(
        client,
        "session1",
        "message1",
        "file-key",
        "file",
        "audio",
    )

    # Assert
    assert (tmp_path / "velpos-attachments" / "session1") in Path(
        attachment["path"]
    ).parents


@pytest.mark.asyncio
async def test_marks_extensionless_lark_image_as_image_when_downloaded(
    tmp_path,
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    download = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            file=BytesIO(b"image"),
            file_name="lark-image",
        )
    )
    client = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                message_resource=SimpleNamespace(aget=download),
            )
        )
    )
    adapter = LarkAdapter()

    # Act
    attachment = await adapter._download_message_resource(
        client,
        "session1",
        "message1",
        "image-key",
        "image",
        "image",
    )

    # Assert
    assert attachment["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_forwards_attachment_metadata_when_media_message_is_handled() -> None:
    # Arrange
    callback = AsyncMock()
    attachment = {
        "filename": "image.png",
        "mime_type": "image/png",
        "path": "/tmp/image.png",
    }
    adapter = LarkAdapter()
    adapter._materialize_inbound_resources = AsyncMock(
        return_value=("[收到图片]", [attachment])
    )
    connection = _WsConnection(
        channel_id="channel1",
        session_id="session1",
        on_message=callback,
    )

    # Act
    await adapter._handle_lark_message(
        connection,
        message_id="message1",
        message_type="image",
        raw_content=json.dumps({"image_key": "image-key"}),
        sender_id="sender1",
        chat_id="chat1",
    )

    # Assert
    assert callback.await_args.args[0].attachments("lark")[0]["path"] == (
        attachment["path"]
    )


def test_adds_media_to_claude_command_when_inbound_attachment_is_present() -> None:
    # Arrange
    attachment = {
        "filename": "voice.opus",
        "mime_type": "audio/ogg",
        "path": "/tmp/voice.opus",
    }

    # Act
    command = ImChannelApplicationService._build_inbound_query_command(
        _binding(),
        "[收到音频]",
        "source-message",
        [attachment],
    )

    # Assert
    assert command.attachments == [attachment]


def test_marks_image_path_when_inbound_image_is_present() -> None:
    # Arrange
    attachment = {
        "filename": "image.png",
        "mime_type": "image/png",
        "path": "/tmp/image.png",
    }

    # Act
    command = ImChannelApplicationService._build_inbound_query_command(
        _binding(),
        "[收到图片]",
        "source-message",
        [attachment],
    )

    # Assert
    assert command.image_paths == ["/tmp/image.png"]


@pytest.mark.parametrize(
    "event_type",
    [
        "p2.im.message.reaction.created_v1",
        "p2.im.message.reaction.deleted_v1",
    ],
)
def test_registers_reaction_event_when_lark_listener_is_built(
    event_type: str,
) -> None:
    # Arrange
    adapter = LarkAdapter()
    connection = _WsConnection(channel_id="channel1", session_id="session1")

    # Act
    handler = adapter._build_event_handler(connection)

    # Assert
    assert event_type in handler._processorMap


@pytest.mark.asyncio
async def test_forwards_web_attachments_to_im_outbox() -> None:
    # Arrange
    enqueue = AsyncMock()
    coordinator = SessionEventCoordinator(
        connection_manager=SimpleNamespace(),
        im_channel_registry=SimpleNamespace(),
        enqueue_im_fn=enqueue,
    )
    attachment = {
        "filename": "image.png",
        "mime_type": "image/png",
        "path": "/tmp/image.png",
    }

    # Act
    await coordinator.on_user_message(
        "session1",
        "look",
        attachments=[attachment],
    )

    # Assert
    assert enqueue.await_args.kwargs["attachments"] == [attachment]


@pytest.mark.asyncio
async def test_uploads_web_image_when_outbound_attachment_is_present(
    tmp_path,
) -> None:
    # Arrange
    image_path = tmp_path / "web-image.png"
    image_path.write_bytes(b"png")
    upload = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(image_key="image-key"),
        )
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="image-message"),
        )
    )
    adapter = LarkAdapter()
    adapter._get_sdk_client = Mock(
        return_value=SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(
                    image=SimpleNamespace(acreate=upload),
                    message=SimpleNamespace(acreate=create),
                )
            )
        )
    )

    # Act
    await adapter.send(
        _binding(),
        OutboundMessage.of_text_with_attachments(
            "",
            [
                {
                    "filename": "web-image.png",
                    "mime_type": "image/png",
                    "path": str(image_path),
                }
            ],
        ),
    )

    # Assert
    upload.assert_awaited_once()


@pytest.mark.parametrize(
    ("mime_type", "expected_type"),
    [
        ("audio/mpeg", LarkMessageType.AUDIO),
        ("video/webm", LarkMessageType.MEDIA),
    ],
)
def test_maps_web_media_to_native_lark_type(
    mime_type: str,
    expected_type: LarkMessageType,
) -> None:
    # Arrange
    attachment = {
        "filename": "media.bin",
        "mime_type": mime_type,
        "path": "/tmp/media.bin",
    }

    # Act
    message = _segment_to_lark_message(MessageSegment.from_attachment(attachment))

    # Assert
    assert message.message_type is expected_type


def test_resolves_web_attachment_against_session_project_when_path_is_relative(
    tmp_path,
) -> None:
    # Arrange
    relative_path = ".upload-file/session1/image.png"

    # Act
    attachments = SessionQueryEngine._resolve_outbound_attachments(
        [{"path": relative_path, "mime_type": "image/png"}],
        str(tmp_path),
    )

    # Assert
    assert attachments[0]["path"] == str((tmp_path / relative_path).resolve())


@pytest.mark.asyncio
async def test_stages_legacy_extensionless_image_before_lark_upload(
    tmp_path,
) -> None:
    # Arrange
    image_path = tmp_path / "jpg"
    image_path.write_bytes(b"image")
    upload = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(image_key="image-key"),
        )
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="image-message"),
        )
    )
    adapter = LarkAdapter()
    adapter._get_sdk_client = Mock(
        return_value=SimpleNamespace(
            im=SimpleNamespace(
                v1=SimpleNamespace(
                    image=SimpleNamespace(acreate=upload),
                    message=SimpleNamespace(acreate=create),
                )
            )
        )
    )

    # Act
    await adapter.send(
        _binding(),
        OutboundMessage.of_text_with_attachments(
            "",
            [
                {
                    "filename": "车.jpg",
                    "mime_type": "image/jpeg",
                    "path": str(image_path),
                }
            ],
        ),
    )

    # Assert
    assert Path(upload.await_args.args[0].body.image.name).suffix == ".jpg"


def test_does_not_raise_on_cache_destructor_when_ws_loop_shuts_down() -> None:
    from lark_oapi.core.cache.expiring_cache import ExpiringCache

    errors: list[object] = []

    def run_ws_thread() -> None:
        previous_hook = sys.unraisablehook
        sys.unraisablehook = lambda args: errors.append(args)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        cache: ExpiringCache | None = None
        try:
            cache = ExpiringCache(clear_interval=30)
            loop.call_soon(loop.stop)
            loop.run_forever()
            LarkAdapter._shutdown_event_loop(loop)
            cache = None
            gc.collect()
            if not loop.is_closed():
                errors.append("loop_not_closed")
        finally:
            sys.unraisablehook = previous_hook
            cache = None
            if not loop.is_closed():
                LarkAdapter._shutdown_event_loop(loop)
            asyncio.set_event_loop(None)

    thread = threading.Thread(target=run_ws_thread)
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
