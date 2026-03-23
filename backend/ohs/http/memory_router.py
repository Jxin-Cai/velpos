from __future__ import annotations

import os
import logging
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ohs.http.api_response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory"])


def _get_memory_dir(project_dir: str) -> Path | None:
    """Resolve the Claude Code project memory directory for a given project_dir."""
    from claude_agent_sdk._internal.sessions import _canonicalize_path, _find_project_dir

    canonical = _canonicalize_path(project_dir)
    proj_dir = _find_project_dir(canonical)
    if proj_dir is None:
        return None
    return proj_dir / "memory"


class MemoryFileWrite(BaseModel):
    project_dir: str
    content: str


@router.get("/claude-md")
async def read_claude_md(project_dir: str = Query(...)):
    """Read the project root CLAUDE.md file."""
    proj_path = Path(project_dir)
    if not proj_path.is_dir():
        return ApiResponse.success(data={"content": ""})

    claude_md_path = proj_path / "CLAUDE.md"
    if not claude_md_path.exists() or not claude_md_path.is_file():
        return ApiResponse.success(data={"content": ""})

    # Safety: ensure within project_dir
    if not claude_md_path.resolve().is_relative_to(proj_path.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid path")

    content = claude_md_path.read_text(encoding="utf-8")
    return ApiResponse.success(data={"content": content})


@router.put("/claude-md")
async def write_claude_md(body: MemoryFileWrite):
    """Write the project root CLAUDE.md file."""
    proj_path = Path(body.project_dir)
    if not proj_path.is_dir():
        return ApiResponse.fail(code=-1, message="Project directory not found")

    claude_md_path = proj_path / "CLAUDE.md"

    # Safety: ensure within project_dir
    if not claude_md_path.resolve().is_relative_to(proj_path.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid path")

    claude_md_path.write_text(body.content, encoding="utf-8")
    logger.info("CLAUDE.md written: %s", claude_md_path)
    return ApiResponse.success(data={"name": "CLAUDE.md"})


@router.get("")
async def list_memory_files(project_dir: str = Query(...)):
    """List all memory files with preview."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None or not mem_dir.exists():
        return ApiResponse.success(data={"files": [], "index": ""})

    files = []
    for f in sorted(mem_dir.iterdir()):
        if f.is_file() and f.suffix == ".md" and f.name != "MEMORY.md":
            try:
                content = f.read_text(encoding="utf-8")
                preview = content[:200] + ("..." if len(content) > 200 else "")
                files.append({"name": f.name, "preview": preview, "size": len(content)})
            except Exception:
                files.append({"name": f.name, "preview": "(read error)", "size": 0})

    # Read MEMORY.md index
    index_path = mem_dir / "MEMORY.md"
    index_content = ""
    if index_path.exists():
        try:
            index_content = index_path.read_text(encoding="utf-8")
        except Exception:
            pass

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

    content = index_path.read_text(encoding="utf-8")
    return ApiResponse.success(data={"content": content})


@router.get("/{filename}")
async def read_memory_file(filename: str, project_dir: str = Query(...)):
    """Read a specific memory file."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    file_path = mem_dir / filename
    if not file_path.exists() or not file_path.is_file():
        return ApiResponse.fail(code=-1, message="File not found")

    # Safety: ensure the file is within mem_dir
    if not file_path.resolve().is_relative_to(mem_dir.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid filename")

    content = file_path.read_text(encoding="utf-8")
    return ApiResponse.success(data={"name": filename, "content": content})


@router.put("/{filename}")
async def write_memory_file(filename: str, body: MemoryFileWrite):
    """Create or update a memory file."""
    mem_dir = _get_memory_dir(body.project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    os.makedirs(mem_dir, exist_ok=True)

    file_path = mem_dir / filename
    if not file_path.resolve().is_relative_to(mem_dir.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid filename")

    file_path.write_text(body.content, encoding="utf-8")
    logger.info("Memory file written: %s", file_path)
    return ApiResponse.success(data={"name": filename})


@router.put("/index/update")
async def write_index(body: MemoryFileWrite):
    """Update MEMORY.md index file."""
    mem_dir = _get_memory_dir(body.project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    os.makedirs(mem_dir, exist_ok=True)

    index_path = mem_dir / "MEMORY.md"
    index_path.write_text(body.content, encoding="utf-8")
    return ApiResponse.success(data={"name": "MEMORY.md"})


@router.delete("/{filename}")
async def delete_memory_file(filename: str, project_dir: str = Query(...)):
    """Delete a memory file."""
    mem_dir = _get_memory_dir(project_dir)
    if mem_dir is None:
        return ApiResponse.fail(code=-1, message="Memory directory not found")

    file_path = mem_dir / filename
    if not file_path.exists():
        return ApiResponse.fail(code=-1, message="File not found")

    if not file_path.resolve().is_relative_to(mem_dir.resolve()):
        return ApiResponse.fail(code=-1, message="Invalid filename")

    file_path.unlink()
    logger.info("Memory file deleted: %s", file_path)
    return ApiResponse.success(data={"name": filename})
