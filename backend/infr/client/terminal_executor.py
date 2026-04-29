from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import shutil
import signal
import struct
import sys
import termios
import time
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PtySession:
    terminal_id: str
    pid: int
    master_fd: int
    cwd: str
    shell: str


class TerminalExecutor:

    def __init__(self) -> None:
        self._pty_sessions: dict[str, PtySession] = {}

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str | None = None,
    ) -> dict[str, Any]:
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

    async def create_pty(self, cwd: str | None = None, cols: int = 120, rows: int = 30) -> dict[str, Any]:
        resolved_cwd = cwd if cwd and os.path.isdir(cwd) else os.getcwd()
        if sys.platform == "darwin" and os.path.exists("/bin/zsh"):
            shell = "/bin/zsh"
        else:
            shell = os.environ.get("SHELL") or "/bin/bash"
        if not os.path.exists(shell):
            shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"

        env = os.environ.copy()
        env["SHELL"] = shell
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env.setdefault("BASH_SILENCE_DEPRECATION_WARNING", "1")
        shell_args = self._shell_args(shell)

        pid, master_fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(resolved_cwd)
                os.execvpe(shell, shell_args, env)
            except BaseException:
                os._exit(127)

        os.set_blocking(master_fd, False)
        self._set_pty_size(master_fd, cols, rows)

        terminal_id = uuid.uuid4().hex
        self._pty_sessions[terminal_id] = PtySession(
            terminal_id=terminal_id,
            pid=pid,
            master_fd=master_fd,
            cwd=resolved_cwd,
            shell=shell,
        )
        return {"terminal_id": terminal_id, "cwd": resolved_cwd, "shell": shell}

    async def read_pty(self, terminal_id: str) -> str:
        while terminal_id in self._pty_sessions:
            session = self._get_pty_session(terminal_id)
            try:
                data = os.read(session.master_fd, 4096)
            except BlockingIOError:
                if not self._is_pty_alive(session):
                    return ""
                await asyncio.sleep(0.03)
                continue
            except OSError:
                return ""
            if data:
                return data.decode("utf-8", errors="replace")
            return ""
        return ""

    async def write_pty(self, terminal_id: str, data: str) -> None:
        session = self._get_pty_session(terminal_id)
        remaining = data.encode("utf-8", errors="replace")
        while remaining:
            try:
                written = os.write(session.master_fd, remaining)
            except BlockingIOError:
                await asyncio.sleep(0.01)
                continue
            except OSError:
                return
            remaining = remaining[written:]

    async def resize_pty(self, terminal_id: str, cols: int, rows: int) -> None:
        session = self._get_pty_session(terminal_id)
        self._set_pty_size(session.master_fd, cols, rows)

    async def close_pty(self, terminal_id: str) -> None:
        session = self._pty_sessions.pop(terminal_id, None)
        if session is None:
            return
        try:
            os.close(session.master_fd)
        except OSError:
            pass
        if not self._is_pty_alive(session):
            return
        try:
            os.killpg(session.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not self._is_pty_alive(session):
                return
            await asyncio.sleep(0.05)
        try:
            os.killpg(session.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def open_path(self, path: str) -> dict[str, Any]:
        if sys.platform == "darwin":
            cmd = ["open", path]
        elif sys.platform == "win32":
            cmd = ["explorer", path]
        else:
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

    def _shell_args(self, shell: str) -> list[str]:
        shell_name = os.path.basename(shell)
        if shell_name == "bash":
            return [shell, "--noprofile", "--norc", "-i"]
        if shell_name in {"sh", "zsh"}:
            return [shell, "-i"]
        return [shell]

    def _get_pty_session(self, terminal_id: str) -> PtySession:
        session = self._pty_sessions.get(terminal_id)
        if session is None:
            raise KeyError(f"Terminal session not found: {terminal_id}")
        return session

    def _is_pty_alive(self, session: PtySession) -> bool:
        try:
            finished_pid, _ = os.waitpid(session.pid, os.WNOHANG)
        except ChildProcessError:
            return False
        return finished_pid == 0

    def _set_pty_size(self, fd: int, cols: int, rows: int) -> None:
        safe_cols = max(20, min(int(cols or 120), 300))
        safe_rows = max(5, min(int(rows or 30), 120))
        size = struct.pack("HHHH", safe_rows, safe_cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
