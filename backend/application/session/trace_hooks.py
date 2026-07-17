from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk.types import HookMatcher

from application.session.trace_collector import TraceCollector
from application.session.trace_redaction import sanitize_and_truncate
from domain.session.model.trace_span import TraceSpan

logger = logging.getLogger(__name__)


def create_observability_hooks(
    session_id: str,
    run_id_ref: list[str],
    collector: TraceCollector,
) -> dict[str, list[HookMatcher]]:
    if not collector.enabled:
        return {}

    async def on_pre_tool_use(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            tool_name = hook_input.get("tool_name", "unknown")
            tool_input = hook_input.get("tool_input", {})
            agent_id = hook_input.get("agent_id")
            actual_tool_use_id = tool_use_id or hook_input.get("tool_use_id")

            parent_span_id = _resolve_parent_for_tool(
                collector, session_id, run_id_ref[0], agent_id,
            )

            collector.ensure_tool_span(
                session_id=session_id,
                run_id=run_id_ref[0],
                tool_use_id=actual_tool_use_id,
                name=tool_name,
                parent_span_id=parent_span_id,
                agent_id=agent_id,
                input_preview=sanitize_and_truncate(tool_input),
                metadata={"agent_type": hook_input.get("agent_type", "")},
            )
        except Exception:
            logger.debug("trace hook on_pre_tool_use error", exc_info=True)
        return {"continue_": True}

    async def on_post_tool_use(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            tool_response = hook_input.get("tool_response")
            actual_tool_use_id = tool_use_id or hook_input.get("tool_use_id", "")
            span = collector.find_running_by_tool_use_id(session_id, actual_tool_use_id)
            if span:
                collector.complete_span(
                    span.id,
                    output_preview=sanitize_and_truncate(tool_response),
                )
        except Exception:
            logger.debug("trace hook on_post_tool_use error", exc_info=True)
        return {"continue_": True}

    async def on_post_tool_use_failure(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            actual_tool_use_id = tool_use_id or hook_input.get("tool_use_id", "")
            span = collector.find_running_by_tool_use_id(session_id, actual_tool_use_id)
            if span:
                error_str = str(hook_input.get("error") or "tool execution failed")[:500]
                collector.fail_span(span.id, error=error_str)
        except Exception:
            logger.debug("trace hook on_post_tool_use_failure error", exc_info=True)
        return {"continue_": True}

    async def on_subagent_start(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            agent_id = hook_input.get("agent_id", "")
            agent_type = hook_input.get("agent_type", "subagent")
            invocation = next((
                hook_input.get(key) for key in (
                    "prompt", "description", "task", "subagent_prompt", "input",
                ) if hook_input.get(key) is not None
            ), None)
            if invocation is None and tool_use_id:
                parent_tool = collector.find_span_by_tool_use_id(
                    session_id, run_id_ref[0], tool_use_id,
                )
                invocation = parent_tool.input_preview if parent_tool else None

            parent_span_id = _resolve_parent_for_subagent(
                collector, session_id, run_id_ref[0], tool_use_id,
            )

            collector.create_span(
                session_id=session_id,
                run_id=run_id_ref[0],
                span_type=TraceSpan.SPAN_TYPE_SUBAGENT,
                name=agent_type,
                parent_span_id=parent_span_id,
                agent_id=agent_id,
                tool_use_id=tool_use_id,
                input_preview=sanitize_and_truncate(invocation),
                metadata={
                    "agent_type": agent_type,
                    "agent_id": agent_id,
                    "tool_use_id": tool_use_id or "",
                    "model": hook_input.get("model", ""),
                    "permission_mode": hook_input.get("permission_mode", ""),
                },
            )
        except Exception:
            logger.debug("trace hook on_subagent_start error", exc_info=True)
        return {"continue_": True}

    async def on_subagent_stop(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            agent_id = hook_input.get("agent_id", "")
            span = collector.find_running_by_agent_id(session_id, agent_id)
            if span:
                child_turn = collector.find_latest_turn_for_parent(span.id)
                returned = next((
                    hook_input.get(key) for key in (
                        "result", "output", "summary", "response", "agent_output",
                    ) if hook_input.get(key) is not None
                ), None)
                returned_preview = sanitize_and_truncate(returned) if returned is not None else None
                if returned_preview is None and child_turn:
                    returned_preview = child_turn.output_preview
                collector.complete_span(
                    span.id,
                    output_preview=returned_preview,
                    metadata={
                        "agent_type": hook_input.get("agent_type", ""),
                        "agent_id": agent_id,
                        "transcript_path": hook_input.get("agent_transcript_path", ""),
                    },
                )
        except Exception:
            logger.debug("trace hook on_subagent_stop error", exc_info=True)
        return {"continue_": True}

    async def on_stop(hook_input: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            llm_turn = collector.find_latest_running_llm_turn(session_id, run_id_ref[0])
            if llm_turn:
                collector.complete_span(llm_turn.id)
        except Exception:
            logger.debug("trace hook on_stop error", exc_info=True)
        return {"continue_": True}

    hooks: dict[str, list[HookMatcher]] = {
        "PreToolUse": [HookMatcher(hooks=[on_pre_tool_use])],
        "PostToolUse": [HookMatcher(hooks=[on_post_tool_use])],
        "PostToolUseFailure": [HookMatcher(hooks=[on_post_tool_use_failure])],
        "SubagentStart": [HookMatcher(hooks=[on_subagent_start])],
        "SubagentStop": [HookMatcher(hooks=[on_subagent_stop])],
        "Stop": [HookMatcher(hooks=[on_stop])],
    }
    return hooks


def _resolve_parent_for_tool(
    collector: TraceCollector,
    session_id: str,
    run_id: str,
    agent_id: str | None,
) -> str | None:
    if agent_id:
        subagent_span = collector.find_running_by_agent_id(session_id, agent_id)
        if subagent_span:
            return subagent_span.id

    llm_turn = collector.find_latest_running_llm_turn(session_id, run_id)
    if llm_turn:
        return llm_turn.id
    run_span = collector.find_run_span(session_id, run_id)
    return run_span.id if run_span else None


def _resolve_parent_for_subagent(
    collector: TraceCollector,
    session_id: str,
    run_id: str,
    tool_use_id: str | None,
) -> str | None:
    tool_span = collector.find_running_tool_by_id(session_id, tool_use_id)
    if tool_span:
        return tool_span.id

    tool_span = collector.find_latest_running_tool(session_id, run_id)
    if tool_span:
        return tool_span.id

    llm_turn = collector.find_latest_running_llm_turn(session_id, run_id)
    if llm_turn:
        return llm_turn.id
    run_span = collector.find_run_span(session_id, run_id)
    return run_span.id if run_span else None


def merge_hooks(
    base: dict[str, list[HookMatcher]] | None,
    extra: dict[str, list[HookMatcher]] | None,
) -> dict[str, list[HookMatcher]] | None:
    if not extra:
        return base
    if not base:
        return extra
    merged: dict[str, list[HookMatcher]] = {}
    all_keys = set(list(base.keys()) + list(extra.keys()))
    for key in all_keys:
        merged[key] = list(base.get(key, [])) + list(extra.get(key, []))
    return merged
