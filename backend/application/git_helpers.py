from __future__ import annotations

import asyncio
import subprocess


async def get_current_git_branch(project_dir: str) -> str:
    if not project_dir:
        return ""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "-C", project_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""
