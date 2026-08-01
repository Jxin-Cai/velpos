from __future__ import annotations

from pathlib import Path

from domain.project.acl.workspace_root_resolver import WorkspaceRootResolver
from infr.config.app_config import app_config


class WorkspaceRootResolverImpl(WorkspaceRootResolver):

    def user_root(self, user_id: int) -> Path:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        return app_config.projects_root_dir / str(user_id)

    def agent_root(self, user_id: int) -> Path:
        return self.user_root(user_id) / "agents"

    def team_root(self, user_id: int) -> Path:
        return self.user_root(user_id) / "teams"
