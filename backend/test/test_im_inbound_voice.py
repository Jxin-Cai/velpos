"""入站语音链路 — 飞书 / 微信 / QQ 的语音消息如何到达 LLM."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from application.session.command.run_query_command import RunQueryCommand
from application.session.session_query_engine import SessionQueryEngine
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_message import MessageSegment, SegmentType
from infr.im.inbound_voice import (
    VOICE_PLACEHOLDER_TEXT,
    InboundVoice,
    InboundVoiceStore,
    VoiceCodec,
)
from infr.im.lark.lark_adapter import LarkAdapter, _WsConnection
from infr.im.lark.lark_message import LarkInboundContent, parse_inbound_content
from infr.im.qq.qq_adapter import QQ_CHANNEL_SPEC, QqAdapter
from infr.im.qq.qq_ws_client import QqInboundEvent, _parse_attachments
from infr.im.weixin.weixin_adapter import _extract_inbound_content


def _voice_command(prompt: str, **overrides: object) -> RunQueryCommand:
    attachment = {
        "filename": "voice.wav",
        "mime_type": "audio/wav",
        "path": ".upload-file/session1/voice.wav",
        **overrides,
    }
    return RunQueryCommand(
        session_id="session1",
        prompt=prompt,
        attachments=[attachment],
    )


# ── prompt 组装 ──


def test_renders_voice_reference_when_audio_attachment_is_present() -> None:
    # Arrange
    command = _voice_command("帮我看下这个")

    # Act
    prompt = SessionQueryEngine._compose_prompt(command)

    # Assert
    assert "[Voice: voice.wav path=.upload-file/session1/voice.wav]" in prompt


def test_appends_transcript_when_prompt_does_not_carry_it() -> None:
    # Arrange
    command = _voice_command("", transcript="明天下午三点开会")

    # Act
    prompt = SessionQueryEngine._compose_prompt(command)

    # Assert
    assert 'transcript="明天下午三点开会"' in prompt


def test_omits_transcript_when_prompt_already_carries_it() -> None:
    # Arrange
    command = _voice_command("明天下午三点开会", transcript="明天下午三点开会")

    # Act
    prompt = SessionQueryEngine._compose_prompt(command)

    # Assert
    assert "transcript=" not in prompt


def test_renders_duration_when_voice_attachment_declares_it() -> None:
    # Arrange
    command = _voice_command("听一下", duration=7)

    # Act
    prompt = SessionQueryEngine._compose_prompt(command)

    # Assert
    assert "duration=7s" in prompt


def test_keeps_generic_reference_when_attachment_is_not_audio() -> None:
    # Arrange
    command = RunQueryCommand(
        session_id="session1",
        prompt="看下报告",
        attachments=[
            {
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "path": ".upload-file/session1/report.pdf",
            }
        ],
    )

    # Act
    prompt = SessionQueryEngine._compose_prompt(command)

    # Assert
    assert "[Attachment: report.pdf path=.upload-file/session1/report.pdf]" in prompt


# ── 领域模型 ──


def test_round_trips_transcript_when_audio_segment_is_converted() -> None:
    # Arrange
    segment = MessageSegment.of_media(
        SegmentType.AUDIO,
        path="/tmp/voice.wav",
        mime_type="audio/wav",
        transcript="你好",
    )

    # Act
    restored = MessageSegment.from_attachment(segment.to_attachment("qq"))

    # Assert
    assert restored.transcript == "你好"


# ── 飞书 ──


def test_marks_voice_when_lark_audio_message_is_parsed() -> None:
    # Arrange
    raw = json.dumps({"file_key": "file-key", "duration": 4200})

    # Act
    parsed = parse_inbound_content("audio", raw)

    # Assert
    assert parsed.is_voice is True


def test_reads_duration_when_lark_audio_message_is_parsed() -> None:
    # Arrange
    raw = json.dumps({"file_key": "file-key", "duration": 4200})

    # Act
    parsed = parse_inbound_content("audio", raw)

    # Assert
    assert parsed.duration_ms == 4200


def test_uses_placeholder_text_when_lark_audio_is_not_yet_transcribed() -> None:
    # Arrange
    raw = json.dumps({"file_key": "file-key"})

    # Act
    parsed = parse_inbound_content("audio", raw)

    # Assert
    assert parsed.text == VOICE_PLACEHOLDER_TEXT


def _lark_voice_fixture() -> tuple[LarkAdapter, _WsConnection, LarkInboundContent, list[dict]]:
    adapter = LarkAdapter()
    connection = _WsConnection(channel_id="channel1", session_id="session1")
    parsed = LarkInboundContent(
        text=VOICE_PLACEHOLDER_TEXT,
        resources=(("file", "file-key"),),
        is_voice=True,
        duration_ms=4200,
    )
    attachments = [
        {
            "filename": "lark-voice.opus",
            "mime_type": "audio/ogg",
            "path": "/tmp/lark-voice.opus",
        }
    ]
    return adapter, connection, parsed, attachments


@pytest.mark.asyncio
async def test_replaces_placeholder_when_lark_speech_is_recognized() -> None:
    # Arrange
    adapter, connection, parsed, attachments = _lark_voice_fixture()
    adapter._recognize_speech_file = AsyncMock(return_value="下周一发版")

    # Act
    text, _attachments = await adapter._transcribe_inbound_voice(
        object(), connection, "message1", parsed, attachments,
    )

    # Assert
    assert text == "下周一发版"


@pytest.mark.asyncio
async def test_attaches_transcript_when_lark_speech_is_recognized() -> None:
    # Arrange
    adapter, connection, parsed, attachments = _lark_voice_fixture()
    adapter._recognize_speech_file = AsyncMock(return_value="下周一发版")

    # Act
    _text, resolved = await adapter._transcribe_inbound_voice(
        object(), connection, "message1", parsed, attachments,
    )

    # Assert
    assert resolved[0]["transcript"] == "下周一发版"


@pytest.mark.asyncio
async def test_converts_duration_to_seconds_when_lark_voice_is_transcribed() -> None:
    # Arrange
    adapter, connection, parsed, attachments = _lark_voice_fixture()
    adapter._recognize_speech_file = AsyncMock(return_value="下周一发版")

    # Act
    _text, resolved = await adapter._transcribe_inbound_voice(
        object(), connection, "message1", parsed, attachments,
    )

    # Assert
    assert resolved[0]["duration"] == 4


@pytest.mark.asyncio
async def test_keeps_placeholder_text_when_lark_speech_recognition_fails() -> None:
    # Arrange
    adapter, connection, parsed, attachments = _lark_voice_fixture()
    adapter._recognize_speech_file = AsyncMock(return_value="")

    # Act
    text, _resolved = await adapter._transcribe_inbound_voice(
        object(), connection, "message1", parsed, attachments,
    )

    # Assert
    assert text == VOICE_PLACEHOLDER_TEXT


@pytest.mark.asyncio
async def test_forwards_audio_file_when_lark_speech_recognition_fails() -> None:
    # Arrange
    adapter, connection, parsed, attachments = _lark_voice_fixture()
    adapter._recognize_speech_file = AsyncMock(return_value="")

    # Act
    _text, resolved = await adapter._transcribe_inbound_voice(
        object(), connection, "message1", parsed, attachments,
    )

    # Assert
    assert resolved[0]["path"] == "/tmp/lark-voice.opus"


def test_keeps_video_label_when_media_message_is_parsed() -> None:
    # Arrange
    raw = json.dumps({"file_key": "file-key", "file_name": "clip.mp4"})

    # Act
    parsed = parse_inbound_content("media", raw)

    # Assert
    assert parsed.text == "[收到视频: clip.mp4]"


# ── 微信 ──


def test_uses_server_transcript_when_weixin_voice_is_received() -> None:
    # Arrange
    msg = {
        "item_list": [
            {"type": 3, "voice_item": {"text": "帮我查一下订单状态", "playtime": 3000}}
        ]
    }

    # Act
    parsed = _extract_inbound_content(msg)

    # Assert
    assert parsed.text == "帮我查一下订单状态"


def test_flags_voice_origin_when_weixin_voice_is_received() -> None:
    # Arrange
    msg = {"item_list": [{"type": 3, "voice_item": {"text": "你好"}}]}

    # Act
    parsed = _extract_inbound_content(msg)

    # Assert
    assert parsed.is_voice is True


def test_falls_back_to_placeholder_when_weixin_transcript_is_empty() -> None:
    # Arrange
    msg = {"item_list": [{"type": 3, "voice_item": {"playtime": 1200}}]}

    # Act
    parsed = _extract_inbound_content(msg)

    # Assert
    assert parsed.text == VOICE_PLACEHOLDER_TEXT


def test_keeps_text_extraction_when_weixin_text_message_is_received() -> None:
    # Arrange
    msg = {"item_list": [{"type": 1, "text_item": {"text": "普通文本"}}]}

    # Act
    parsed = _extract_inbound_content(msg)

    # Assert
    assert parsed.text == "普通文本"


def test_yields_empty_text_when_weixin_message_has_only_image() -> None:
    # Arrange
    msg = {"item_list": [{"type": 2, "image_item": {"url": "https://x/y.png"}}]}

    # Act
    parsed = _extract_inbound_content(msg)

    # Assert
    assert parsed.text == ""


# ── QQ ──


def test_collects_voice_attachment_when_qq_event_has_no_text() -> None:
    # Arrange
    event_data = {
        "id": "msg1",
        "content": "",
        "attachments": [
            {
                "content_type": "voice",
                "voice_wav_url": "//multimedia.nt.qq.com/voice.wav",
                "asr_refer_text": "今天几号",
            }
        ],
    }

    # Act
    attachments = _parse_attachments(event_data)

    # Assert
    assert len(attachments) == 1


def test_drops_attachment_when_qq_event_carries_no_download_url() -> None:
    # Arrange
    event_data = {"attachments": [{"content_type": "voice", "filename": "v.silk"}]}

    # Act
    attachments = _parse_attachments(event_data)

    # Assert
    assert attachments == ()


@pytest.mark.asyncio
async def test_uses_tencent_transcript_when_qq_voice_is_materialized() -> None:
    # Arrange
    api = AsyncMock()
    api.download_attachment.return_value = b"RIFFfake"
    store = AsyncMock(spec=InboundVoiceStore)
    store.store.return_value = InboundVoice(
        transcript="今天几号",
        attachment={"filename": "qq-voice.wav", "mime_type": "audio/wav", "path": "/tmp/v.wav"},
    )
    adapter = QqAdapter(ws_client=AsyncMock(), api_client=api, voice_store=store)
    event = QqInboundEvent(
        message_id="msg1",
        content="",
        sender_openid="user1",
        attachments=(
            {
                "content_type": "voice",
                "voice_wav_url": "//multimedia.nt.qq.com/voice.wav",
                "asr_refer_text": "今天几号",
            },
        ),
    )

    # Act
    text, _attachments = await adapter._materialize_inbound_event("session1", event)

    # Assert
    assert text == "今天几号"


@pytest.mark.asyncio
async def test_prefers_wav_codec_when_qq_voice_provides_transcoded_url() -> None:
    # Arrange
    api = AsyncMock()
    api.download_attachment.return_value = b"RIFFfake"
    store = AsyncMock(spec=InboundVoiceStore)
    store.store.return_value = InboundVoice(transcript="今天几号")
    adapter = QqAdapter(ws_client=AsyncMock(), api_client=api, voice_store=store)
    event = QqInboundEvent(
        message_id="msg1",
        content="",
        sender_openid="user1",
        attachments=(
            {
                "content_type": "voice",
                "url": "//multimedia.nt.qq.com/voice.silk",
                "voice_wav_url": "//multimedia.nt.qq.com/voice.wav",
            },
        ),
    )

    # Act
    await adapter._materialize_inbound_event("session1", event)

    # Assert
    assert store.store.await_args.kwargs["codec"] is VoiceCodec.WAV


def _qq_download_failure_fixture() -> tuple[QqAdapter, QqInboundEvent]:
    api = AsyncMock()
    api.download_attachment.side_effect = httpx.ConnectError("boom")
    adapter = QqAdapter(ws_client=AsyncMock(), api_client=api)
    event = QqInboundEvent(
        message_id="msg1",
        content="",
        sender_openid="user1",
        attachments=(
            {
                "content_type": "voice",
                "voice_wav_url": "//multimedia.nt.qq.com/voice.wav",
                "asr_refer_text": "订单到哪了",
            },
        ),
    )
    return adapter, event


@pytest.mark.asyncio
async def test_keeps_transcript_when_qq_voice_download_fails() -> None:
    # Arrange
    adapter, event = _qq_download_failure_fixture()

    # Act
    text, _attachments = await adapter._materialize_inbound_event("session1", event)

    # Assert
    assert text == "订单到哪了"


@pytest.mark.asyncio
async def test_drops_audio_attachment_when_qq_voice_download_fails() -> None:
    # Arrange
    adapter, event = _qq_download_failure_fixture()

    # Act
    _text, attachments = await adapter._materialize_inbound_event("session1", event)

    # Assert
    assert attachments == []


@pytest.mark.asyncio
async def test_falls_back_to_placeholder_when_qq_voice_has_no_transcript() -> None:
    # Arrange
    api = AsyncMock()
    api.download_attachment.return_value = b"RIFFfake"
    store = AsyncMock(spec=InboundVoiceStore)
    store.store.return_value = InboundVoice(
        attachment={"filename": "qq-voice.wav", "mime_type": "audio/wav", "path": "/tmp/v.wav"},
    )
    adapter = QqAdapter(ws_client=AsyncMock(), api_client=api, voice_store=store)
    event = QqInboundEvent(
        message_id="msg1",
        content="",
        sender_openid="user1",
        attachments=({"content_type": "voice", "url": "//x/voice.silk"},),
    )

    # Act
    text, _attachments = await adapter._materialize_inbound_event("session1", event)

    # Assert
    assert text == VOICE_PLACEHOLDER_TEXT


def test_declares_inbound_attachment_when_qq_channel_is_registered() -> None:
    # Arrange
    spec = QQ_CHANNEL_SPEC

    # Act
    capabilities = spec.capabilities

    # Assert
    assert ChannelCapability.INBOUND_ATTACHMENT in capabilities


@pytest.mark.asyncio
async def test_persists_voice_file_when_audio_bytes_are_stored(tmp_path) -> None:
    # Arrange
    class _Storage:
        def save(self, _project_dir, _session_id, filename, data):
            target = tmp_path / filename
            target.write_bytes(data)
            return str(target), "digest"

    store = InboundVoiceStore(storage=_Storage())

    # Act
    voice = await store.store(
        session_id="session1",
        source=ImChannelType.QQ.value,
        audio=b"RIFFfake",
        codec=VoiceCodec.WAV,
        transcript="你好",
    )

    # Assert
    assert voice.attachment["mime_type"] == "audio/wav"


@pytest.mark.asyncio
async def test_skips_storage_when_voice_download_is_empty() -> None:
    # Arrange
    store = InboundVoiceStore()

    # Act
    voice = await store.store(
        session_id="session1",
        source=ImChannelType.QQ.value,
        audio=b"",
        codec=VoiceCodec.WAV,
        transcript="你好",
    )

    # Assert
    assert voice.attachment is None
