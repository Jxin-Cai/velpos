from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from domain.session.model.execution_ledger_event import ExecutionLedgerEvent
from domain.session.model.llm_request import PromptChangeKind
from domain.session.service.llm_request_decomposer import (
    API_REQUEST_BODY_EVENT_NAME,
    LlmRequestDecomposer,
)

_SESSION_ID = "sess0001"
_RUN_ID = "run-1"
_NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def _body_event(
    body: object,
    *,
    event_id: str = "event-1",
    offset_seconds: int = 0,
    attribute_key: str = "request_body",
) -> ExecutionLedgerEvent:
    serialized = body if isinstance(body, str) else json.dumps(body)
    return ExecutionLedgerEvent.from_otel_record(
        event_id=event_id,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        signal="log",
        event_name=API_REQUEST_BODY_EVENT_NAME,
        event_time=_NOW + timedelta(seconds=offset_seconds),
        payload={
            "signal": "log",
            "event_name": API_REQUEST_BODY_EVENT_NAME,
            "body": API_REQUEST_BODY_EVENT_NAME,
            "attributes": {attribute_key: serialized},
        },
    )


def test_splits_system_messages_and_tools_when_body_is_json_string() -> None:
    # Arrange
    event = _body_event({
        "model": "claude-sonnet-4",
        "system": "You are helpful.",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"name": "Read", "description": "Read a file", "input_schema": {"type": "object"}}],
    })

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert (records[0].system, records[0].message_count, records[0].tool_names) == (
        "You are helpful.",
        1,
        ("Read",),
    )


def test_joins_system_blocks_when_system_is_a_block_list() -> None:
    # Arrange
    event = _body_event({
        "system": [
            {"type": "text", "text": "Base instructions."},
            {"type": "text", "text": "Project instructions."},
        ],
        "messages": [],
    })

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records[0].system == "Base instructions.\n\nProject instructions."


def test_reads_body_when_carried_as_a_nested_mapping() -> None:
    # Arrange
    event = _body_event({"system": "S", "messages": [{"role": "user"}]})
    event.payload["attributes"]["request_body"] = {"system": "S", "messages": [{"role": "user"}]}

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records[0].system == "S"


def test_marks_first_request_as_initial_when_no_predecessor_exists() -> None:
    # Arrange
    event = _body_event({"system": "S", "messages": []})

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records[0].change is PromptChangeKind.INITIAL


def test_marks_request_unchanged_when_system_and_tools_repeat() -> None:
    # Arrange
    body = {"system": "S", "messages": [], "tools": [{"name": "Read"}]}
    events = [
        _body_event(body, event_id="e1", offset_seconds=0),
        _body_event(body, event_id="e2", offset_seconds=5),
    ]

    # Act
    records = LlmRequestDecomposer().decompose(events)

    # Assert
    assert records[1].change is PromptChangeKind.UNCHANGED


def test_flags_system_change_when_only_the_system_prompt_differs() -> None:
    # Arrange
    events = [
        _body_event({"system": "S", "messages": [], "tools": [{"name": "Read"}]}, event_id="e1"),
        _body_event(
            {"system": "S2", "messages": [], "tools": [{"name": "Read"}]},
            event_id="e2",
            offset_seconds=5,
        ),
    ]

    # Act
    records = LlmRequestDecomposer().decompose(events)

    # Assert
    assert records[1].change is PromptChangeKind.SYSTEM


def test_flags_tools_change_when_only_the_tool_catalog_differs() -> None:
    # Arrange
    events = [
        _body_event({"system": "S", "messages": [], "tools": [{"name": "Read"}]}, event_id="e1"),
        _body_event(
            {"system": "S", "messages": [], "tools": [{"name": "Read"}, {"name": "Write"}]},
            event_id="e2",
            offset_seconds=5,
        ),
    ]

    # Act
    records = LlmRequestDecomposer().decompose(events)

    # Assert
    assert records[1].change is PromptChangeKind.TOOLS


def test_flags_combined_change_when_system_and_tools_both_differ() -> None:
    # Arrange
    events = [
        _body_event({"system": "S", "messages": [], "tools": [{"name": "Read"}]}, event_id="e1"),
        _body_event(
            {"system": "S2", "messages": [], "tools": [{"name": "Write"}]},
            event_id="e2",
            offset_seconds=5,
        ),
    ]

    # Act
    records = LlmRequestDecomposer().decompose(events)

    # Assert
    assert records[1].change is PromptChangeKind.SYSTEM_AND_TOOLS


def test_skips_event_when_body_is_not_a_request_envelope() -> None:
    # Arrange
    event = _body_event("not json at all")

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records == ()


def test_skips_event_when_body_json_lacks_request_fields() -> None:
    # Arrange
    event = _body_event({"unrelated": True})

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records == ()


def test_orders_records_chronologically_when_events_arrive_out_of_order() -> None:
    # Arrange
    events = [
        _body_event({"system": "late", "messages": []}, event_id="e2", offset_seconds=10),
        _body_event({"system": "early", "messages": []}, event_id="e1", offset_seconds=0),
    ]

    # Act
    records = LlmRequestDecomposer().decompose(events)

    # Assert
    assert [record.system for record in records] == ["early", "late"]


def test_numbers_records_sequentially_when_multiple_requests_decompose() -> None:
    # Arrange
    events = [
        _body_event({"system": "a", "messages": []}, event_id="e1", offset_seconds=0),
        _body_event({"system": "b", "messages": []}, event_id="e2", offset_seconds=5),
    ]

    # Act
    records = LlmRequestDecomposer().decompose(events)

    # Assert
    assert [record.sequence for record in records] == [1, 2]


def test_truncates_system_preview_when_prompt_exceeds_preview_length() -> None:
    # Arrange
    event = _body_event({"system": "x" * 900, "messages": []})

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records[0].system_preview.endswith("…")


def test_reports_full_system_length_when_preview_is_truncated() -> None:
    # Arrange
    event = _body_event({"system": "x" * 900, "messages": []})

    # Act
    records = LlmRequestDecomposer().decompose([event])

    # Assert
    assert records[0].system_char_count == 900
