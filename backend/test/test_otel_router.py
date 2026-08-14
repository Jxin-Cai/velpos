from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from application.session.native_otel_config import native_otel_ingest_token
from ohs.http.otel_auth import authorize_otel_request


def _request_from(host: str) -> Request:
    return Request({"type": "http", "client": (host, 4318), "headers": []})


def test_accepts_current_ingest_token_when_request_is_remote(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_MODE", "pro")
    request = _request_from("203.0.113.10")

    # Act
    authorize_otel_request(native_otel_ingest_token(), request)

    # Assert: no exception means the current token is valid from any peer.


def test_accepts_legacy_ingest_token_when_request_is_local_in_dev(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_MODE", "dev")
    monkeypatch.delenv("VELPOS_OTEL_ACCEPT_LEGACY_LOOPBACK_TOKEN", raising=False)
    request = _request_from("127.0.0.1")

    # Act
    authorize_otel_request("legacy-token-from-running-sdk-process-1234", request)

    # Assert: no exception keeps an already-running local SDK client exporting.


def test_rejects_missing_ingest_token_when_request_is_local_in_dev(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_MODE", "dev")
    request = _request_from("127.0.0.1")

    # Act
    with pytest.raises(HTTPException) as exc_info:
        authorize_otel_request(None, request)

    # Assert
    assert exc_info.value.status_code == 401


def test_rejects_legacy_ingest_token_when_request_is_remote_in_dev(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_MODE", "dev")
    request = _request_from("203.0.113.10")

    # Act
    with pytest.raises(HTTPException) as exc_info:
        authorize_otel_request("legacy-token-from-running-sdk-process-1234", request)

    # Assert
    assert exc_info.value.status_code == 401


def test_rejects_legacy_ingest_token_when_compatibility_is_disabled(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_MODE", "dev")
    monkeypatch.setenv("VELPOS_OTEL_ACCEPT_LEGACY_LOOPBACK_TOKEN", "false")
    request = _request_from("::1")

    # Act
    with pytest.raises(HTTPException) as exc_info:
        authorize_otel_request("legacy-token-from-running-sdk-process-1234", request)

    # Assert
    assert exc_info.value.status_code == 401
