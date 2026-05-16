from __future__ import annotations

import asyncio
import json
import os
import logging
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from application.memory.claude_md_revision_application_service import ClaudeMdRevisionApplicationService
from domain.memory.model.claude_md_revision import ClaudeMdRevision
from ohs.dependencies import get_claude_md_revision_application_service
from ohs.http.api_response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory"])

ClaudeMdRevisionServiceDep = Annotated[
    ClaudeMdRevisionApplicationService,
    Depends(get_claude_md_revision_application_service),
]


def _get_memory_dir(project_dir: str) -> Path | None:
    """Resolve the Claude Code project memory directory for a given project_dir."""
    from claude_agent_sdk._internal.sessions import _canonicalize_path, _find_project_dir

    canonical = _canonicalize_path(project_dir)
    proj_dir = _find_project_dir(canonical)
    if proj_dir is None:
        return None
    return proj_dir / "memory"


def _get_rules_dir(project_dir: str) -> Path | None:
    project_path = Path(project_dir).expanduser().resolve()
    if not project_path.is_dir():
        return None
    return project_path / ".claude" / "rules"


def _resolve_rule_file(rules_dir: Path, rule_path: str) -> Path | None:
    path = PurePosixPath(rule_path)
    if not rule_path or path.is_absolute() or path.suffix.lower() != ".md" or ".." in path.parts:
        return None
    file_path = (rules_dir / Path(*path.parts)).resolve()
    rules_root = rules_dir.resolve()
    if not file_path.is_relative_to(rules_root):
        return None
    return file_path


def _validate_rule_paths(paths: list[str]) -> list[str] | None:
    cleaned = []
    for item in paths:
        value = item.strip()
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts:
            return None
        cleaned.append(value)
    return cleaned


def _parse_rule_markdown(raw: str) -> tuple[list[str], str]:
    if not raw.startswith("---\n"):
        return [], raw
    end = raw.find("\n---", 4)
    if end < 0:
        return [], raw
    frontmatter = raw[4:end].splitlines()
    content_start = end + len("\n---")
    if raw[content_start:content_start + 1] == "\n":
        content_start += 1
    paths = []
    in_paths = False
    for line in frontmatter:
        stripped = line.strip()
        if stripped == "paths:":
            in_paths = True
            continue
        if in_paths and stripped.startswith("-"):
            paths.append(stripped[1:].strip().strip('"').strip("'"))
        elif in_paths and stripped:
            in_paths = False
    return paths, raw[content_start:]


def _compose_rule_markdown(content: str, paths: list[str]) -> str:
    if not paths:
        return content
    lines = ["---", "paths:"]
    lines.extend(f"  - {json.dumps(path, ensure_ascii=False)}" for path in paths)
    lines.append("---")
    lines.append(content)
    return "\n".join(lines)


def _rule_to_dict(file_path: Path, rules_dir: Path) -> dict:
    raw = file_path.read_text(encoding="utf-8")
    paths, content = _parse_rule_markdown(raw)
    relative_path = file_path.relative_to(rules_dir).as_posix()
    return {
        "path": relative_path,
        "name": file_path.name,
        "content": content,
        "paths": paths,
        "size": len(raw),
        "updated_time": file_path.stat().st_mtime,
    }


class MemoryFileWrite(BaseModel):
    project_dir: str
    content: str


class RuleFileWrite(BaseModel):
    project_dir: str
    content: str = ""
    paths: list[str] = []


class ClaudeMdDraftRequest(BaseModel):
    project_dir: str
    content: str
    base_revision_id: str = ""


class ClaudeMdUpdateRequest(BaseModel):
    content: str


class ClaudeMdRejectRequest(BaseModel):
    reason: str = ""


class ClaudeMdApplyRequest(BaseModel):
    project_dir: str
    expected_base_revision_id: str
    expected_file_hash: str


def _revision_to_dict(revision: ClaudeMdRevision) -> dict:
    return ClaudeMdRevisionApplicationService._revision_to_dict(revision)


@router.get("/claude-md")
async def read_claude_md(
    service: ClaudeMdRevisionServiceDep,
    project_dir: str = Query(...),
):
    """Read project CLAUDE.md and initialize revision history if needed."""
    data = await service.read_current(project_dir)
    return ApiResponse.success(data=data)


@router.put("/claude-md")
async def write_claude_md(
    body: MemoryFileWrite,
    service: ClaudeMdRevisionServiceDep,
):
    """Create a draft revision for project CLAUDE.md without writing the file."""
    revision = await service.create_draft(body.project_dir, body.content)
    logger.info("CLAUDE.md draft created: %s", revision.id)
    return ApiResponse.success(data={"revision": _revision_to_dict(revision)})


@router.get("/claude-md/versions")
async def list_claude_md_versions(
    service: ClaudeMdRevisionServiceDep,
    project_dir: str = Query(...),
):
    revisions = await service.list_versions(project_dir)
    return ApiResponse.success(data={"versions": [_revision_to_dict(r) for r in revisions]})


@router.post("/claude-md/drafts")
async def create_claude_md_draft(
    body: ClaudeMdDraftRequest,
    service: ClaudeMdRevisionServiceDep,
):
    revision = await service.create_draft(
        project_dir=body.project_dir,
        content=body.content,
        base_revision_id=body.base_revision_id,
    )
    return ApiResponse.success(data={"revision": _revision_to_dict(revision)})


@router.patch("/claude-md/revisions/{revision_id}")
async def update_claude_md_revision(
    revision_id: str,
    body: ClaudeMdUpdateRequest,
    service: ClaudeMdRevisionServiceDep,
):
    revision = await service.update_revision(revision_id, body.content)
    return ApiResponse.success(data={"revision": _revision_to_dict(revision)})


@router.post("/claude-md/revisions/{revision_id}/propose")
async def propose_claude_md_revision(
    revision_id: str,
    service: ClaudeMdRevisionServiceDep,
):
    revision = await service.propose(revision_id)
    return ApiResponse.success(data={"revision": _revision_to_dict(revision)})


@router.post("/claude-md/revisions/{revision_id}/approve")
async def approve_claude_md_revision(
    revision_id: str,
    service: ClaudeMdRevisionServiceDep,
):
    revision = await service.approve(revision_id)
    return ApiResponse.success(data={"revision": _revision_to_dict(revision)})


@router.post("/claude-md/revisions/{revision_id}/reject")
async def reject_claude_md_revision(
    revision_id: str,
    body: ClaudeMdRejectRequest,
    service: ClaudeMdRevisionServiceDep,
):
    revision = await service.reject(revision_id, body.reason)
    return ApiResponse.success(data={"revision": _revision_to_dict(revision)})


@router.post("/claude-md/revisions/{revision_id}/apply")
async def apply_claude_md_revision(
    revision_id: str,
    body: ClaudeMdApplyRequest,
    service: ClaudeMdRevisionServiceDep,
):
    result = await service.apply(
        revision_id=revision_id,
        project_dir=body.project_dir,
        expected_base_revision_id=body.expected_base_revision_id,
        expected_file_hash=body.expected_file_hash,
    )
    data = {
        "revision": _revision_to_dict(result.revision),
        "conflict": result.conflict,
        "current_file_hash": result.current_file_hash,
    }
    if result.conflict:
        response = ApiResponse.fail(code=-409, message="CLAUDE.md has changed on disk")
        payload = response.model_dump()
        payload["data"] = data
        return JSONResponse(status_code=409, content=payload)
    return ApiResponse.success(data=data)


@router.delete("/claude-md/revisions/{revision_id}")
async def delete_claude_md_revision(
    revision_id: str,
    service: ClaudeMdRevisionServiceDep,
):
    await service.delete_revision(revision_id)
    return ApiResponse.success()


@router.get("/claude-md/revisions/{revision_id}/diff")
async def diff_claude_md_revision(
    revision_id: str,
    service: ClaudeMdRevisionServiceDep,
):
    return ApiResponse.success(data=await service.diff_revision(revision_id))


@router.get("/rules")
async def list_rules(project_dir: str = Query(...)):
    rules_dir = _get_rules_dir(project_dir)
    if rules_dir is None or not rules_dir.exists():
        return ApiResponse.success(data={"rules": []})

    def _scan():
        result = []
        for file_path in sorted(rules_dir.rglob("*.md")):
            if file_path.is_file():
                result.append(_rule_to_dict(file_path, rules_dir))
        return result

    rules = await asyncio.to_thread(_scan)
    return ApiResponse.success(data={"rules": rules})


@router.get("/rules/{rule_path:path}")
async def read_rule(rule_path: str, project_dir: str = Query(...)):
    rules_dir = _get_rules_dir(project_dir)
    if rules_dir is None:
        return ApiResponse.fail(code=-1, message="Project directory not found")
    file_path = _resolve_rule_file(rules_dir, rule_path)
    if file_path is None:
        return ApiResponse.fail(code=-1, message="Invalid rule path")
    if not file_path.exists() or not file_path.is_file():
        return ApiResponse.fail(code=-1, message="Rule not found")
    rule = await asyncio.to_thread(_rule_to_dict, file_path, rules_dir)
    return ApiResponse.success(data={"rule": rule})


@router.put("/rules/{rule_path:path}")
async def write_rule(rule_path: str, body: RuleFileWrite):
    rules_dir = _get_rules_dir(body.project_dir)
    if rules_dir is None:
        return ApiResponse.fail(code=-1, message="Project directory not found")
    file_path = _resolve_rule_file(rules_dir, rule_path)
    if file_path is None:
        return ApiResponse.fail(code=-1, message="Invalid rule path")
    paths = _validate_rule_paths(body.paths)
    if paths is None:
        return ApiResponse.fail(code=-1, message="Invalid paths")

    def _write():
        os.makedirs(file_path.parent, exist_ok=True)
        file_path.write_text(_compose_rule_markdown(body.content, paths), encoding="utf-8")
        return _rule_to_dict(file_path, rules_dir)

    rule = await asyncio.to_thread(_write)
    logger.info("Rule file written: %s", file_path)
    return ApiResponse.success(data={"rule": rule})


@router.delete("/rules/{rule_path:path}")
async def delete_rule(rule_path: str, project_dir: str = Query(...)):
    rules_dir = _get_rules_dir(project_dir)
    if rules_dir is None:
        return ApiResponse.fail(code=-1, message="Project directory not found")
    file_path = _resolve_rule_file(rules_dir, rule_path)
    if file_path is None:
        return ApiResponse.fail(code=-1, message="Invalid rule path")
    if not file_path.exists() or not file_path.is_file():
        return ApiResponse.fail(code=-1, message="Rule not found")

    await asyncio.to_thread(file_path.unlink)
    logger.info("Rule file deleted: %s", file_path)
    return ApiResponse.success(data={"path": rule_path})


@router.get("")
async def list_memory_files(project_dir: str = Query(...)):
    """List all memory files with preview."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None or not mem_dir.exists():
        return ApiResponse.success(data={"files": [], "index": ""})

    def _scan():
        files = []
        for f in sorted(mem_dir.iterdir()):
            if f.is_file() and f.suffix == ".md" and f.name != "MEMORY.md":
                try:
                    text = f.read_text(encoding="utf-8")
                    preview = text[:200] + ("..." if len(text) > 200 else "")
                    files.append({"name": f.name, "preview": preview, "size": len(text)})
                except Exception:
                    files.append({"name": f.name, "preview": "(read error)", "size": 0})
        index_path = mem_dir / "MEMORY.md"
        index_content = ""
        if index_path.exists():
            try:
                index_content = index_path.read_text(encoding="utf-8")
            except Exception:
                pass
        return files, index_content

    files, index_content = await asyncio.to_thread(_scan)
    return ApiResponse.success(data={"files": files, "index": index_content})


@router.get("/index")
async def read_index(project_dir: str = Query(...)):
    """Read MEMORY.md index file."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None:
        return ApiResponse.success(data={"content": ""})

    index_path = mem_dir / "MEMORY.md"
    if not index_path.exists():
        return ApiResponse.success(data={"content": ""})

    content = await asyncio.to_thread(index_path.read_text, "utf-8")
    return ApiResponse.success(data={"content": content})


@router.get("/{filename}")
async def read_memory_file(filename: str, project_dir: str = Query(...)):
    """Read a specific memory file."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    file_path = mem_dir / filename
    if not file_path.resolve().is_relative_to(mem_dir.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid filename")

    if not file_path.exists() or not file_path.is_file():
        return ApiResponse.fail(code=-1, message="File not found")

    content = await asyncio.to_thread(file_path.read_text, "utf-8")
    return ApiResponse.success(data={"name": filename, "content": content})


@router.put("/{filename}")
async def write_memory_file(filename: str, body: MemoryFileWrite):
    """Create or update a memory file."""
    mem_dir = _get_memory_dir(body.project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    file_path = mem_dir / filename
    if not file_path.resolve().is_relative_to(mem_dir.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid filename")

    def _write():
        os.makedirs(mem_dir, exist_ok=True)
        file_path.write_text(body.content, encoding="utf-8")

    await asyncio.to_thread(_write)
    logger.info("Memory file written: %s", file_path)
    return ApiResponse.success(data={"name": filename})


@router.put("/index/update")
async def write_index(body: MemoryFileWrite):
    """Update MEMORY.md index file."""
    mem_dir = _get_memory_dir(body.project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    def _write():
        os.makedirs(mem_dir, exist_ok=True)
        index_path = mem_dir / "MEMORY.md"
        index_path.write_text(body.content, encoding="utf-8")

    await asyncio.to_thread(_write)
    return ApiResponse.success(data={"name": "MEMORY.md"})


@router.delete("/{filename}")
async def delete_memory_file(filename: str, project_dir: str = Query(...)):
    """Delete a memory file."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    file_path = mem_dir / filename
    if not file_path.resolve().is_relative_to(mem_dir.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid filename")

    if not file_path.exists():
        return ApiResponse.fail(code=-1, message="File not found")

    await asyncio.to_thread(file_path.unlink)
    logger.info("Memory file deleted: %s", file_path)
    return ApiResponse.success(data={"name": filename})
