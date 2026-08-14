from __future__ import annotations

import hashlib
import os
from urllib.parse import quote

from infr.client.claude_settings_env import with_claude_code_general_env_defaults


def _derive_ingest_token() -> str:
    explicit = os.getenv("VELPOS_OTEL_INGEST_TOKEN")
    if explicit:
        return explicit
    secret = os.getenv("JWT_SECRET", "velpos-dev-secret-key-change-in-production")
    return hashlib.sha256(f"velpos-otel-ingest-v1:{secret}".encode()).hexdigest()


_INGEST_TOKEN = _derive_ingest_token()


def native_otel_enabled() -> bool:
    return os.getenv("VELPOS_NATIVE_OTEL_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def native_otel_ingest_token() -> str:
    return _INGEST_TOKEN


def native_otel_accept_legacy_loopback_token() -> bool:
    """Allow already-running local SDK clients to survive a token migration.

    Older Velpos versions generated a new random token on every backend start.
    A Claude SDK subprocess keeps the environment it was started with, so those
    clients otherwise receive 401 responses until they are reconnected.  The
    compatibility path is deliberately limited to loopback requests by the
    HTTP adapter and defaults to development mode only.
    """
    configured = os.getenv("VELPOS_OTEL_ACCEPT_LEGACY_LOOPBACK_TOKEN")
    if configured is not None:
        return configured.lower() in {"1", "true", "yes"}
    return os.getenv("VELPOS_MODE", "dev") == "dev"


def _append_resource_attribute(raw: str, key: str, value: str) -> str:
    encoded = quote(value, safe="-._~")
    item = f"{key}={encoded}"
    return f"{raw},{item}" if raw else item


def build_native_otel_env(
    session_id: str,
    inherited: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the official Claude Code OTLP configuration for one SDK client."""
    env = dict(inherited or {})
    if not native_otel_enabled():
        return env
    env = with_claude_code_general_env_defaults(env)

    backend_port = os.getenv(
        "VELPOS_BACKEND_PORT",
        os.getenv("BACKEND_PORT", os.getenv("PORT", "8083")),
    )
    endpoint = os.getenv(
        "VELPOS_OTEL_ENDPOINT",
        f"http://127.0.0.1:{backend_port}/api/otel",
    ).rstrip("/")
    resource_attributes = env.get("OTEL_RESOURCE_ATTRIBUTES", "")
    resource_attributes = _append_resource_attribute(
        resource_attributes,
        "velpos.session.id",
        session_id,
    )
    resource_attributes = _append_resource_attribute(
        resource_attributes,
        "deployment.environment",
        os.getenv("VELPOS_MODE", "dev"),
    )

    env.update(
        {
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
            "OTEL_EXPORTER_OTLP_HEADERS": (
                f"x-velpos-otel-token={native_otel_ingest_token()}"
            ),
            "OTEL_SERVICE_NAME": os.getenv("VELPOS_OTEL_SERVICE_NAME", "velpos-agent"),
            "OTEL_RESOURCE_ATTRIBUTES": resource_attributes,
            "OTEL_METRIC_EXPORT_INTERVAL": os.getenv(
                "VELPOS_OTEL_METRIC_EXPORT_INTERVAL", "1000"
            ),
            "OTEL_LOGS_EXPORT_INTERVAL": os.getenv(
                "VELPOS_OTEL_LOGS_EXPORT_INTERVAL", "1000"
            ),
            "OTEL_TRACES_EXPORT_INTERVAL": os.getenv(
                "VELPOS_OTEL_TRACES_EXPORT_INTERVAL", "1000"
            ),
            "CLAUDE_CODE_OTEL_DIAG_STDERR": "1",
            # Required in addition to enhanced telemetry for hook spans. The
            # SDK/non-interactive path does not require an allowlist.
            "BETA_TRACING_ENDPOINT": endpoint,
        }
    )
    return env
