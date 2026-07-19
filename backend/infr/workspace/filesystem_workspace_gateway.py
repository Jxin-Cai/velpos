import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from domain.team.acl.workspace_gateway import WorkspaceGateway
from infr.agent.catalog import get_agent_by_id, read_prompt


_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MANIFEST_PATH = Path(".velpos/agent-manifest.json")
_SCHEMA_VERSION = 1


class FilesystemWorkspaceGateway(WorkspaceGateway):
    """Prepare isolated team slot and execution directories on local disk."""

    def __init__(self) -> None:
        self._team_roots: set[Path] = set()

    def create_independent_workspace(
        self,
        team_root: str,
        team_slug: str,
        slot_slug: str,
        project_root: str,
        agent_profile_ref: str | None = None,
    ) -> str:
        root = self._prepare_team_root(team_root)
        team = self._normalize_slug(team_slug, "team_slug")
        slot = self._normalize_slug(slot_slug, "slot_slug")
        source = self._resolve_existing_directory(project_root, "project_root")
        target = self._confined_path(root, f"{team}-{slot}")
        profile_ref = agent_profile_ref or slot_slug
        files, plugin_references, source_hash = self._read_allowed_source(source)
        files, plugin_references = self._apply_agent_profile(
            files,
            plugin_references,
            profile_ref,
        )
        source_hash = self._hash_files(files)

        if target.exists() or target.is_symlink():
            self._validate_existing_workspace(
                target,
                root,
                team_slug,
                slot_slug,
                team,
                slot,
                profile_ref,
                source_hash,
            )
            return str(target.resolve(strict=True))

        staging = Path(tempfile.mkdtemp(prefix=".workspace-", dir=root))
        try:
            self._write_workspace(
                staging,
                team_slug,
                slot_slug,
                team,
                slot,
                profile_ref,
                source,
                files,
                plugin_references,
                source_hash,
            )
            try:
                staging.replace(target)
            except OSError:
                if not target.exists():
                    raise
                self._validate_existing_workspace(
                    target,
                    root,
                    team_slug,
                    slot_slug,
                    team,
                    slot,
                    profile_ref,
                    source_hash,
                )
            return str(target.resolve(strict=True))
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def create_execution_workspace(
        self,
        workspace_ref: str,
        execution_id: str,
    ) -> str:
        workspace = Path(workspace_ref).resolve(strict=True)
        root = self._registered_root_for(workspace)
        self._ensure_confined(workspace, root)
        self._load_manifest(workspace)
        execution = self._normalize_slug(execution_id, "execution_id")
        executions_root = self._confined_path(workspace, "executions")
        self._reject_symlink(executions_root, "executions directory")
        executions_root.mkdir(exist_ok=True)
        target = self._confined_path(executions_root, execution)

        if target.exists() or target.is_symlink():
            self._reject_symlink(target, "execution workspace")
            return str(target.resolve(strict=True))

        staging = Path(tempfile.mkdtemp(prefix=".execution-", dir=executions_root))
        try:
            self._copy_execution_snapshot(workspace, staging)
            try:
                staging.replace(target)
            except OSError:
                if not target.is_dir() or target.is_symlink():
                    raise
            resolved = target.resolve(strict=True)
            self._ensure_confined(resolved, root)
            return str(resolved)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def remove_workspace(self, workspace_ref: str) -> None:
        workspace = Path(workspace_ref).resolve(strict=True)
        root = self._registered_root_for(workspace)
        self._ensure_confined(workspace, root)
        self._load_manifest(workspace)
        shutil.rmtree(workspace)

    def _prepare_team_root(self, value: str) -> Path:
        path = Path(value).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        root = path.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("team_root must be a directory")
        self._team_roots.add(root)
        return root

    @staticmethod
    def _resolve_existing_directory(value: str, name: str) -> Path:
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError(f"{name} must be a directory")
        return path

    @staticmethod
    def _normalize_slug(value: str, name: str) -> str:
        if not value or Path(value).is_absolute() or "/" in value or "\\" in value:
            raise ValueError(f"invalid {name}")
        normalized = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
        normalized = normalized.strip(".-")
        if not _SLUG_PATTERN.fullmatch(normalized):
            raise ValueError(f"invalid {name}")
        return normalized

    def _confined_path(self, root: Path, child: str) -> Path:
        candidate = root / child
        self._reject_symlink(candidate, "workspace path")
        self._ensure_confined(candidate.resolve(strict=False), root)
        return candidate

    @staticmethod
    def _ensure_confined(candidate: Path, root: Path) -> None:
        if candidate != root and not candidate.is_relative_to(root):
            raise ValueError("path escapes team root")

    @staticmethod
    def _reject_symlink(path: Path, name: str) -> None:
        if path.is_symlink():
            raise ValueError(f"{name} cannot be a symlink")

    def _registered_root_for(self, path: Path) -> Path:
        for root in self._team_roots:
            if path != root and path.is_relative_to(root):
                return root
        # Gateway instances are request-scoped; recover the team root from a
        # previously materialized slot workspace when handling a later card.
        candidate = path.parent
        if candidate.is_dir() and (path / _MANIFEST_PATH).is_file():
            self._team_roots.add(candidate)
            return candidate
        raise ValueError("workspace is outside registered team roots")

    @staticmethod
    def _read_allowed_source(
        project_root: Path,
    ) -> tuple[dict[str, bytes], tuple[str, ...], str]:
        files: dict[str, bytes] = {}
        claude_md = project_root / "CLAUDE.md"
        if claude_md.is_file() and not claude_md.is_symlink():
            files["CLAUDE.md"] = claude_md.read_bytes()

        rules_root = project_root / ".claude" / "rules"
        if rules_root.is_dir() and not rules_root.is_symlink():
            for rule in sorted(rules_root.rglob("*")):
                if rule.is_file() and not rule.is_symlink():
                    relative = rule.relative_to(project_root).as_posix()
                    files[relative] = rule.read_bytes()

        plugins: tuple[str, ...] = ()
        settings_path = project_root / ".claude" / "settings.json"
        if settings_path.is_file() and not settings_path.is_symlink():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(settings, dict):
                raise ValueError("project settings must be an object")
            enabled = settings.get("enabledPlugins", {})
            if not isinstance(enabled, dict) or not all(
                isinstance(key, str) and isinstance(value, bool)
                for key, value in enabled.items()
            ):
                raise ValueError("enabledPlugins must be a string-to-boolean object")
            plugins = tuple(
                sorted(key for key, enabled_flag in enabled.items() if enabled_flag)
            )
            sanitized = {
                "enabledPlugins": {key: enabled[key] for key in sorted(enabled)}
            }
            files[".claude/settings.json"] = (
                json.dumps(sanitized, indent=2, sort_keys=True) + "\n"
            ).encode()

        digest = hashlib.sha256()
        for relative_path in sorted(files):
            digest.update(relative_path.encode())
            digest.update(b"\0")
            digest.update(files[relative_path])
            digest.update(b"\0")
        return files, plugins, digest.hexdigest()

    @classmethod
    def _apply_agent_profile(
        cls,
        files: dict[str, bytes],
        project_plugins: tuple[str, ...],
        agent_profile_ref: str,
    ) -> tuple[dict[str, bytes], tuple[str, ...]]:
        profile = get_agent_by_id(agent_profile_ref)
        if profile is None:
            return files, project_plugins

        prompt = read_prompt(agent_profile_ref, "en").strip()
        project_instructions = files.get("CLAUDE.md", b"").decode(
            "utf-8",
            errors="replace",
        ).strip()
        sections = [prompt]
        if project_instructions:
            sections.append(
                "# Project Instructions\n\n"
                "The following instructions come from the selected project and still apply.\n\n"
                f"{project_instructions}"
            )

        local_plugins = tuple(
            plugin["name"]
            for plugin in profile.get("plugins", [])
            if isinstance(plugin, dict) and isinstance(plugin.get("name"), str)
        )
        marketplace_plugins = tuple(
            plugin
            for plugin in profile.get("marketplace_plugins", {}).get("plugins", [])
            if isinstance(plugin, str)
        )
        plugin_references = tuple(
            sorted(set(project_plugins + local_plugins + marketplace_plugins))
        )
        profiled_files = {
            **files,
            "CLAUDE.md": ("\n\n".join(sections) + "\n").encode(),
        }
        if plugin_references:
            profiled_files[".claude/settings.json"] = (
                json.dumps(
                    {"enabledPlugins": {plugin: True for plugin in plugin_references}},
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        return profiled_files, plugin_references

    @staticmethod
    def _hash_files(files: dict[str, bytes]) -> str:
        digest = hashlib.sha256()
        for relative_path in sorted(files):
            digest.update(relative_path.encode())
            digest.update(b"\0")
            digest.update(files[relative_path])
            digest.update(b"\0")
        return digest.hexdigest()

    @classmethod
    def _write_workspace(
        cls,
        staging: Path,
        team_ref: str,
        slot_ref: str,
        team_slug: str,
        slot_slug: str,
        agent_profile_ref: str,
        project_root: Path,
        files: dict[str, bytes],
        plugins: tuple[str, ...],
        source_hash: str,
    ) -> None:
        if "CLAUDE.md" not in files:
            files = {
                **files,
                "CLAUDE.md": (
                    "# Team Agent Workspace\n\n"
                    f"Agent profile: `{agent_profile_ref}`.\n"
                ).encode(),
            }
        for relative_path, content in files.items():
            destination = staging / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        (staging / "executions").mkdir()
        manifest: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "team_ref": team_ref,
            "slot_ref": slot_ref,
            "team_slug": team_slug,
            "slot_slug": slot_slug,
            "agent_profile_ref": agent_profile_ref,
            "project_root": str(project_root),
            "source_config_hash": source_hash,
            "plugin_references": list(plugins),
        }
        cls._atomic_write_json(staging / _MANIFEST_PATH, manifest)

    def _validate_existing_workspace(
        self,
        target: Path,
        root: Path,
        team_ref: str,
        slot_ref: str,
        team_slug: str,
        slot_slug: str,
        agent_profile_ref: str,
        source_hash: str,
    ) -> None:
        resolved = target.resolve(strict=True)
        self._ensure_confined(resolved, root)
        if resolved != target.absolute():
            raise ValueError("workspace path cannot be a symlink")
        manifest = self._load_manifest(resolved)
        expected = (
            team_ref,
            slot_ref,
            team_slug,
            slot_slug,
            agent_profile_ref,
            source_hash,
        )
        actual = (
            manifest.get("team_ref"),
            manifest.get("slot_ref"),
            manifest.get("team_slug"),
            manifest.get("slot_slug"),
            manifest.get("agent_profile_ref"),
            manifest.get("source_config_hash"),
        )
        if actual != expected:
            raise FileExistsError("workspace exists with different source or identity")

    @staticmethod
    def _load_manifest(workspace: Path) -> dict[str, Any]:
        manifest_path = workspace / _MANIFEST_PATH
        if manifest_path.is_symlink():
            raise ValueError("workspace manifest cannot be a symlink")
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != _SCHEMA_VERSION:
            raise ValueError("invalid workspace manifest")
        return value

    @staticmethod
    def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_execution_snapshot(workspace: Path, execution: Path) -> None:
        for source in (workspace / "CLAUDE.md", workspace / ".claude"):
            if not source.exists():
                continue
            destination = execution / source.relative_to(workspace)
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=False)
            else:
                shutil.copy2(source, destination)
        for path in sorted(execution.rglob("*"), reverse=True):
            path.chmod(0o555 if path.is_dir() else 0o444)
