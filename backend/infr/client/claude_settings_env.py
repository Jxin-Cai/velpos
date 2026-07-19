from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


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
        return {}
    except json.JSONDecodeError:
        logger.warning("Claude settings file contains invalid JSON: %s", settings_path)
        return {}
    except OSError:
        logger.error("Failed to read Claude settings file: %s", settings_path, exc_info=True)
        raise

    if not isinstance(settings, dict):
        logger.warning("Claude settings file must contain a JSON object: %s", settings_path)
        return {}

    raw_env = settings.get("env")
    if raw_env is None:
        return {}
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
    return env
