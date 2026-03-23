from __future__ import annotations

import json
from pathlib import Path

_AGENTS_DIR = Path(__file__).parent / "agents"

# ── Category definitions ──

CATEGORIES: list[dict] = [
    {"id": "engineering", "name_en": "Engineering", "name_zh": "工程开发"},
    {"id": "design", "name_en": "Design", "name_zh": "设计"},
    {"id": "testing", "name_en": "Testing", "name_zh": "测试"},
    {"id": "product", "name_en": "Product", "name_zh": "产品"},
    {"id": "project-management", "name_en": "Project Management", "name_zh": "项目管理"},
    {"id": "marketing", "name_en": "Marketing", "name_zh": "市场营销"},
    {"id": "support", "name_en": "Support", "name_zh": "客户支持"},
]


# ── Auto-scanned agent catalog ──


def _scan_agents() -> list[dict]:
    """Scan agents/ directory and load config from each agent's agent.json."""
    agents = []
    if not _AGENTS_DIR.is_dir():
        return agents
    for agent_dir in sorted(_AGENTS_DIR.iterdir()):
        config_path = agent_dir / "config" / "agent.json"
        if not config_path.exists():
            continue
        try:
            meta = json.loads(config_path.read_text(encoding="utf-8"))
            # Scan for Claude Code plugins in subdirectories
            plugins = []
            for sub in agent_dir.iterdir():
                if not sub.is_dir():
                    continue
                plugin_json = sub / ".claude-plugin" / "plugin.json"
                if plugin_json.exists():
                    try:
                        plugin_meta = json.loads(plugin_json.read_text(encoding="utf-8"))
                        plugins.append({
                            "name": plugin_meta.get("name", sub.name),
                            "path": str(sub.resolve()),
                        })
                    except Exception:
                        continue
            meta["plugins"] = plugins

            # Load marketplace plugin config
            plugins_config_path = agent_dir / "config" / "plugins.json"
            if plugins_config_path.exists():
                try:
                    plugins_config = json.loads(plugins_config_path.read_text(encoding="utf-8"))
                    meta["marketplace_plugins"] = plugins_config
                except Exception:
                    meta["marketplace_plugins"] = {}
            else:
                meta["marketplace_plugins"] = {}

            meta["has_plugin"] = len(plugins) > 0 or bool(meta["marketplace_plugins"].get("plugins"))
            agents.append(meta)
        except Exception:
            continue
    return agents


AGENT_CATALOG: list[dict] = _scan_agents()


def get_prompt_path(agent_id: str, category: str, language: str) -> Path:
    """Return the path to the prompt .md file for the given agent."""
    return _AGENTS_DIR / agent_id / "role" / f"{language}.md"


def read_prompt(agent_id: str, category: str, language: str) -> str:
    """Read and return the prompt content for the given agent."""
    path = get_prompt_path(agent_id, category, language)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def get_agent_by_id(agent_id: str) -> dict | None:
    """Find agent metadata by ID."""
    for agent in AGENT_CATALOG:
        if agent["id"] == agent_id:
            return agent
    return None
