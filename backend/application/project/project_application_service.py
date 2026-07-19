from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from application.git_helpers import run_git

from application.project.command.create_project_command import CreateProjectCommand
from application.project.command.reorder_projects_command import ReorderProjectsCommand
from domain.session.acl.connection_manager import ConnectionManager
from application.session.session_application_service import SessionApplicationService
from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.session.repository.session_repository import SessionRepository
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


class ProjectApplicationService:

    def __init__(
        self,
        project_repository: ProjectRepository,
        session_repository: SessionRepository,
        session_service_factory: Callable[[], Awaitable[SessionApplicationService]],
        connection_manager: ConnectionManager,
    ) -> None:
        self._project_repository = project_repository
        self._session_repository = session_repository
        self._session_service_factory = session_service_factory
        self._connection_manager = connection_manager

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_project(self, command: CreateProjectCommand) -> Project:
        projects_root = os.getenv(
            "PROJECTS_ROOT_DIR", os.path.expanduser("~/.velpos/agents")
        )
        dir_path = os.path.join(projects_root, command.name.strip())

        if command.github_url:
            # Clone from GitHub — relies on local Git auth (SSH key / credential helper)
            await asyncio.to_thread(os.makedirs, projects_root, exist_ok=True)
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", command.github_url, dir_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_msg = stderr.decode().strip() if stderr else "git clone failed"
                raise BusinessException(
                    f"Failed to clone repository: {err_msg}",
                    "GIT_CLONE_FAILED",
                )
        else:
            await asyncio.to_thread(os.makedirs, dir_path, exist_ok=True)
            # Auto git init + initial commit so branch exists immediately
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "init", dir_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                if proc.returncode != 0:
                    logger.warning("git init failed for %s", dir_path)
                else:
                    # Create initial commit so 'master' branch exists.
                    # Read global gitconfig; fall back to defaults if unset.
                    from application.git.git_application_service import GitApplicationService
                    git_svc = GitApplicationService()
                    cfg = await git_svc.get_git_config()
                    u_name = cfg["user_name"] or "Velpos"
                    u_email = cfg["user_email"] or "velpos@local"
                    for cmd in [
                        ["git", "-C", dir_path, "checkout", "-b", "master"],
                        [
                            "git", "-C", dir_path,
                            "-c", f"user.name={u_name}",
                            "-c", f"user.email={u_email}",
                            "commit", "--allow-empty", "-m", "init",
                        ],
                    ]:
                        p = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        await p.communicate()
            except Exception:
                logger.warning("git init failed for %s", dir_path, exc_info=True)

        project = Project.create(name=command.name.strip(), dir_path=dir_path)
        await self._project_repository.save(project)
        logger.info("Project created: id=%s, name=%s", project.id, project.name)
        return project

    async def list_projects(self) -> list[Project]:
        return await self._project_repository.find_all()

    async def get_project(self, project_id: str) -> Project:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")
        return project

        mode = config.get("mode")
        if mode not in ("delegation", "collaboration"):
            raise BusinessException("Invalid team mode, must be 'delegation' or 'collaboration'", "INVALID_TEAM_MODE")

        members_key = "pipeline" if mode == "delegation" else "members"
        members = config.get(members_key, [])
        if not isinstance(members, list) or not members:
            raise BusinessException("Team must have at least one member", "TEAM_NO_MEMBERS")

        seen_project_ids = set()
        seen_roles = set()
        for member in members:
            if not isinstance(member, dict):
                raise BusinessException("Each team member must be an object", "INVALID_MEMBER")
            pid = member.get("project_id")
            role = member.get("role")
            if not pid:
                raise BusinessException("Each member must reference a project_id", "MEMBER_NO_PROJECT")
            if not role:
                raise BusinessException("Each member must define a role", "MEMBER_NO_ROLE")
            if pid in seen_project_ids:
                raise BusinessException(f"Duplicate project_id in team: {pid}", "DUPLICATE_MEMBER")
            if role in seen_roles:
                raise BusinessException(f"Duplicate role in team: {role}", "DUPLICATE_ROLE")
            seen_project_ids.add(pid)
            seen_roles.add(role)
            sub_project = await self._project_repository.find_by_id(pid)
            if sub_project is None:
                raise BusinessException(f"Sub-project not found: {pid}", "SUB_PROJECT_NOT_FOUND")
            if sub_project.project_type == "team":
                raise BusinessException(f"Cannot use a team project as a sub-project: {pid}", "NESTED_TEAM")

        self._validate_int_range(config, "max_concurrent", 1, 10)
        self._validate_int_range(config, "worker_max_turns", 1, 200)
        self._validate_number_range(config, "worker_max_budget_usd", 0.1, 50)
        self._validate_int_range(config, "max_depth", 1, 10)

        if "file_checkpointing" in config and not isinstance(config.get("file_checkpointing"), bool):
            raise BusinessException("file_checkpointing must be a boolean", "INVALID_FILE_CHECKPOINTING")

        if mode == "collaboration":
            default_workflow = config.get("default_workflow", [])
            if default_workflow and not isinstance(default_workflow, list):
                raise BusinessException("default_workflow must be a list", "INVALID_DEFAULT_WORKFLOW")
            unknown_roles = [role for role in default_workflow if role not in seen_roles]
            if unknown_roles:
                raise BusinessException(
                    f"default_workflow contains unknown roles: {', '.join(unknown_roles)}",
                    "INVALID_DEFAULT_WORKFLOW",
                )

        return mode

    @staticmethod
    def _validate_int_range(config: dict, key: str, minimum: int, maximum: int) -> None:
        if key not in config:
            return
        value = config.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > maximum:
            raise BusinessException(f"{key} must be an integer between {minimum} and {maximum}", f"INVALID_{key.upper()}")

    @staticmethod
    def _validate_number_range(config: dict, key: str, minimum: float, maximum: float) -> None:
        if key not in config:
            return
        value = config.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum or value > maximum:
            raise BusinessException(f"{key} must be between {minimum} and {maximum}", f"INVALID_{key.upper()}")

    async def get_sessions_by_project(self, project_id: str) -> list:
        """Return all sessions belonging to a project."""
        return await self._session_repository.find_by_project_id(project_id)

    async def delete_project(self, project_id: str) -> None:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")

        # Cascade delete sessions under this project via SessionApplicationService
        # so that gateway disconnect/cleanup is properly called
        sessions = await self._session_repository.find_by_project_id(project_id)
        svc = await self._session_service_factory()
        try:
            for session in sessions:
                try:
                    await svc.delete_session(session.session_id)
                except Exception:
                    logger.warning(
                        "Failed to delete session %s during project cascade, attempting partial cleanup",
                        session.session_id,
                        exc_info=True,
                    )
                    await svc.force_cleanup(session.session_id)
                    await self._session_repository.remove(session.session_id)
        finally:
            # Commit and close the standalone DB session created by the factory
            try:
                await svc.commit()
                await svc.close()
            except Exception:
                logger.debug("Failed to close cascade session DB session", exc_info=True)

        await self._project_repository.remove(project_id)

        logger.info("Project deleted: id=%s (cascade %d sessions)", project_id, len(sessions))

        # Clean up Claude Code session JSONL files so the project doesn't
        # get re-created on next page refresh via ensureProjectsByDirs.
        try:
            mgr = getattr(svc, "_claude_session_manager", None)
            if mgr and hasattr(mgr, "delete_all_sessions_in_dir"):
                deleted = mgr.delete_all_sessions_in_dir(project.dir_path)
                if deleted:
                    logger.info(
                        "Deleted %d CC session JSONL files for dir=%s",
                        deleted, project.dir_path,
                    )
        except Exception:
            logger.warning(
                "Failed to clean CC session files for project=%s",
                project_id, exc_info=True,
            )

    async def reorder_projects(self, command: ReorderProjectsCommand) -> None:
        projects_to_save = []
        for idx, pid in enumerate(command.ordered_ids):
            project = await self._project_repository.find_by_id(pid)
            if project is not None:
                # Higher index = higher priority (first in list = highest sort_order)
                project.update_sort_order(len(command.ordered_ids) - idx)
                projects_to_save.append(project)
        # Save all in a single batch so any failure rolls back completely
        for project in projects_to_save:
            await self._project_repository.save(project)

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    async def list_git_branches(self, project_id: str) -> dict[str, Any]:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")

        dir_path = project.dir_path
        if not os.path.isdir(os.path.join(dir_path, ".git")):
            return {"current": "", "branches": []}

        # Get current branch
        result = await run_git(dir_path, "rev-parse", "--abbrev-ref", "HEAD")
        current = result.stdout if result.ok else ""

        # List all local branches
        result = await run_git(dir_path, "branch", "--list", "--format=%(refname:short)")
        branches = [b.strip() for b in result.stdout.splitlines() if b.strip()] if result.ok else []

        return {"current": current, "branches": branches}

    async def checkout_git_branch(self, project_id: str, branch: str) -> str:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")

        dir_path = project.dir_path
        if not os.path.isdir(os.path.join(dir_path, ".git")):
            raise BusinessException("Not a git repository", "NOT_GIT_REPO")

        result = await run_git(dir_path, "checkout", branch)
        if not result.ok:
            err_msg = result.stderr or "git checkout failed"
            raise BusinessException(f"Failed to checkout: {err_msg}", "GIT_CHECKOUT_FAILED")

        # Return new current branch
        result = await run_git(dir_path, "rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout if result.ok else branch

    async def ensure_projects_for_dirs(
        self, dir_paths: list[str]
    ) -> dict[str, str]:
        """For each dir_path, find or create a project. Return {dir_path: project_id}."""
        mappings: dict[str, str] = {}
        for dir_path in dir_paths:
            if not dir_path:
                continue
            normalized = str(Path(dir_path).expanduser().resolve())
            existing = await self._project_repository.find_by_dir_path(normalized)
            if existing:
                mappings[dir_path] = existing.id
            else:
                name = os.path.basename(normalized) or dir_path
                project = Project.create(name=name, dir_path=normalized)
                await self._project_repository.save(project)
                mappings[dir_path] = project.id
                logger.info(
                    "Auto-created project: id=%s, name=%s, dir=%s",
                    project.id, project.name, normalized,
                )
        return mappings

    async def pick_directory(self) -> str:
        if sys.platform != "darwin":
            raise BusinessException("Directory picker is only supported on macOS", "UNSUPPORTED_PLATFORM")

        proc = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            'POSIX path of (choose folder with prompt "Select project folder")',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "directory picker failed"
            if "User canceled" in err_msg or "(-128)" in err_msg:
                return ""
            raise BusinessException(
                f"Failed to pick directory: {err_msg}",
                "DIRECTORY_PICK_FAILED",
            )

        return stdout.decode().strip()
