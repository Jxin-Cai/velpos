from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class TerminalExecutor:
    """Execute shell commands asynchronously and return structured results."""

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Execute a shell command and return stdout, stderr, return_code, and duration_ms.

        Args:
            command: The shell command to execute.
            timeout: Maximum execution time in seconds. Defaults to 30.
            cwd: Working directory for the command. Defaults to None (inherit).

        Returns:
            A dict with keys: stdout, stderr, return_code, duration_ms.
            On timeout, return_code is -1 and stderr contains a timeout message.
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or None,
        )

        start = time.monotonic()
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            end = time.monotonic()
            return {
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "return_code": process.returncode,
                "duration_ms": int((end - start) * 1000),
            }
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning(
                "Command timed out after %ds: %s", timeout, command[:200],
            )
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "return_code": -1,
                "duration_ms": timeout * 1000,
            }

    async def open_path(self, path: str) -> dict[str, Any]:
        """Open a file or directory using the system default handler.

        In headless/container environments where no GUI is available,
        simply verify the path exists and return success.
        """
        import os
        import sys

        if sys.platform == "darwin":
            cmd = ["open", path]
        elif sys.platform == "win32":
            cmd = ["explorer", path]
        else:
            # Headless Linux (e.g. Docker): no xdg-open, just verify path
            if os.path.exists(path):
                return {"stdout": "", "stderr": "", "return_code": 0}
            return {"stdout": "", "stderr": f"Path not found: {path}", "return_code": 1}

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "return_code": process.returncode,
        }
