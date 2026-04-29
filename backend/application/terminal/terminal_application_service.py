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
        return await self._terminal_gateway.execute(
            command=command.command,
            timeout=command.timeout,
            cwd=command.cwd,
        )

    async def create_pty(self, cwd: str | None = None, cols: int = 120, rows: int = 30) -> dict[str, Any]:
        return await self._terminal_gateway.create_pty(cwd=cwd, cols=cols, rows=rows)

    async def read_pty(self, terminal_id: str) -> str:
        return await self._terminal_gateway.read_pty(terminal_id)

    async def write_pty(self, terminal_id: str, data: str) -> None:
        await self._terminal_gateway.write_pty(terminal_id, data)

    async def resize_pty(self, terminal_id: str, cols: int, rows: int) -> None:
        await self._terminal_gateway.resize_pty(terminal_id, cols, rows)

    async def close_pty(self, terminal_id: str) -> None:
        await self._terminal_gateway.close_pty(terminal_id)

    async def open_path(self, path: str) -> dict[str, Any]:
        return await self._terminal_gateway.open_path(path)
