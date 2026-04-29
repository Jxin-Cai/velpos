from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Awaitable, Callable

from domain.shared.async_utils import safe_create_task

from application.project.command.create_project_command import CreateProjectCommand
from application.project.command.init_plugin_command import InitPluginCommand
from application.project.command.reorder_projects_command import ReorderProjectsCommand
from application.session.command.create_session_command import CreateSessionCommand
from application.session.command.run_query_command import RunQueryCommand
from domain.session.acl.connection_manager import ConnectionManager
from application.session.session_application_service import SessionApplicationService
from domain.project.model.plugin_init_status import PluginInitStatus
from domain.project.model.plugin_type import PluginType
from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.session.repository.session_repository import SessionRepository
from domain.shared.business_exception import BusinessException
from infr.im.lark.lark_init_spec import PLUGIN_INIT_SPECS

logger = logging.getLogger(__name__)

# Section markers for CLAUDE.md — used by plugin init and agent load
_SECTION_BEGIN = "# === VP {tag} ==="
_SECTION_END = "# === End VP {tag} ==="


def _write_claude_md_section(path: str, tag: str, content: str) -> None:
    """Append or replace a tagged section in CLAUDE.md, preserving other content."""
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()

    begin = _SECTION_BEGIN.format(tag=tag)
    end = _SECTION_END.format(tag=tag)
    section = f"\n{begin}\n{content}\n{end}\n"

    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    if pattern.search(existing):
        updated = pattern.sub(section.strip(), existing)
    else:
        updated = existing.rstrip() + "\n" + section if existing.strip() else section.lstrip("\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)


def _remove_claude_md_section(path: str, tag: str) -> None:
    """Remove a tagged section from CLAUDE.md if it exists."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        existing = f.read()

    begin = _SECTION_BEGIN.format(tag=tag)
    end = _SECTION_END.format(tag=tag)
    pattern = re.compile(
        r"\n?" + re.escape(begin) + r".*?" + re.escape(end) + r"\n?",
        re.DOTALL,
    )
    updated = pattern.sub("", existing)
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)


class ProjectApplicationService:

    def __init__(
        self,
        project_repository: ProjectRepository,
        session_repository: SessionRepository,
        session_service_factory: Callable[[], Awaitable[SessionApplicationService]],
        connection_manager: ConnectionManager,
        lark_config: Any = None,
    ) -> None:
        self._project_repository = project_repository
        self._session_repository = session_repository
        self._session_service_factory = session_service_factory
        self._connection_manager = connection_manager
        self._lark_config = lark_config

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_project(self, command: CreateProjectCommand) -> Project:
        projects_root = os.getenv(
            "PROJECTS_ROOT_DIR", os.path.expanduser("~/claude-projects")
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
            stdout, stderr = await proc.communicate()
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
                        "Failed to delete session %s during project cascade, removing directly",
                        session.session_id,
                        exc_info=True,
                    )
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
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", dir_path, "rev-parse", "--abbrev-ref", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        current = stdout.decode().strip() if proc.returncode == 0 else ""

        # List all local branches
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", dir_path, "branch", "--list", "--format=%(refname:short)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        branches = [b.strip() for b in stdout.decode().splitlines() if b.strip()] if proc.returncode == 0 else []

        return {"current": current, "branches": branches}

    async def checkout_git_branch(self, project_id: str, branch: str) -> str:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")

        dir_path = project.dir_path
        if not os.path.isdir(os.path.join(dir_path, ".git")):
            raise BusinessException("Not a git repository", "NOT_GIT_REPO")

        proc = await asyncio.create_subprocess_exec(
            "git", "-C", dir_path, "checkout", branch,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "git checkout failed"
            raise BusinessException(f"Failed to checkout: {err_msg}", "GIT_CHECKOUT_FAILED")

        # Return new current branch
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", dir_path, "rev-parse", "--abbrev-ref", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() if proc.returncode == 0 else branch

    async def list_workspace_files(
        self,
        project_id: str,
        changed_only: bool = False,
        keyword: str = "",
    ) -> list[dict[str, Any]]:
        project = await self.get_project(project_id)
        root = Path(project.dir_path).resolve()
        statuses = await self._workspace_git_status(root)
        keyword = keyword.strip().lower()
        files: list[dict[str, Any]] = []

        paths = [root / p for p in statuses] if changed_only else [p for p in root.rglob("*") if p.is_file()]
        for path in paths:
            resolved = path.resolve()
            if not self._is_inside_project(root, resolved):
                continue
            if any(part in {".git", "node_modules", "__pycache__", ".venv", "dist"} for part in resolved.relative_to(root).parts):
                continue
            rel_path = resolved.relative_to(root).as_posix()
            if keyword and keyword not in rel_path.lower():
                continue
            try:
                stat = resolved.stat()
            except FileNotFoundError:
                continue
            files.append({
                "path": rel_path,
                "type": "file",
                "size": stat.st_size,
                "git_status": statuses.get(rel_path, ""),
                "is_changed": rel_path in statuses,
            })

        files.sort(key=lambda item: (not item["is_changed"], item["path"]))
        return files[:500]

    async def read_workspace_file(self, project_id: str, path: str) -> dict[str, Any]:
        project = await self.get_project(project_id)
        root = Path(project.dir_path).resolve()
        file_path = self._resolve_workspace_path(root, path)
        if not file_path.is_file():
            raise BusinessException("File not found", "FILE_NOT_FOUND")

        raw = await asyncio.to_thread(file_path.read_bytes)
        rel_path = file_path.relative_to(root).as_posix()
        return self._workspace_content_response(rel_path, raw)

    async def get_workspace_diff(self, project_id: str, path: str) -> dict[str, Any]:
        project = await self.get_project(project_id)
        root = Path(project.dir_path).resolve()
        file_path = self._resolve_workspace_path(root, path)
        rel_path = file_path.relative_to(root).as_posix()
        if not os.path.isdir(root / ".git"):
            return {"path": rel_path, "patch": "", "truncated": False}

        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(root), "diff", "--", rel_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        patch = stdout.decode(errors="replace") if proc.returncode == 0 else ""
        max_patch_len = 12000
        return {
            "path": rel_path,
            "patch": patch[:max_patch_len],
            "truncated": len(patch) > max_patch_len,
        }

    async def list_workspace_file_history(
        self,
        project_id: str,
        path: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        project = await self.get_project(project_id)
        root = Path(project.dir_path).resolve()
        file_path = self._resolve_workspace_path(root, path)
        rel_path = file_path.relative_to(root).as_posix()
        if not os.path.isdir(root / ".git"):
            return []

        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(root), "log", "--follow", f"--max-count={limit}",
            "--format=%H%x1f%h%x1f%ct%x1f%an%x1f%s", "--", rel_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []
        commits: list[dict[str, Any]] = []
        for line in stdout.decode(errors="replace").splitlines():
            parts = line.split("\x1f", 4)
            if len(parts) != 5:
                continue
            full_hash, short_hash, commit_time, author_name, message = parts
            commits.append({
                "ref": full_hash,
                "hash": full_hash,
                "short_hash": short_hash,
                "commit_time": int(commit_time or 0),
                "author_name": author_name,
                "message": message,
            })
        return commits

    async def read_workspace_file_at_ref(
        self,
        project_id: str,
        path: str,
        ref: str,
    ) -> dict[str, Any]:
        project = await self.get_project(project_id)
        root = Path(project.dir_path).resolve()
        file_path = self._resolve_workspace_path(root, path)
        rel_path = file_path.relative_to(root).as_posix()
        if not os.path.isdir(root / ".git"):
            raise BusinessException("Not a git repository", "NOT_GIT_REPO")
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(root), "show", f"{ref}:{rel_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return {
                "path": rel_path,
                "content": "",
                "encoding": "utf-8",
                "size": 0,
                "truncated": False,
                "is_binary": False,
                "missing": True,
            }
        return self._workspace_content_response(rel_path, stdout)

    async def export_workspace_selection(
        self,
        project_id: str,
        paths: list[str],
    ) -> tuple[str, bytes]:
        project = await self.get_project(project_id)
        root = Path(project.dir_path).resolve()
        normalized_paths = [path.strip().strip("/") for path in paths if path and path.strip()]
        if not normalized_paths:
            raise BusinessException("No files selected", "NO_WORKSPACE_SELECTION")

        targets: list[Path] = []
        for path in normalized_paths:
            target = self._resolve_workspace_path(root, path)
            if not target.exists():
                raise BusinessException(f"Workspace path not found: {path}", "WORKSPACE_PATH_NOT_FOUND")
            targets.append(target)

        def build_zip() -> bytes:
            buffer = io.BytesIO()
            written: set[str] = set()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for target in targets:
                    if target.is_file():
                        self._write_workspace_zip_file(root, target, archive, written)
                    elif target.is_dir():
                        if self._should_skip_workspace_path(root, target):
                            continue
                        rel_dir = target.relative_to(root).as_posix().rstrip("/")
                        if rel_dir and rel_dir not in written:
                            archive.writestr(f"{rel_dir}/", b"")
                            written.add(rel_dir)
                        for child in target.rglob("*"):
                            if child.is_file():
                                self._write_workspace_zip_file(root, child, archive, written)
            return buffer.getvalue()

        content = await asyncio.to_thread(build_zip)
        if not content:
            raise BusinessException("Selected paths contain no files", "EMPTY_WORKSPACE_SELECTION")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", project.name).strip("-._") or "workspace"
        return f"{safe_name}-export.zip", content

    def _should_skip_workspace_path(self, root: Path, path: Path) -> bool:
        return any(part in {".git", "node_modules", "__pycache__", ".venv", "dist"} for part in path.relative_to(root).parts)

    def _write_workspace_zip_file(
        self,
        root: Path,
        path: Path,
        archive: zipfile.ZipFile,
        written: set[str],
    ) -> None:
        resolved = path.resolve()
        if not self._is_inside_project(root, resolved):
            return
        rel_path = resolved.relative_to(root).as_posix()
        if self._should_skip_workspace_path(root, resolved):
            return
        if rel_path in written:
            return
        archive.write(resolved, rel_path)
        written.add(rel_path)

    def _workspace_content_response(self, rel_path: str, raw: bytes) -> dict[str, Any]:
        max_size = 200_000
        is_binary = b"\0" in raw[:4096]
        content = "" if is_binary else raw[:max_size].decode("utf-8", errors="replace")
        return {
            "path": rel_path,
            "content": content,
            "encoding": "binary" if is_binary else "utf-8",
            "size": len(raw),
            "truncated": len(raw) > max_size,
            "is_binary": is_binary,
        }

    async def _workspace_git_status(self, root: Path) -> dict[str, str]:
        if not os.path.isdir(root / ".git"):
            return {}
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(root), "status", "--porcelain",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return {}
        statuses: dict[str, str] = {}
        for line in stdout.decode(errors="replace").splitlines():
            if len(line) < 4:
                continue
            status = line[:2].strip()
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            statuses[path] = status
        return statuses

    @staticmethod
    def _is_inside_project(root: Path, path: Path) -> bool:
        return path == root or root in path.parents

    def _resolve_workspace_path(self, root: Path, path: str) -> Path:
        target = (root / path).resolve()
        if not self._is_inside_project(root, target):
            raise BusinessException("Path is outside project", "INVALID_WORKSPACE_PATH")
        return target

    async def ensure_projects_for_dirs(
        self, dir_paths: list[str]
    ) -> dict[str, str]:
        """For each dir_path, find or create a project. Return {dir_path: project_id}."""
        mappings: dict[str, str] = {}
        for dir_path in dir_paths:
            if not dir_path:
                continue
            existing = await self._project_repository.find_by_dir_path(dir_path)
            if existing:
                mappings[dir_path] = existing.id
            else:
                name = os.path.basename(dir_path.rstrip("/")) or dir_path
                project = Project.create(name=name, dir_path=dir_path)
                await self._project_repository.save(project)
                mappings[dir_path] = project.id
                logger.info(
                    "Auto-created project: id=%s, name=%s, dir=%s",
                    project.id, project.name, dir_path,
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

    # ------------------------------------------------------------------
    # Agent / Plugin uninstall
    # ------------------------------------------------------------------

    async def reset_plugin(self, project_id: str, plugin_type_str: str) -> Project:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")
        plugin_type = PluginType(plugin_type_str)
        project.reset_plugin(plugin_type)
        await self._project_repository.save(project)

        # Remove plugin section from CLAUDE.md
        claude_md_path = os.path.join(project.dir_path, "CLAUDE.md")
        await asyncio.to_thread(_remove_claude_md_section, claude_md_path, f"Plugin:{plugin_type.value}")

        logger.info("Plugin reset: project=%s, type=%s", project_id, plugin_type.value)
        return project

    # ------------------------------------------------------------------
    # Plugin init — MD-document-driven, runs in current session
    # ------------------------------------------------------------------

    async def init_plugin(self, command: InitPluginCommand) -> Project:
        project = await self._project_repository.find_by_id(command.project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")

        plugin_type = PluginType(command.plugin_type)

        if project.get_plugin_init_status(plugin_type) == PluginInitStatus.INITIALIZING:
            raise BusinessException(
                "Plugin init is already in progress", "PLUGIN_ALREADY_RUNNING"
            )

        spec = PLUGIN_INIT_SPECS.get(plugin_type)
        if spec is None:
            raise BusinessException(
                f"Unknown plugin type: {command.plugin_type}", "UNKNOWN_PLUGIN_TYPE"
            )

        # Check prerequisites
        await self._check_prerequisites(spec, project.dir_path)

        # Write plugin content to CLAUDE.md using section markers (preserve existing content)
        api_base_url = ""
        if self._lark_config:
            api_base_url = self._lark_config.api_base_url
        claude_md_content = spec.claude_md_template.format(api_base_url=api_base_url)
        claude_md_path = os.path.join(project.dir_path, "CLAUDE.md")
        await asyncio.to_thread(os.makedirs, project.dir_path, exist_ok=True)
        await asyncio.to_thread(_write_claude_md_section, claude_md_path, f"Plugin:{plugin_type.value}", claude_md_content)

        # Use current session (no new session creation)
        init_session_id = command.session_id

        project.start_plugin_init(plugin_type, init_session_id)
        await self._project_repository.save(project)

        # Read init MD document and send as prompt in current session
        init_md_content = self._read_init_md(spec.init_md_path)
        if init_md_content:
            init_md_content = init_md_content.replace(
                "PF_API_BASE_URL", api_base_url
            ).replace(
                "PF_SESSION_ID", init_session_id
            )
            safe_create_task(
                self._send_plugin_init_prompt(
                    init_session_id, init_md_content,
                    command.project_id, plugin_type,
                )
            )

        logger.info(
            "Plugin init started: project=%s, type=%s, session=%s",
            project.id, plugin_type.value, init_session_id,
        )
        return project

    async def _check_prerequisites(self, spec, project_dir: str) -> None:
        """Run prerequisite commands from the plugin spec and raise on failure."""
        for cmd in spec.prereq_commands:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=project_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    hint = f" Install: {spec.prereq_install}" if spec.prereq_install else ""
                    raise BusinessException(
                        f"Prerequisite check failed: `{cmd}` exited with code {proc.returncode}.{hint}",
                        "PREREQ_FAILED",
                    )
            except FileNotFoundError:
                hint = f" Install: {spec.prereq_install}" if spec.prereq_install else ""
                raise BusinessException(
                    f"Prerequisite not found: `{cmd}`.{hint}",
                    "PREREQ_FAILED",
                )

    @staticmethod
    def _read_init_md(path: str) -> str:
        """Read an init MD file relative to the backend directory."""
        if not path:
            return ""
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        full_path = os.path.join(backend_dir, path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("Init MD not found: %s", full_path)
            return ""

    async def _send_plugin_init_prompt(
        self, init_session_id: str, init_md_content: str,
        project_id: str, plugin_type: PluginType,
    ) -> None:
        svc = None
        try:
            svc = await self._session_service_factory()
            await svc.set_permission_mode(init_session_id, "bypassPermissions")
            try:
                await svc.run_claude_query(
                    RunQueryCommand(session_id=init_session_id, prompt=init_md_content)
                )
            finally:
                # Always restore permission mode to default after plugin init,
                # regardless of success or failure
                await svc.set_permission_mode(init_session_id, "default")
            await svc.commit()

            # Do NOT auto-complete here — the plugin init prompt should call
            # POST /api/projects/{id}/complete-plugin-init explicitly when done.
            logger.info(
                "Plugin init prompt sent: project=%s, type=%s (awaiting explicit completion)",
                project_id, plugin_type.value,
            )
        except Exception:
            logger.error(
                "Failed to send plugin init prompt: session=%s",
                init_session_id, exc_info=True,
            )
            try:
                await self._auto_fail_plugin_init(project_id, plugin_type)
            except Exception:
                logger.warning(
                    "Auto-fail plugin init failed: project=%s", project_id, exc_info=True
                )
        finally:
            if svc is not None:
                await svc.close()

    async def _auto_complete_plugin_init(
        self, project_id: str, plugin_type: PluginType,
    ) -> None:
        from infr.config.database import async_session_factory
        from infr.repository.project_repository_impl import ProjectRepositoryImpl

        async with async_session_factory() as db_session:
            repo = ProjectRepositoryImpl(db_session)
            project = await repo.find_by_id(project_id)
            if project is None:
                return
            if project.get_plugin_init_status(plugin_type) == PluginInitStatus.INITIALIZING:
                project.complete_plugin_init(plugin_type)
                await repo.save(project)
                await db_session.commit()
                logger.info(
                    "Plugin init auto-completed: project=%s, type=%s",
                    project_id, plugin_type.value,
                )

    async def _auto_fail_plugin_init(
        self, project_id: str, plugin_type: PluginType,
    ) -> None:
        from infr.config.database import async_session_factory
        from infr.repository.project_repository_impl import ProjectRepositoryImpl

        async with async_session_factory() as db_session:
            repo = ProjectRepositoryImpl(db_session)
            project = await repo.find_by_id(project_id)
            if project is None:
                return
            if project.get_plugin_init_status(plugin_type) == PluginInitStatus.INITIALIZING:
                project.fail_plugin_init(plugin_type)
                await repo.save(project)
                await db_session.commit()
                logger.info(
                    "Plugin init auto-failed: project=%s, type=%s",
                    project_id, plugin_type.value,
                )

    async def complete_plugin_init(
        self, project_id: str, plugin_type_str: str,
    ) -> Project:
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found", "PROJECT_NOT_FOUND")

        plugin_type = PluginType(plugin_type_str)

        if project.get_plugin_init_status(plugin_type) != PluginInitStatus.INITIALIZING:
            raise BusinessException(
                "Plugin init is not in progress", "PLUGIN_NOT_INITIALIZING"
            )

        project.complete_plugin_init(plugin_type)
        await self._project_repository.save(project)
        logger.info(
            "Plugin init completed: project=%s, type=%s",
            project_id, plugin_type.value,
        )
        return project
