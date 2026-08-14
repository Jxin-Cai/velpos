from __future__ import annotations

import gzip
import json
import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from application.session.native_otel_ingestor import (
    ingest_logs,
    ingest_metrics,
    ingest_traces,
)
from domain.session.repository.execution_ledger_event_repository import (
    ExecutionLedgerEventRepository,
)
from domain.session.repository.trace_span_repository import TraceSpanRepository
from ohs.dependencies import (
    get_connection_manager,
    get_execution_ledger_event_repository,
    get_trace_collector,
    get_trace_span_repository,
)
from ohs.http.otel_auth import authorize_otel_request

logger = logging.getLogger(__name__)

_MAX_OTLP_PAYLOAD_BYTES = max(
    int(os.getenv("VELPOS_OTEL_MAX_PAYLOAD_BYTES", str(32 * 1024 * 1024))),
    1024,
)

router = APIRouter(prefix="/api/otel", tags=["OpenTelemetry"])

TraceRepoDep = Annotated[TraceSpanRepository, Depends(get_trace_span_repository)]
EventRepoDep = Annotated[
    ExecutionLedgerEventRepository,
    Depends(get_execution_ledger_event_repository),
]


async def _read_json_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "json" not in content_type:
        raise HTTPException(
            status_code=415,
            detail="Velpos OTLP ingest requires the http/json protocol",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_OTLP_PAYLOAD_BYTES:
                raise HTTPException(status_code=413, detail="OTLP payload is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    body = await request.body()
    if len(body) > _MAX_OTLP_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="OTLP payload is too large")
    if request.headers.get("content-encoding", "").lower() == "gzip":
        try:
            body = gzip.decompress(body)
        except gzip.BadGzipFile as exc:
            raise HTTPException(status_code=400, detail="Invalid gzip payload") from exc
        if len(body) > _MAX_OTLP_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="OTLP payload is too large")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid OTLP JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="OTLP payload must be an object")
    return payload


async def _broadcast_telemetry_events(events: list[Any]) -> None:
    connection_manager = get_connection_manager()
    for event in events:
        try:
            await connection_manager.broadcast(
                event.session_id,
                {
                    "event": "telemetry_event",
                    "run_id": event.run_id,
                    "signal": event.payload.get("signal"),
                    "event_sequence": event.position,
                },
            )
        except Exception:
            logger.warning(
                "Failed to broadcast native OTel event: session=%s event=%s",
                event.session_id,
                event.event_id,
                exc_info=True,
            )


@router.post("/v1/traces", include_in_schema=False)
async def receive_traces(
    request: Request,
    repository: TraceRepoDep,
    x_velpos_otel_token: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    authorize_otel_request(x_velpos_otel_token, request)
    payload = await _read_json_payload(request)
    await get_trace_collector().flush()
    spans = await ingest_traces(payload, repository)
    connection_manager = get_connection_manager()
    for span in spans:
        try:
            await connection_manager.broadcast(
                span.session_id,
                {
                    "event": "trace_span",
                    "action": "ingested",
                    "span": span.to_dict(),
                    "event_sequence": span.sequence,
                },
            )
        except Exception:
            logger.warning(
                "Failed to broadcast native OTel span: session=%s span=%s",
                span.session_id,
                span.id,
                exc_info=True,
            )
    return JSONResponse(content={})


@router.post("/v1/logs", include_in_schema=False)
async def receive_logs(
    request: Request,
    span_repository: TraceRepoDep,
    event_repository: EventRepoDep,
    x_velpos_otel_token: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    authorize_otel_request(x_velpos_otel_token, request)
    payload = await _read_json_payload(request)
    await get_trace_collector().flush()
    events = await ingest_logs(payload, span_repository, event_repository)
    await _broadcast_telemetry_events(events)
    return JSONResponse(content={})


@router.post("/v1/metrics", include_in_schema=False)
async def receive_metrics(
    request: Request,
    span_repository: TraceRepoDep,
    event_repository: EventRepoDep,
    x_velpos_otel_token: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    authorize_otel_request(x_velpos_otel_token, request)
    payload = await _read_json_payload(request)
    await get_trace_collector().flush()
    events = await ingest_metrics(payload, span_repository, event_repository)
    await _broadcast_telemetry_events(events)
    return JSONResponse(content={})
