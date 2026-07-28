from __future__ import annotations

from pathlib import Path
from uuid import uuid4


_WORKSPACE_ID_LENGTH = 8
_MAX_ALLOCATION_ATTEMPTS = 10


def default_agent_workspace_root() -> Path:
    return Path.home() / ".velpos" / "agents"


def default_team_workspace_root() -> Path:
    return Path.home() / ".velpos" / "teams"


def github_repository_name(github_url: str) -> str:
    repository = github_url.strip().rstrip("/").rsplit("/", maxsplit=1)[-1]
    repository = repository.rsplit(":", maxsplit=1)[-1]
    if repository.endswith(".git"):
        repository = repository[:-4]
    return repository


def create_workspace_directory(root_path: str) -> Path:
    """Create an isolated workspace under the supplied workspace root."""
    normalized_root = root_path.strip()
    if not normalized_root:
        raise ValueError("Project directory is required")

    root = Path(normalized_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    for _ in range(_MAX_ALLOCATION_ATTEMPTS):
        workspace = root / uuid4().hex[:_WORKSPACE_ID_LENGTH]
        try:
            workspace.mkdir()
        except FileExistsError:
            continue
        return workspace

    raise RuntimeError("Failed to allocate a unique workspace directory")
