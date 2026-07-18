from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from application.session.execution_trace_query_service import ExecutionTraceQueryService
from domain.session.repository.trace_span_repository import TraceSpanRepository
from ohs.dependencies import get_execution_trace_query_service, get_trace_span_repository
from ohs.http.api_response import ApiResponse
from ohs.http.assembler.execution_trace_assembler import ExecutionTraceAssembler
from ohs.http.dto.execution_trace_dto import ExecutionTreeResponse, LoopDetailPageResponse

router = APIRouter(prefix="/api/sessions", tags=["Trace"])

TraceRepoDep = Annotated[TraceSpanRepository, Depends(get_trace_span_repository)]
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
    for span in spans:
        d = span.to_dict()
        runs.setdefault(span.run_id, []).append(d)

    run_summaries = []
    for run_id, span_dicts in runs.items():
        total_duration = max((s.get("duration_ms", 0) for s in span_dicts), default=0)
        tool_count = sum(1 for s in span_dicts if s.get("span_type") == "tool_call")
        run_summaries.append({
            "run_id": run_id,
            "span_count": len(span_dicts),
            "tool_count": tool_count,
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
    agent = await service.get_execution_tree(session_id, run_id, agent_span_id)
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
