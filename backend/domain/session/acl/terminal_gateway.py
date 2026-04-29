from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TerminalGateway(ABC):

    @abstractmethod
    async def execute(self, command: str, timeout: int, cwd: str | None = None) -> dict[str, Any]:
        """Execute a shell command inside the container.

        Returns a dict with keys:
            - stdout (str): standard output
            - stderr (str): standard error
            - exit_code (int): process exit code; -1 on timeout

        On timeout, exit_code is set to -1 and stderr contains a timeout message.
        """
        ...

    @abstractmethod
    async def create_pty(self, cwd: str | None = None, cols: int = 120, rows: int = 30) -> dict[str, Any]:
        """Create an interactive terminal session."""
        ...

    @abstractmethod
    async def read_pty(self, terminal_id: str) -> str:
        """Read output from an interactive terminal session."""
        ...

    @abstractmethod
    async def write_pty(self, terminal_id: str, data: str) -> None:
        """Write input to an interactive terminal session."""
        ...

    @abstractmethod
    async def resize_pty(self, terminal_id: str, cols: int, rows: int) -> None:
        """Resize an interactive terminal session."""
        ...

    @abstractmethod
    async def close_pty(self, terminal_id: str) -> None:
        """Close an interactive terminal session."""
        ...

    @abstractmethod
    async def open_path(self, path: str) -> dict[str, Any]:
        """Open a file or directory using the system default handler."""
        ...
