from __future__ import annotations

from ohs.http.assembler.audit_payload_assembler import (
    MAX_SEQUENCE_ITEMS,
    trim_audit_payload,
)


def test_keeps_payload_unchanged_when_no_field_is_oversized() -> None:
    # Arrange
    payload = {"signal": "log", "event_name": "api_request", "attributes": {"cost_usd": 0.01}}

    # Act
    result = trim_audit_payload(payload)

    # Assert
    assert result.payload == payload


def test_reports_no_truncation_when_payload_fits() -> None:
    # Arrange
    payload = {"body": "short"}

    # Act
    result = trim_audit_payload(payload)

    # Assert
    assert result.truncated is False


def test_clips_oversized_string_when_raw_api_body_is_returned() -> None:
    # Arrange
    payload = {"event_name": "api_response_body", "body": "x" * 5000}

    # Act
    result = trim_audit_payload(payload, max_string_length=100)

    # Assert
    assert result.payload["body"].startswith("x" * 100)


def test_reports_original_length_when_string_is_clipped() -> None:
    # Arrange
    payload = {"body": "x" * 5000}

    # Act
    result = trim_audit_payload(payload, max_string_length=100)

    # Assert
    assert "5000 chars total" in result.payload["body"]


def test_flags_truncation_when_any_field_is_clipped() -> None:
    # Arrange
    payload = {"body": "x" * 5000}

    # Act
    result = trim_audit_payload(payload, max_string_length=100)

    # Assert
    assert result.truncated is True


def test_clips_nested_strings_when_payload_is_deep() -> None:
    # Arrange
    payload = {"scope": {"attributes": {"prompt": "y" * 500}}}

    # Act
    result = trim_audit_payload(payload, max_string_length=10)

    # Assert
    assert result.payload["scope"]["attributes"]["prompt"].startswith("y" * 10)


def test_caps_sequence_length_when_payload_holds_a_long_list() -> None:
    # Arrange
    payload = {"bucket_counts": list(range(MAX_SEQUENCE_ITEMS + 50))}

    # Act
    result = trim_audit_payload(payload)

    # Assert
    assert len(result.payload["bucket_counts"]) == MAX_SEQUENCE_ITEMS


def test_leaves_non_string_scalars_untouched_when_trimming() -> None:
    # Arrange
    payload = {"value": 1.25, "count": 3, "is_monotonic": True, "unit": None}

    # Act
    result = trim_audit_payload(payload, max_string_length=1)

    # Assert
    assert result.payload == payload
