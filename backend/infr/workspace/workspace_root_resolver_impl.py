from __future__ import annotations

from pathlib import Path

from domain.project.acl.workspace_root_resolver import WorkspaceRootResolver
from infr.config.app_config import app_config


class WorkspaceRootResolverImpl(WorkspaceRootResolver):

    def agent_root(self, user_id: int) -> Path:
        base = Path.home() / ".velpos"
        if app_config.mode == "pro":
            return base / str(user_id) / "agents"
        return base / "agents"

    def team_root(self, user_id: int) -> Path:
        base = Path.home() / ".velpos"
        if app_config.mode == "pro":
            return base / str(user_id) / "teams"
        return base / "teams"
