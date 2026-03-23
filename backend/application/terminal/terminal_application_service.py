from __future__ import annotations

from typing import Any

from application.terminal.command.execute_terminal_command import ExecuteTerminalCommand
from domain.session.acl.terminal_gateway import TerminalGateway


class TerminalApplicationService:

    def __init__(
        self,
        terminal_gateway: TerminalGateway,
    ) -> None:
        self._terminal_gateway = terminal_gateway

    async def execute_command(self, command: ExecuteTerminalCommand) -> dict[str, Any]:
        """Execute a shell command inside the container.

        Delegates to the terminal gateway and returns the result dict
        containing stdout, stderr, and exit_code.
        """
        return await self._terminal_gateway.execute(
            command=command.command,
            timeout=command.timeout,
            cwd=command.cwd,
        )

    async def open_path(self, path: str) -> dict[str, Any]:
        """Open a file or directory using the system default handler."""
        return await self._terminal_gateway.open_path(path)
