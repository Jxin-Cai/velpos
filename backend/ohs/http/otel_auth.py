from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
from functools import lru_cache

from fastapi import HTTPException, Request

from application.session.native_otel_config import (
    native_otel_accept_legacy_loopback_token,
    native_otel_ingest_token,
)

logger = logging.getLogger(__name__)


def _is_loopback_request(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


@lru_cache(maxsize=32)
def _log_legacy_token_acceptance(token_fingerprint: str) -> None:
    logger.warning(
        "Accepted a legacy OTLP ingest token from loopback; reconnect the Claude "
        "SDK client to rotate it: token_fingerprint=%s",
        token_fingerprint,
    )


def authorize_otel_request(token: str | None, request: Request) -> None:
    expected = native_otel_ingest_token()
    if token is not None and hmac.compare_digest(token, expected):
        return

    # Before stable token derivation was introduced, every backend restart
    # invalidated the token held by an already-running SDK subprocess. Accept
    # those legacy tokens only from the kernel-reported loopback peer in dev.
    # Missing/short tokens are never eligible for compatibility acceptance.
    if (
        token is not None
        and len(token) >= 64
        and native_otel_accept_legacy_loopback_token()
        and _is_loopback_request(request)
    ):
        fingerprint = hashlib.sha256(token.encode()).hexdigest()[:12]
        _log_legacy_token_acceptance(fingerprint)
        return

    raise HTTPException(status_code=401, detail="Invalid OTLP ingest token")
