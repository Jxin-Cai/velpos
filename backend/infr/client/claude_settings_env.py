from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# Collection switches are destination-agnostic Claude Code defaults. The
# OTLP exporter destination is merged and persisted separately so
# ~/.claude/settings.json matches the SDK subprocess in both dev and pro.
CLAUDE_CODE_GENERAL_ENV_DEFAULTS: dict[str, str] = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "ENABLE_BETA_TRACING_DETAILED": "1",
    "OTEL_LOG_USER_PROMPTS": "1",
    "OTEL_LOG_ASSISTANT_RESPONSES": "1",
    "OTEL_LOG_TOOL_DETAILS": "1",
    "OTEL_LOG_TOOL_CONTENT": "1",
    "OTEL_LOG_RAW_API_BODIES": "1",
    "CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH": "262144",
    "OTEL_METRICS_INCLUDE_SESSION_ID": "true",
    "OTEL_METRICS_INCLUDE_VERSION": "true",
    "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "true",
    "OTEL_METRICS_INCLUDE_ENTRYPOINT": "true",
    "OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES": "true",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "0",
}


def with_claude_code_general_env_defaults(
    env: dict[str, str] | None,
) -> dict[str, str]:
    merged = dict(CLAUDE_CODE_GENERAL_ENV_DEFAULTS)
    merged.update(env or {})
    return merged


def resolve_claude_settings_path(config_dir: Path | None = None) -> Path:
    claude_dir = config_dir or Path(
        os.getenv("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
    ).expanduser()
    return claude_dir / "settings.json"


def load_claude_settings_env(config_dir: Path | None = None) -> dict[str, str]:
    """Load environment variables that Claude Code defines in user settings."""
    settings_path = resolve_claude_settings_path(config_dir)

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(CLAUDE_CODE_GENERAL_ENV_DEFAULTS)
    except json.JSONDecodeError:
        logger.warning("Claude settings file contains invalid JSON: %s", settings_path)
        return dict(CLAUDE_CODE_GENERAL_ENV_DEFAULTS)
    except OSError:
        logger.error("Failed to read Claude settings file: %s", settings_path, exc_info=True)
        raise

    if not isinstance(settings, dict):
        logger.warning("Claude settings file must contain a JSON object: %s", settings_path)
        return dict(CLAUDE_CODE_GENERAL_ENV_DEFAULTS)

    raw_env = settings.get("env")
    if raw_env is None:
        return dict(CLAUDE_CODE_GENERAL_ENV_DEFAULTS)
    if not isinstance(raw_env, dict):
        logger.warning("Claude settings env must be a JSON object: %s", settings_path)
        return {}

    env = {
        key: value
        for key, value in raw_env.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    if len(env) != len(raw_env):
        logger.warning(
            "Ignored %d non-string entries in Claude settings env: %s",
            len(raw_env) - len(env),
            settings_path,
        )
    return with_claude_code_general_env_defaults(env)


def resolve_default_model() -> str:
    """Resolve default model: env var → settings.json → fallback."""
    from_env = os.getenv("DEFAULT_MODEL")
    if from_env:
        return from_env
    settings_env = load_claude_settings_env()
    return settings_env.get("ANTHROPIC_MODEL", "default")
