from __future__ import annotations

from typing import Any

from domain.project.model.project import Project


class ProjectAssembler:
    @staticmethod
    def to_dict(project: Project) -> dict[str, Any]:
        return {
            "id": project.id,
            "name": project.name,
            "dir_path": project.dir_path,
            "agents": project.agents,
            "plugins": project.plugins,
            "sort_order": project.sort_order,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }
