from __future__ import annotations

import logging
import os
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from domain.session.acl.command_gateway import CommandGateway as CommandGatewayPort

logger = logging.getLogger(__name__)


class ClaudeCommandGateway(CommandGatewayPort):

    def __init__(self, cli_path: str | None = None, permission_mode: str | None = None) -> None:
        self._cli_path = cli_path or os.getenv("CLAUDE_CLI_PATH")
        if not self._cli_path:
            raise RuntimeError("CLAUDE_CLI_PATH environment variable is not set")
        self._permission_mode = permission_mode or os.getenv("CLAUDE_PERMISSION_MODE", "acceptEdits")

    async def get_commands(self, cwd: str) -> list[dict[str, Any]]:
        logger.info("Fetching commands from Claude CLI for cwd=%s", cwd)
        options = ClaudeAgentOptions(
            permission_mode=self._permission_mode,
            cli_path=self._cli_path,
            setting_sources=["user"],
            cwd=cwd if cwd else None,
        )

        commands: list[dict[str, Any]] = []
        try:
            async with ClaudeSDKClient(options=options) as agent:
                server_info = await agent.get_server_info()
                if server_info and "commands" in server_info:
                    raw_commands = server_info["commands"]
                    for cmd in raw_commands:
                        if cmd.get("isHidden"):
                            continue
                        commands.append({
                            "name": cmd.get("name", ""),
                            "description": cmd.get("description", ""),
                            "type": cmd.get("type", "unknown"),
                            "isUserInvocable": cmd.get("userInvocable", cmd.get("isUserInvocable", True)),
                        })
                    logger.info("Fetched %d commands from CLI", len(commands))
                else:
                    logger.warning("No commands found in server info: %s", server_info)
        except Exception:
            logger.exception("Failed to fetch commands from Claude CLI")

        return commands
