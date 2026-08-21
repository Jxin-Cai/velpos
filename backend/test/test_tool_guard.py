from __future__ import annotations

import pytest
from claude_agent_sdk.types import HookMatcher

import infr.client.claude_agent_gateway as claude_agent_gateway_module
from infr.client.claude_agent_gateway import ClaudeAgentGateway
from infr.client.tool_guard import (
    inspect_pre_tool_use,
    merge_session_hooks,
    recovery_hint_for_tool_failure,
    session_execution_hooks,
)


def test_denies_read_when_path_is_a_directory() -> None:
    decision = inspect_pre_tool_use(
        "Read",
        {"file_path": "/workspace/features/working-sessions"},
        isdir=lambda _path: True,
    )

    assert decision is not None
    assert decision.deny is True
    assert "directory" in decision.reason.casefold()
    assert "Glob" in decision.reason


def test_denies_read_when_file_path_is_missing() -> None:
    decision = inspect_pre_tool_use("Read", {})

    assert decision is not None
    assert "file path" in decision.reason.casefold()


def test_allows_read_when_path_is_a_file() -> None:
    decision = inspect_pre_tool_use(
        "Read",
        {"file_path": "/workspace/App.vue"},
        isdir=lambda _path: False,
    )

    assert decision is None


def test_resolves_relative_read_path_against_cwd() -> None:
    seen: list[str] = []

    def isdir(path: str) -> bool:
        seen.append(path)
        return path.endswith("working-sessions")

    decision = inspect_pre_tool_use(
        "Read",
        {"file_path": "features/working-sessions"},
        cwd="/workspace",
        isdir=isdir,
    )

    assert seen == ["/workspace/features/working-sessions"]
    assert decision is not None


def test_denies_edit_when_old_and_new_strings_are_identical() -> None:
    snippet = "const unviewedIds = new Set()"
    decision = inspect_pre_tool_use(
        "Edit",
        {"file_path": "/workspace/App.vue", "old_string": snippet, "new_string": snippet},
    )

    assert decision is not None
    assert "identical" in decision.reason.casefold()


def test_allows_edit_when_strings_differ() -> None:
    decision = inspect_pre_tool_use(
        "Edit",
        {
            "file_path": "/workspace/App.vue",
            "old_string": "const unviewedIds = new Set()",
            "new_string": "const unviewedIds = props.unviewedIds",
        },
    )

    assert decision is None


def test_hints_gitnexus_to_retry_with_repo_parameter() -> None:
    hint = recovery_hint_for_tool_failure(
        "mcp__gitnexus__query",
        {"search_query": "session sidebar"},
        'Error: Multiple repositories indexed. Specify which one with the "repo" parameter. Available: aiworkforce-platform, openstar',
    )

    assert hint is not None
    assert "repo" in hint.casefold()
    assert "retry" in hint.casefold()


def test_does_not_preempt_gitnexus_when_repo_is_unknown() -> None:
    decision = inspect_pre_tool_use(
        "mcp__gitnexus__query",
        {"search_query": "session sidebar"},
    )

    assert decision is None


def test_hints_edit_to_reread_when_old_string_is_stale() -> None:
    hint = recovery_hint_for_tool_failure(
        "Edit",
        {"file_path": "claude_agent_gateway.py", "old_string": "def _is_query_busy"},
        "String to replace not found in file.",
    )

    assert hint is not None
    assert "Re-Read" in hint
    assert "old_string" in hint


@pytest.mark.asyncio
async def test_pre_tool_use_hook_denies_directory_read(monkeypatch) -> None:
    monkeypatch.setattr("infr.client.tool_guard.os.path.isdir", lambda _path: True)
    callback = session_execution_hooks()["PreToolUse"][0].hooks[0]

    result = await callback(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/workspace/features/working-sessions"},
            "tool_use_id": "tool-1",
            "session_id": "session-1",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/workspace",
        },
        "tool-1",
        {"signal": None},
    )

    output = result.get("hookSpecificOutput") or {}
    assert output.get("permissionDecision") == "deny"
    assert "directory" in str(output.get("permissionDecisionReason", "")).casefold()


@pytest.mark.asyncio
async def test_post_tool_use_failure_hook_explains_gitnexus_repo_requirement() -> None:
    callback = session_execution_hooks()["PostToolUseFailure"][0].hooks[0]

    result = await callback(
        {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "mcp__gitnexus__query",
            "tool_input": {"search_query": "session sidebar"},
            "tool_use_id": "tool-2",
            "error": 'Multiple repositories indexed. Specify which one with the "repo" parameter.',
            "session_id": "session-1",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/workspace",
        },
        "tool-2",
        {"signal": None},
    )

    output = result.get("hookSpecificOutput") or {}
    assert "repo" in str(output.get("additionalContext", "")).casefold()


def test_keeps_framework_hooks_ahead_of_caller_hooks() -> None:
    extra = HookMatcher(matcher="Bash", hooks=[])
    merged = merge_session_hooks({"PreToolUse": [extra]})
    builtin = session_execution_hooks()

    assert merged["PreToolUse"][0].matcher == builtin["PreToolUse"][0].matcher
    assert merged["PreToolUse"][-1] is extra
    assert "PostToolUseFailure" in merged


@pytest.mark.asyncio
async def test_injects_framework_hooks_when_sdk_client_starts(monkeypatch) -> None:
    captured_options: dict = {}

    class _OptionsStub:
        def __init__(self, **kwargs) -> None:
            captured_options.update(kwargs)

    class _ClientStub:
        def __init__(self, options) -> None:
            self.options = options

        async def connect(self) -> None:
            return None

    monkeypatch.setattr(claude_agent_gateway_module, "ClaudeAgentOptions", _OptionsStub)
    monkeypatch.setattr(claude_agent_gateway_module, "ClaudeSDKClient", _ClientStub)
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")

    await gateway._try_connect(
        session_id="session-1",
        model="claude-sonnet-4-6",
        perm_mode="bypassPermissions",
        cwd="/tmp/project",
        prev_sdk_sid=None,
    )

    hooks = captured_options["hooks"]
    assert "PreToolUse" in hooks
    assert "PostToolUseFailure" in hooks
    assert hooks["PreToolUse"][0].matcher == "Read|Edit"
