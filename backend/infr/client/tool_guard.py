from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from claude_agent_sdk.types import HookContext, HookInput, HookJSONOutput, HookMatcher

IsDir = Callable[[str], bool]


@dataclass(frozen=True)
class ToolGuardDecision:
    reason: str
    deny: bool = True


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _resolve_path(file_path: str, cwd: str) -> str:
    if os.path.isabs(file_path):
        return file_path
    if cwd:
        return os.path.join(cwd, file_path)
    return file_path


def inspect_pre_tool_use(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    cwd: str = "",
    *,
    isdir: IsDir | None = None,
) -> ToolGuardDecision | None:
    """Return a deny decision for known-invalid tool calls, else None."""
    check_dir = isdir or os.path.isdir
    payload = tool_input or {}
    if tool_name == "Read":
        file_path = _as_text(payload.get("file_path")).strip()
        if not file_path:
            return ToolGuardDecision(
                "Read requires a file path. Use Glob or a directory listing to discover files first."
            )
        resolved = _resolve_path(file_path, cwd)
        if check_dir(resolved):
            return ToolGuardDecision(
                f"Read cannot open a directory: {file_path}. "
                "Use Glob with a pattern under that path, or list the directory, then Read a specific file."
            )
        return None

    if tool_name == "Edit":
        old_string = payload.get("old_string")
        new_string = payload.get("new_string")
        if isinstance(old_string, str) and old_string == new_string:
            return ToolGuardDecision(
                "Edit old_string and new_string are identical, so no change would be made. "
                "Re-Read the current file and supply a different new_string, or skip this edit."
            )
        return None

    return None


def recovery_hint_for_tool_failure(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    error: str,
) -> str | None:
    """Return recovery guidance for known tool-execution failures."""
    message = error or ""
    lowered = message.casefold()
    payload = tool_input or {}

    if tool_name == "Read" and ("eisdir" in lowered or "illegal operation on a directory" in lowered):
        file_path = _as_text(payload.get("file_path")) or "<path>"
        return (
            f"Read failed because {file_path} is a directory. "
            "Use Glob or list the directory, then Read a specific file."
        )

    if tool_name == "Edit":
        if "old_string and new_string are exactly the same" in lowered:
            return (
                "Edit made no change because old_string and new_string were identical. "
                "Re-Read the file and provide a real replacement, or skip the edit."
            )
        if "string to replace not found" in lowered:
            return (
                "Edit failed because old_string no longer matches the file. "
                "Re-Read the current file contents, copy an exact unique snippet as old_string, "
                "and avoid reusing a stale snapshot from an earlier Read."
            )

    if tool_name.startswith("mcp__gitnexus__") and (
        "multiple repositories indexed" in lowered
        or 'specify which one with the "repo" parameter' in lowered
        or "specify which one with the 'repo' parameter" in lowered
    ):
        return (
            "GitNexus requires a repo parameter when multiple repositories are indexed. "
            "Retry the same call with repo set to one of the repositories listed in the error."
        )

    return None


def _deny_output(reason: str) -> HookJSONOutput:
    return {
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def _context_output(
    event_name: Literal["PostToolUseFailure"],
    context: str,
) -> HookJSONOutput:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        },
    }


async def _pre_tool_use_guard(
    hook_input: HookInput,
    _tool_use_id: str | None,
    _context: HookContext,
) -> HookJSONOutput:
    if hook_input.get("hook_event_name") != "PreToolUse":
        return {}
    decision = inspect_pre_tool_use(
        _as_text(hook_input.get("tool_name")),
        hook_input.get("tool_input"),
        _as_text(hook_input.get("cwd")),
    )
    if decision is None:
        return {}
    return _deny_output(decision.reason)


async def _post_tool_use_failure_guard(
    hook_input: HookInput,
    _tool_use_id: str | None,
    _context: HookContext,
) -> HookJSONOutput:
    if hook_input.get("hook_event_name") != "PostToolUseFailure":
        return {}
    hint = recovery_hint_for_tool_failure(
        _as_text(hook_input.get("tool_name")),
        hook_input.get("tool_input"),
        _as_text(hook_input.get("error")),
    )
    if hint is None:
        return {}
    return _context_output("PostToolUseFailure", hint)


def session_execution_hooks() -> dict[str, list[HookMatcher]]:
    """Framework hooks that intercept known-invalid tool calls during a session."""
    return {
        "PreToolUse": [
            HookMatcher(
                matcher="Read|Edit",
                hooks=[_pre_tool_use_guard],
            )
        ],
        "PostToolUseFailure": [
            HookMatcher(
                matcher=None,
                hooks=[_post_tool_use_failure_guard],
            )
        ],
    }


def merge_session_hooks(
    existing: dict[str, list[HookMatcher]] | None,
) -> dict[str, list[HookMatcher]]:
    merged: dict[str, list[HookMatcher]] = {
        event: list(matchers) for event, matchers in session_execution_hooks().items()
    }
    if not existing:
        return merged
    for event, matchers in existing.items():
        merged[event] = [*merged.get(event, []), *matchers]
    return merged
