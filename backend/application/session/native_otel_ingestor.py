from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from domain.session.model.execution_ledger_event import ExecutionLedgerEvent
from domain.session.model.trace_span import TraceSpan, parse_claude_agent_result
from domain.session.repository.execution_ledger_event_repository import (
    ExecutionLedgerEventRepository,
)
from domain.session.repository.trace_span_repository import TraceSpanRepository

logger = logging.getLogger(__name__)

_SPAN_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{16}$")
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_SAFE_AGENT_ID = re.compile(r"^[A-Za-z0-9_-]+$")

_SPAN_TYPE_BY_NAME = {
    # Preserve the established projection vocabulary while retaining the
    # canonical OTel span name and span.type in metadata.
    "claude_code.interaction": TraceSpan.SPAN_TYPE_AGENT,
    "claude_code.llm_request": TraceSpan.SPAN_TYPE_LLM_TURN,
    "claude_code.tool": TraceSpan.SPAN_TYPE_TOOL_CALL,
    "claude_code.tool.execution": TraceSpan.SPAN_TYPE_TOOL_EXECUTION,
    "claude_code.tool.blocked_on_user": TraceSpan.SPAN_TYPE_PERMISSION_WAIT,
    "claude_code.hook": TraceSpan.SPAN_TYPE_HOOK,
}


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in (
        "stringValue",
        "boolValue",
        "intValue",
        "doubleValue",
        "bytesValue",
    ):
        if key in value:
            raw = value[key]
            if key == "intValue":
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return raw
            return raw
    if "arrayValue" in value:
        return [_decode_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return _decode_attributes(value["kvlistValue"].get("values", []))
    return value


def _decode_attributes(items: Any) -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("key")): _decode_value(item.get("value"))
        for item in items
        if isinstance(item, dict) and item.get("key") is not None
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _from_unix_nano(raw: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(raw) / 1_000_000_000)
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now()


def _stable_event_id(*parts: Any) -> str:
    content = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def _status_for_span(raw_span: dict[str, Any], attributes: dict[str, Any]) -> str:
    status = raw_span.get("status") or {}
    code = status.get("code")
    if code in (2, "2", "STATUS_CODE_ERROR") or attributes.get("success") is False:
        return TraceSpan.STATUS_FAILED
    return TraceSpan.STATUS_COMPLETED


def _duration_ms(
    raw_span: dict[str, Any],
    attributes: dict[str, Any],
    started: datetime,
    ended: datetime,
) -> int:
    declared = attributes.get("duration_ms") or attributes.get("interaction.duration_ms")
    try:
        if declared is not None:
            return max(int(float(declared)), 0)
    except (TypeError, ValueError):
        pass
    return max(int((ended - started).total_seconds() * 1000), 0)


def _payload_from_attributes(attributes: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = attributes.get(key)
        if value in (None, "", "<REDACTED>"):
            continue
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)
    return None


async def _resolve_run(
    repository: TraceSpanRepository,
    session_id: str,
    occurred_at: datetime,
) -> tuple[str, str | None]:
    spans = await repository.find_by_session(session_id, limit=5000)
    run_spans = [span for span in spans if span.span_type == TraceSpan.SPAN_TYPE_RUN]
    eligible = [span for span in run_spans if span.started_time <= occurred_at]
    if eligible:
        envelope = max(eligible, key=lambda item: item.started_time)
        return envelope.run_id, envelope.id
    if run_spans:
        envelope = max(run_spans, key=lambda item: item.started_time)
        return envelope.run_id, envelope.id
    return "otel-unscoped", None


def _resource_attributes(resource: dict[str, Any]) -> dict[str, Any]:
    return _decode_attributes(resource.get("attributes", []))


def _session_id(resource: dict[str, Any]) -> str:
    return str(_resource_attributes(resource).get("velpos.session.id") or "")


def _span_from_payload(
    raw_span: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    run_span_id: str | None,
    resource: dict[str, Any],
    scope: dict[str, Any],
    exported_span_ids: set[str],
) -> TraceSpan | None:
    span_id = str(raw_span.get("spanId") or "")
    trace_id = str(raw_span.get("traceId") or "")
    if not _SPAN_ID_PATTERN.fullmatch(span_id) or not _TRACE_ID_PATTERN.fullmatch(trace_id):
        return None
    name = str(raw_span.get("name") or "unknown")
    attributes = _decode_attributes(raw_span.get("attributes", []))
    resource_attrs = _resource_attributes(resource)
    started = _from_unix_nano(raw_span.get("startTimeUnixNano"))
    ended = _from_unix_nano(raw_span.get("endTimeUnixNano"))
    native_parent_id = str(raw_span.get("parentSpanId") or "") or None
    parent_id = native_parent_id
    if name == "claude_code.interaction" and parent_id not in exported_span_ids:
        # TRACEPARENT can point to an application span that is not stored in
        # Velpos. Preserve it as metadata and attach the interaction to our run
        # envelope so the local tree never contains an orphan root.
        parent_id = run_span_id
    span_events = []
    for event in _dict_items(raw_span.get("events")):
        span_events.append(
            {
                "name": event.get("name"),
                "time": _from_unix_nano(event.get("timeUnixNano")).isoformat(),
                "attributes": _decode_attributes(event.get("attributes", [])),
            }
        )

    metadata = {
        **attributes,
        "telemetry.source": "claude_code_otel",
        "otel.span_name": name,
        "otel.trace_id": trace_id,
        "otel.scope": scope.get("name", ""),
        "otel.scope_version": scope.get("version", ""),
        "otel.scope_attributes": _decode_attributes(scope.get("attributes", [])),
        "otel.resource": resource_attrs,
        "otel.events": span_events,
        "otel.trace_state": raw_span.get("traceState", ""),
        "otel.flags": raw_span.get("flags"),
        "otel.dropped_attributes_count": raw_span.get("droppedAttributesCount", 0),
        "otel.dropped_events_count": raw_span.get("droppedEventsCount", 0),
        "otel.dropped_links_count": raw_span.get("droppedLinksCount", 0),
    }
    if native_parent_id and native_parent_id != parent_id:
        metadata["otel.remote_parent_span_id"] = native_parent_id
    status = _status_for_span(raw_span, attributes)
    if status == TraceSpan.STATUS_FAILED:
        error = attributes.get("error") or (raw_span.get("status") or {}).get("message")
        if error:
            metadata["error"] = error

    if name == "claude_code.tool" and str(attributes.get("tool_name") or "").casefold() == "agent":
        result = parse_claude_agent_result(attributes.get("new_context"))
        result_agent_id = result.get("agentId") or result.get("agent_id")
        claude_session_id = attributes.get("session.id") or resource_attrs.get("session.id")
        if isinstance(result_agent_id, str) and _SAFE_AGENT_ID.fullmatch(result_agent_id):
            metadata["agent_id"] = result_agent_id
            if isinstance(claude_session_id, str) and _SAFE_AGENT_ID.fullmatch(claude_session_id):
                metadata["agent_transcript_path"] = (
                    f"{claude_session_id}/subagents/agent-{result_agent_id}.jsonl"
                )

    input_payload = _payload_from_attributes(
        attributes,
        (
            "user_prompt",
            "prompt",
            "request.model_input",
            "tool_input",
            "tool.input",
            "tool_parameters",
            "full_command",
            "file_path",
            "input",
        ),
    )
    output_preview = _payload_from_attributes(
        attributes,
        ("response.model_output", "tool_output", "tool.output", "tool.result", "output"),
    )
    for event in span_events:
        event_attrs = event.get("attributes") or {}
        input_payload = input_payload or _payload_from_attributes(
            event_attrs,
            ("user_prompt", "prompt", "request.model_input", "tool_input", "tool.input", "input"),
        )
        output_preview = output_preview or _payload_from_attributes(
            event_attrs,
            ("tool_output", "tool.output", "output", "content"),
        )

    display_name = name.removeprefix("claude_code.")
    if name == "claude_code.tool":
        display_name = str(attributes.get("tool_name") or display_name)
    elif name == "claude_code.hook":
        display_name = str(attributes.get("hook_name") or display_name)

    return TraceSpan(
        id=span_id,
        session_id=session_id,
        run_id=run_id,
        parent_span_id=parent_id,
        span_type=_SPAN_TYPE_BY_NAME.get(name, "otel_span"),
        name=display_name,
        status=status,
        agent_id=str(attributes.get("agent_id") or attributes.get("agent.name") or "") or None,
        tool_use_id=str(attributes.get("tool_use_id") or attributes.get("gen_ai.tool.call.id") or "") or None,
        input_preview=input_payload,
        output_preview=output_preview,
        metadata=metadata,
        started_time=started,
        ended_time=ended,
        duration_ms=_duration_ms(raw_span, attributes, started, ended),
        created_time=datetime.now(),
        sequence=int(raw_span.get("endTimeUnixNano") or 0) // 1_000_000,
        revision=1,
    )


async def ingest_traces(
    payload: dict[str, Any],
    span_repository: TraceSpanRepository,
) -> list[TraceSpan]:
    ingested: list[TraceSpan] = []
    run_cache: dict[tuple[str, str], tuple[str, str | None]] = {}
    for resource_spans in _dict_items(payload.get("resourceSpans")):
        resource = resource_spans.get("resource") or {}
        session_id = _session_id(resource)
        if not session_id:
            continue
        exported_span_ids = {
            str(span.get("spanId"))
            for scope_spans in _dict_items(resource_spans.get("scopeSpans"))
            for span in _dict_items(scope_spans.get("spans"))
            if span.get("spanId")
        }
        for scope_spans in _dict_items(resource_spans.get("scopeSpans")):
            scope = scope_spans.get("scope") or {}
            for raw_span in _dict_items(scope_spans.get("spans")):
                occurred_at = _from_unix_nano(raw_span.get("startTimeUnixNano"))
                trace_id = str(raw_span.get("traceId") or "")
                cache_key = (session_id, trace_id or occurred_at.isoformat())
                if cache_key not in run_cache:
                    run_cache[cache_key] = await _resolve_run(
                        span_repository,
                        session_id,
                        occurred_at,
                    )
                run_id, run_span_id = run_cache[cache_key]
                span = _span_from_payload(
                    raw_span,
                    session_id=session_id,
                    run_id=run_id,
                    run_span_id=run_span_id,
                    resource=resource,
                    scope=scope,
                    exported_span_ids=exported_span_ids,
                )
                if span is not None:
                    ingested.append(span)
    if ingested:
        await span_repository.save_batch(ingested)
        await span_repository.commit()
    return ingested


async def _event_context(
    repository: TraceSpanRepository,
    session_id: str,
    occurred_at: datetime,
) -> tuple[str, str | None]:
    return await _resolve_run(repository, session_id, occurred_at)


async def ingest_logs(
    payload: dict[str, Any],
    span_repository: TraceSpanRepository,
    event_repository: ExecutionLedgerEventRepository,
) -> list[ExecutionLedgerEvent]:
    events: list[ExecutionLedgerEvent] = []
    run_cache: dict[tuple[str, str], tuple[str, str | None]] = {}
    for resource_logs in _dict_items(payload.get("resourceLogs")):
        resource = resource_logs.get("resource") or {}
        resource_attrs = _resource_attributes(resource)
        session_id = str(resource_attrs.get("velpos.session.id") or "")
        if not session_id:
            continue
        for scope_logs in _dict_items(resource_logs.get("scopeLogs")):
            scope = scope_logs.get("scope") or {}
            for record in _dict_items(scope_logs.get("logRecords")):
                occurred_at = _from_unix_nano(
                    record.get("timeUnixNano") or record.get("observedTimeUnixNano")
                )
                trace_id = str(record.get("traceId") or "")
                cache_key = (session_id, trace_id or occurred_at.isoformat())
                if cache_key not in run_cache:
                    run_cache[cache_key] = await _event_context(
                        span_repository, session_id, occurred_at
                    )
                run_id, _ = run_cache[cache_key]
                attributes = _decode_attributes(record.get("attributes", []))
                body = _decode_value(record.get("body"))
                event_name = str(attributes.get("event.name") or body or "log")
                span_id = str(record.get("spanId") or "")
                event_id = _stable_event_id(
                    session_id,
                    run_id,
                    "log",
                    occurred_at.isoformat(),
                    record.get("traceId"),
                    span_id,
                    event_name,
                    attributes,
                )
                events.append(
                    ExecutionLedgerEvent.from_otel_record(
                        event_id=event_id,
                        session_id=session_id,
                        run_id=run_id,
                        signal="log",
                        event_name=event_name,
                        event_time=occurred_at,
                        span_id=span_id,
                        agent_id=str(attributes.get("agent_id") or "") or None,
                        tool_use_id=str(attributes.get("tool_use_id") or "") or None,
                        payload={
                            "signal": "log",
                            "event_name": event_name,
                            "body": body,
                            "severity": record.get("severityText"),
                            "severity_number": record.get("severityNumber"),
                            "trace_id": trace_id,
                            "span_id": span_id,
                            "flags": record.get("flags"),
                            "observed_time": _from_unix_nano(
                                record.get("observedTimeUnixNano")
                            ).isoformat(),
                            "scope": {
                                "name": scope.get("name", ""),
                                "version": scope.get("version", ""),
                                "attributes": _decode_attributes(
                                    scope.get("attributes", [])
                                ),
                            },
                            "attributes": attributes,
                            "resource": resource_attrs,
                        },
                    )
                )
    if events:
        await event_repository.save_batch(events)
        await span_repository.commit()
    return events


def _metric_points(metric: dict[str, Any]) -> list[dict[str, Any]]:
    for kind in ("sum", "gauge", "histogram", "exponentialHistogram"):
        data = metric.get(kind)
        if isinstance(data, dict):
            return [dict(point, metric_kind=kind) for point in data.get("dataPoints", [])]
    return []


def _metric_value(point: dict[str, Any]) -> int | float | None:
    if "asInt" in point:
        try:
            return int(point["asInt"])
        except (TypeError, ValueError):
            return None
    if "asDouble" in point:
        try:
            return float(point["asDouble"])
        except (TypeError, ValueError):
            return None
    return None


async def ingest_metrics(
    payload: dict[str, Any],
    span_repository: TraceSpanRepository,
    event_repository: ExecutionLedgerEventRepository,
) -> list[ExecutionLedgerEvent]:
    events: list[ExecutionLedgerEvent] = []
    run_cache: dict[tuple[str, str], tuple[str, str | None]] = {}
    for resource_metrics in _dict_items(payload.get("resourceMetrics")):
        resource = resource_metrics.get("resource") or {}
        resource_attrs = _resource_attributes(resource)
        session_id = str(resource_attrs.get("velpos.session.id") or "")
        if not session_id:
            continue
        for scope_metrics in _dict_items(resource_metrics.get("scopeMetrics")):
            scope = scope_metrics.get("scope") or {}
            for metric in _dict_items(scope_metrics.get("metrics")):
                metric_name = str(metric.get("name") or "metric")
                for point in _metric_points(metric):
                    occurred_at = _from_unix_nano(point.get("timeUnixNano"))
                    attributes = _decode_attributes(point.get("attributes", []))
                    # Claude Code's official `session.id` metric attribute is
                    # the SDK/CLI UUID, not Velpos's 8-character session key.
                    # Keep it in the audit payload but always route and persist
                    # with our resource-level correlation attribute.
                    cache_key = (session_id, occurred_at.isoformat())
                    if cache_key not in run_cache:
                        run_cache[cache_key] = await _event_context(
                            span_repository, session_id, occurred_at
                        )
                    run_id, _ = run_cache[cache_key]
                    value = _metric_value(point)
                    event_id = _stable_event_id(
                        session_id,
                        run_id,
                        "metric",
                        metric_name,
                        occurred_at.isoformat(),
                        attributes,
                        value,
                    )
                    events.append(
                        ExecutionLedgerEvent.from_otel_record(
                            event_id=event_id,
                            session_id=session_id,
                            run_id=run_id,
                            signal="metric",
                            event_name=metric_name,
                            event_time=occurred_at,
                            agent_id=str(attributes.get("agent_id") or "") or None,
                            payload={
                                "signal": "metric",
                                "metric_name": metric_name,
                                "description": metric.get("description", ""),
                                "unit": metric.get("unit", ""),
                                "metric_kind": point.get("metric_kind"),
                                "value": value,
                                "count": point.get("count"),
                                "sum": point.get("sum"),
                                "min": point.get("min"),
                                "max": point.get("max"),
                                "bucket_counts": point.get("bucketCounts", []),
                                "explicit_bounds": point.get("explicitBounds", []),
                                "exemplars": point.get("exemplars", []),
                                "aggregation_temporality": (
                                    metric.get(point.get("metric_kind"), {}) or {}
                                ).get("aggregationTemporality"),
                                "is_monotonic": (
                                    metric.get(point.get("metric_kind"), {}) or {}
                                ).get("isMonotonic"),
                                "scope": {
                                    "name": scope.get("name", ""),
                                    "version": scope.get("version", ""),
                                },
                                "attributes": attributes,
                                "resource": resource_attrs,
                            },
                        )
                    )
    if events:
        await event_repository.save_batch(events)
        await span_repository.commit()
    return events
