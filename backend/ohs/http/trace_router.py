from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from application.session.execution_trace_query_service import ExecutionTraceQueryService
from domain.session.model.execution_ledger_event import (
    ExecutionLedgerEvent,
    ExecutionLedgerEventType,
)
from domain.session.model.trace_span import TraceSpan
from domain.session.repository.execution_ledger_event_repository import ExecutionLedgerEventRepository
from domain.session.repository.trace_span_repository import TraceSpanRepository
from ohs.dependencies import (
    get_execution_ledger_event_repository,
    get_execution_trace_query_service,
    get_trace_span_repository,
)
from ohs.http.api_response import ApiResponse
from ohs.http.assembler.audit_payload_assembler import trim_audit_payload
from ohs.http.assembler.execution_trace_assembler import ExecutionTraceAssembler
from ohs.http.dto.execution_trace_dto import ExecutionTreeResponse, LoopDetailPageResponse

router = APIRouter(prefix="/api/sessions", tags=["Trace"])

_RECENT_LOG_EVENT_LIMIT = 100
# Cost carrying events hold only a small attribute map, so the whole run's worth
# can be summed without the payload weight that raw body events carry.
_COST_EVENT_SCAN_LIMIT = 5001
_COST_LOG_EVENT_NAME = "api_request"
_COST_METRIC_NAME = "claude_code.cost.usage"
_RAW_BODY_EVENT_NAMES = ("api_request_body", "api_response_body")
_API_FAILURE_EVENT_NAMES = (
    "api_error",
    "api_refusal",
    "api_retries_exhausted",
    "internal_error",
)

TraceRepoDep = Annotated[TraceSpanRepository, Depends(get_trace_span_repository)]
ExecutionEventRepoDep = Annotated[
    ExecutionLedgerEventRepository,
    Depends(get_execution_ledger_event_repository),
]
ExecutionTraceQueryDep = Annotated[ExecutionTraceQueryService, Depends(get_execution_trace_query_service)]


def _build_tree(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for s in spans:
        s["children"] = []
        by_id[s["id"]] = s

    roots: list[dict[str, Any]] = []
    for node in by_id.values():
        parent_id = node.get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


@router.get("/{session_id}/traces", summary="List trace runs for a session")
async def list_traces(
    session_id: str,
    repo: TraceRepoDep,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> ApiResponse[dict]:
    spans = await repo.find_by_session(session_id, limit=limit)
    runs: dict[str, list[dict[str, Any]]] = {}
    run_spans_by_id: dict[str, list[TraceSpan]] = {}
    for span in spans:
        d = span.to_dict()
        runs.setdefault(span.run_id, []).append(d)
        run_spans_by_id.setdefault(span.run_id, []).append(span)

    run_summaries = []
    for run_id, span_dicts in runs.items():
        run_spans = run_spans_by_id[run_id]
        total_duration = max((s.get("duration_ms", 0) for s in span_dicts), default=0)
        tool_count = sum(1 for s in span_dicts if s.get("span_type") == "tool_call")
        subagent_count = len({
            span.subagent_invocation_key
            for span in run_spans
            if span.subagent_invocation_key
        })
        run_summaries.append({
            "run_id": run_id,
            "span_count": len(span_dicts),
            "tool_count": tool_count,
            "subagent_count": subagent_count,
            "total_duration_ms": total_duration,
            "started_time": span_dicts[0].get("started_time") if span_dicts else None,
        })

    return ApiResponse.success({
        "session_id": session_id,
        "runs": run_summaries,
        "spans": [span.to_dict() for span in spans],
    })


@router.get("/{session_id}/runs/{run_id}/trace-tree", summary="Get trace tree for a run")
async def get_trace_tree(
    session_id: str,
    run_id: str,
    repo: TraceRepoDep,
) -> ApiResponse[dict]:
    spans = await repo.find_by_run(session_id, run_id)
    span_dicts = [s.to_dict() for s in spans]
    tree = _build_tree(span_dicts)
    return ApiResponse.success({
        "session_id": session_id,
        "run_id": run_id,
        "tree": tree,
        "span_count": len(span_dicts),
    })


@router.get(
    "/{session_id}/runs/{run_id}/execution-events",
    summary="Replay structured execution events for a run",
)
async def list_execution_events(
    session_id: str,
    run_id: str,
    repo: ExecutionEventRepoDep,
    after_sequence: int = Query(default=0, ge=0, description="Return events after this cursor"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> ApiResponse[dict]:
    events = await repo.find_by_run_after(
        session_id,
        run_id,
        after_position=after_sequence,
        limit=limit + 1,
    )
    has_more = len(events) > limit
    page = events[:limit]
    next_sequence = page[-1].position if page else after_sequence
    return ApiResponse.success({
        "session_id": session_id,
        "run_id": run_id,
        "events": [event.to_dict() for event in page],
        "next_sequence": next_sequence,
        "has_more": has_more,
    })


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _run_cost_usd(
    event_repo: ExecutionLedgerEventRepository,
    session_id: str,
    run_id: str,
) -> float:
    """Sum the run cost from API request events, falling back to cost metrics."""
    api_requests = await event_repo.find_by_event_names(
        session_id,
        run_id,
        ExecutionLedgerEventType.OTEL_LOG,
        (_COST_LOG_EVENT_NAME,),
        limit=_COST_EVENT_SCAN_LIMIT,
    )
    cost_usd = sum(
        _number(event.payload.get("attributes", {}).get("cost_usd"))
        for event in api_requests
    )
    if cost_usd:
        return cost_usd

    cost_metrics = await event_repo.find_by_event_names(
        session_id,
        run_id,
        ExecutionLedgerEventType.OTEL_METRIC,
        (_COST_METRIC_NAME,),
        limit=_COST_EVENT_SCAN_LIMIT,
    )
    return sum(_number(event.payload.get("value")) for event in cost_metrics)


def _to_clipped_event_dict(event: ExecutionLedgerEvent) -> dict[str, Any]:
    trimmed = trim_audit_payload(event.payload)
    return {
        **event.to_dict(),
        "payload": trimmed.payload,
        "payload_truncated": trimmed.truncated,
    }


@router.get(
    "/{session_id}/runs/{run_id}/telemetry-summary",
    summary="Summarize native Claude Code OpenTelemetry signals",
)
async def get_telemetry_summary(
    session_id: str,
    run_id: str,
    span_repo: TraceRepoDep,
    event_repo: ExecutionEventRepoDep,
) -> ApiResponse[dict]:
    spans = await span_repo.find_by_run(session_id, run_id)
    native_spans = [
        span
        for span in spans
        if span.metadata.get("telemetry.source") == "claude_code_otel"
    ]
    llm_spans = [
        span
        for span in native_spans
        if span.metadata.get("otel.span_name") == "claude_code.llm_request"
    ]
    tool_spans = [
        span
        for span in native_spans
        if span.metadata.get("otel.span_name") == "claude_code.tool"
    ]
    interaction_spans = [
        span
        for span in native_spans
        if span.metadata.get("otel.span_name") == "claude_code.interaction"
    ]
    counts = await event_repo.count_by_run(session_id, run_id)
    cost_usd = await _run_cost_usd(event_repo, session_id, run_id)
    latencies = [span.duration_ms for span in llm_spans if span.duration_ms > 0]
    ttft_values = [
        int(_number(span.metadata.get("ttft_ms")))
        for span in llm_spans
        if _number(span.metadata.get("ttft_ms")) > 0
    ]
    retry_count = sum(
        max(int(_number(span.metadata.get("attempt")) or 1) - 1, 0)
        for span in llm_spans
    )
    permission_wait_spans = [
        span
        for span in native_spans
        if span.metadata.get("otel.span_name") == "claude_code.tool.blocked_on_user"
    ]
    hook_spans = [
        span
        for span in native_spans
        if span.metadata.get("otel.span_name") == "claude_code.hook"
    ]
    trace_ids = {
        str(span.metadata.get("otel.trace_id"))
        for span in native_spans
        if span.metadata.get("otel.trace_id")
    }
    recent = await event_repo.find_recent_by_type(
        session_id,
        run_id,
        ExecutionLedgerEventType.OTEL_LOG,
        limit=_RECENT_LOG_EVENT_LIMIT,
    )
    recent_events = [_to_clipped_event_dict(event) for event in recent]

    return ApiResponse.success({
        "source": "claude_code_otel" if native_spans else "legacy_trace",
        "trace_count": len(trace_ids),
        "interaction_count": len(interaction_spans),
        "llm_request_count": len(llm_spans),
        "tool_count": len(tool_spans),
        "log_event_count": counts.log_event_count,
        "metric_sample_count": counts.metric_sample_count,
        "api_error_count": counts.log_count_of(*_API_FAILURE_EVENT_NAMES),
        "api_refusal_count": counts.log_count_of("api_refusal"),
        "retry_count": retry_count,
        "permission_wait_count": len(permission_wait_spans),
        "permission_wait_ms": sum(span.duration_ms for span in permission_wait_spans),
        "hook_count": len(hook_spans),
        "raw_api_body_count": counts.log_count_of(*_RAW_BODY_EVENT_NAMES),
        "event_counts": dict(counts.log_counts_by_name),
        "cost_usd": round(cost_usd, 6),
        "input_tokens": sum(int(span.metadata.get("input_tokens") or 0) for span in llm_spans),
        "output_tokens": sum(int(span.metadata.get("output_tokens") or 0) for span in llm_spans),
        "cache_read_tokens": sum(int(span.metadata.get("cache_read_tokens") or 0) for span in llm_spans),
        "cache_creation_tokens": sum(int(span.metadata.get("cache_creation_tokens") or 0) for span in llm_spans),
        "llm_latency_p50_ms": _percentile(latencies, 0.50),
        "llm_latency_p95_ms": _percentile(latencies, 0.95),
        "ttft_p50_ms": _percentile(ttft_values, 0.50),
        "ttft_p95_ms": _percentile(ttft_values, 0.95),
        "recent_events": recent_events,
    })


@router.get(
    "/{session_id}/execution-events/{event_id}",
    summary="Get the verbatim audit payload of one execution event",
)
async def get_execution_event(
    session_id: str,
    event_id: str,
    repo: ExecutionEventRepoDep,
) -> ApiResponse[dict]:
    event = await repo.find_by_event_id(session_id, event_id)
    if event is None:
        return ApiResponse.fail(code=404, message="Execution event not found")
    return ApiResponse.success(event.to_dict())


@router.get("/{session_id}/traces/{span_id}", summary="Get span detail")
async def get_span_detail(
    session_id: str,
    span_id: str,
    repo: TraceRepoDep,
) -> ApiResponse[dict]:
    span = await repo.find_by_id(span_id)
    if span is None or span.session_id != session_id:
        return ApiResponse.fail(code=404, message="Span not found")
    return ApiResponse.success(span.to_dict())


@router.get("/{session_id}/runs/{run_id}/execution-tree", summary="Get execution tree for a run")
async def get_execution_tree(
    session_id: str,
    run_id: str,
    service: ExecutionTraceQueryDep,
    agent_span_id: str | None = Query(default=None, description="Optional agent span to scope the tree"),
) -> ApiResponse[ExecutionTreeResponse]:
    agent = await service.get_cached_execution_tree(session_id, run_id, agent_span_id)
    dto = ExecutionTraceAssembler.to_tree_response(agent)
    return ApiResponse.success(dto)


@router.get("/{session_id}/runs/{run_id}/execution-loops/{loop_id}", summary="Get loop detail page")
async def get_execution_loop_detail(
    session_id: str,
    run_id: str,
    loop_id: str,
    service: ExecutionTraceQueryDep,
    agent_span_id: str | None = Query(default=None, description="Optional agent span to scope the tree"),
    cursor: int = Query(default=0, ge=0, description="Pagination cursor"),
    limit: int = Query(default=100, ge=1, le=500, description="Page size"),
) -> ApiResponse[LoopDetailPageResponse]:
    page = await service.get_loop_detail(session_id, run_id, loop_id, agent_span_id, cursor, limit)
    dto = ExecutionTraceAssembler.to_loop_detail_response(page)
    return ApiResponse.success(dto)
