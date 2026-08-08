from __future__ import annotations

import asyncio
import os

import pytest

from infr.client.terminal_executor import TerminalExecutor


async def _read_until(
    executor: TerminalExecutor,
    terminal_id: str,
    expected: str,
) -> str:
    output = ""
    for _ in range(30):
        try:
            output += await asyncio.wait_for(executor.read_pty(terminal_id), timeout=0.2)
        except asyncio.TimeoutError:
            continue
        if expected in output:
            return output
    return output


def test_return_interactive_shell_argv_when_shell_is_configured() -> None:
    # Arrange
    executor = TerminalExecutor()

    # Act
    shell_args = executor._shell_args("/bin/zsh")

    # Assert
    assert shell_args == ["/bin/zsh", "-i"]


@pytest.mark.asyncio
async def test_create_interactive_shell_when_pty_is_created(tmp_path, monkeypatch) -> None:
    # Arrange
    executor = TerminalExecutor()
    shell = os.environ.get("SHELL", "/bin/sh")
    monkeypatch.setenv("SHELL", shell)

    # Act
    terminal = await executor.create_pty(cwd=str(tmp_path), cols=90, rows=28)

    try:
        # Assert
        assert terminal["cwd"] == str(tmp_path)
        assert terminal["shell"] == shell
    finally:
        await executor.close_pty(terminal["terminal_id"])


@pytest.mark.asyncio
async def test_return_command_output_when_input_is_written_to_pty(tmp_path, monkeypatch) -> None:
    # Arrange
    executor = TerminalExecutor()
    monkeypatch.setenv("SHELL", "/bin/sh")
    terminal = await executor.create_pty(cwd=str(tmp_path), cols=90, rows=28)

    try:
        # Act
        await executor.write_pty(
            terminal["terminal_id"],
            "printf 'VELPOS_%s\\n' 'PTY_OUTPUT_7842'\r",
        )
        output = await _read_until(executor, terminal["terminal_id"], "VELPOS_PTY_OUTPUT_7842")

        # Assert
        assert "VELPOS_PTY_OUTPUT_7842" in output
    finally:
        await executor.close_pty(terminal["terminal_id"])
