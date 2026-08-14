from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from application.session.native_otel_config import _derive_ingest_token, build_native_otel_env
from application.session.native_otel_ingestor import ingest_logs, ingest_metrics, ingest_traces
from domain.session.model.execution_ledger_event import ExecutionLedgerEvent
from domain.session.model.trace_span import TraceSpan


class _SpanRepositoryStub:
    def __init__(self) -> None:
        self.run = TraceSpan.create("session1", "run1", TraceSpan.SPAN_TYPE_RUN, "Agent run")
        self.run.started_time = datetime(2026, 8, 13, 10, 0, 0)
        self.saved: list[TraceSpan] = []

    async def find_by_session(self, session_id: str, limit: int = 1000) -> list[TraceSpan]:
        return [self.run] if session_id == "session1" else []

    async def save_batch(self, spans: list[TraceSpan]) -> None:
        self.saved.extend(spans)

    async def commit(self) -> None:
        return None


class _EventRepositoryStub:
    def __init__(self) -> None:
        self.saved: list[ExecutionLedgerEvent] = []

    async def save_batch(self, events: list[ExecutionLedgerEvent]) -> None:
        self.saved.extend(events)


def _resource() -> dict[str, Any]:
    return {
        "attributes": [
            {"key": "velpos.session.id", "value": {"stringValue": "session1"}},
            {"key": "service.name", "value": {"stringValue": "velpos-agent"}},
        ]
    }


def test_builds_official_exporters_when_native_otel_is_enabled(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "true")

    # Act
    env = build_native_otel_env("session1", {"PATH": "/usr/bin"})

    # Assert
    assert env["OTEL_TRACES_EXPORTER"] == "otlp"
    assert env["OTEL_METRICS_EXPORTER"] == "otlp"
    assert env["OTEL_LOGS_EXPORTER"] == "otlp"
    assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/json"
    assert "velpos.session.id=session1" in env["OTEL_RESOURCE_ATTRIBUTES"]
    assert env["ENABLE_BETA_TRACING_DETAILED"] == "1"
    assert env["BETA_TRACING_ENDPOINT"].endswith("/api/otel")
    assert env["OTEL_LOG_USER_PROMPTS"] == "1"
    assert env["OTEL_LOG_ASSISTANT_RESPONSES"] == "1"
    assert env["OTEL_LOG_TOOL_DETAILS"] == "1"
    assert env["OTEL_LOG_TOOL_CONTENT"] == "1"
    assert env["OTEL_LOG_RAW_API_BODIES"] == "1"


def test_preserves_explicit_audit_opt_out_when_settings_disable_content(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "true")

    # Act
    env = build_native_otel_env(
        "session1",
        {"OTEL_LOG_RAW_API_BODIES": "0", "OTEL_LOG_TOOL_CONTENT": "0"},
    )

    # Assert
    assert env["OTEL_LOG_RAW_API_BODIES"] == "0"
    assert env["OTEL_LOG_TOOL_CONTENT"] == "0"


def test_derives_stable_ingest_token_from_service_secret(monkeypatch) -> None:
    # Arrange
    monkeypatch.delenv("VELPOS_OTEL_INGEST_TOKEN", raising=False)
    monkeypatch.setenv("JWT_SECRET", "stable-service-secret-for-tests")

    # Act
    first = _derive_ingest_token()
    second = _derive_ingest_token()

    # Assert
    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_preserves_official_parent_child_hierarchy_when_trace_payload_arrives() -> None:
    # Arrange
    repository = _SpanRepositoryStub()
    payload = {
        "resourceSpans": [{
            "resource": _resource(),
            "scopeSpans": [{
                "scope": {"name": "com.anthropic.claude_code"},
                "spans": [
                    {
                        "traceId": "a" * 32,
                        "spanId": "1" * 16,
                        "name": "claude_code.interaction",
                        "startTimeUnixNano": "1786586401000000000",
                        "endTimeUnixNano": "1786586403000000000",
                        "attributes": [],
                    },
                    {
                        "traceId": "a" * 32,
                        "spanId": "2" * 16,
                        "parentSpanId": "1" * 16,
                        "name": "claude_code.llm_request",
                        "startTimeUnixNano": "1786586401100000000",
                        "endTimeUnixNano": "1786586402900000000",
                        "attributes": [
                            {"key": "model", "value": {"stringValue": "claude-sonnet-5"}},
                            {"key": "input_tokens", "value": {"intValue": "120"}},
                        ],
                    },
                ],
            }],
        }],
    }

    # Act
    spans = await ingest_traces(payload, repository)  # type: ignore[arg-type]

    # Assert
    interaction, llm_request = spans
    assert interaction.parent_span_id == repository.run.id
    assert llm_request.parent_span_id == interaction.id
    assert llm_request.metadata["input_tokens"] == 120


@pytest.mark.asyncio
async def test_attaches_remote_parent_interaction_to_velpos_run_envelope() -> None:
    # Arrange
    repository = _SpanRepositoryStub()
    payload = {
        "resourceSpans": [{
            "resource": _resource(),
            "scopeSpans": [{
                "spans": [{
                    "traceId": "b" * 32,
                    "spanId": "3" * 16,
                    "parentSpanId": "9" * 16,
                    "name": "claude_code.interaction",
                    "startTimeUnixNano": "1786586401000000000",
                    "endTimeUnixNano": "1786586402000000000",
                    "attributes": [],
                }],
            }],
        }],
    }

    # Act
    spans = await ingest_traces(payload, repository)  # type: ignore[arg-type]

    # Assert
    assert spans[0].parent_span_id == repository.run.id
    assert spans[0].metadata["otel.remote_parent_span_id"] == "9" * 16


@pytest.mark.asyncio
async def test_preserves_full_tool_content_from_official_span_event() -> None:
    # Arrange
    repository = _SpanRepositoryStub()
    payload = {
        "resourceSpans": [{
            "resource": _resource(),
            "scopeSpans": [{
                "spans": [{
                    "traceId": "c" * 32,
                    "spanId": "4" * 16,
                    "name": "claude_code.tool",
                    "startTimeUnixNano": "1786586401000000000",
                    "endTimeUnixNano": "1786586402000000000",
                    "attributes": [
                        {"key": "tool_name", "value": {"stringValue": "Bash"}},
                    ],
                    "events": [{
                        "name": "tool.output",
                        "timeUnixNano": "1786586401900000000",
                        "attributes": [
                            {"key": "tool.input", "value": {"stringValue": "echo audit"}},
                            {"key": "tool.output", "value": {"stringValue": "audit"}},
                        ],
                    }],
                }],
            }],
        }],
    }

    # Act
    spans = await ingest_traces(payload, repository)  # type: ignore[arg-type]

    # Assert
    assert spans[0].input_preview == "echo audit"
    assert spans[0].output_preview == "audit"
    assert spans[0].metadata["otel.events"][0]["attributes"]["tool.input"] == "echo audit"


@pytest.mark.asyncio
async def test_classifies_official_agent_tool_span_as_subagent_invocation() -> None:
    # Arrange
    repository = _SpanRepositoryStub()
    payload = {
        "resourceSpans": [{
            "resource": _resource(),
            "scopeSpans": [{
                "spans": [{
                    "traceId": "e" * 32,
                    "spanId": "6" * 16,
                    "name": "claude_code.tool",
                    "startTimeUnixNano": "1786586401000000000",
                    "endTimeUnixNano": "1786586402000000000",
                    "attributes": [
                        {"key": "tool_name", "value": {"stringValue": "Agent"}},
                        {"key": "tool_use_id", "value": {"stringValue": "call-agent-1"}},
                        {"key": "subagent_type", "value": {"stringValue": "Explore"}},
                    ],
                }],
            }],
        }],
    }

    # Act
    spans = await ingest_traces(payload, repository)  # type: ignore[arg-type]

    # Assert
    assert spans[0].is_subagent_invocation is True
    assert spans[0].subagent_invocation_key == "call-agent-1"


@pytest.mark.asyncio
async def test_derives_subagent_transcript_when_official_agent_result_contains_agent_id() -> None:
    # Arrange
    repository = _SpanRepositoryStub()
    result = '[TOOL RESULT: Agent]\n{"status":"completed","agentId":"child-1"}'
    payload = {
        "resourceSpans": [{
            "resource": _resource(),
            "scopeSpans": [{
                "spans": [{
                    "traceId": "f" * 32,
                    "spanId": "7" * 16,
                    "name": "claude_code.tool",
                    "startTimeUnixNano": "1786586401000000000",
                    "endTimeUnixNano": "1786586402000000000",
                    "attributes": [
                        {"key": "tool_name", "value": {"stringValue": "Agent"}},
                        {"key": "session.id", "value": {"stringValue": "claude-session-1"}},
                        {"key": "new_context", "value": {"stringValue": result}},
                    ],
                }],
            }],
        }],
    }

    # Act
    spans = await ingest_traces(payload, repository)  # type: ignore[arg-type]

    # Assert
    assert spans[0].resolved_subagent_transcript_path == (
        "claude-session-1/subagents/agent-child-1.jsonl"
    )


@pytest.mark.asyncio
async def test_preserves_complete_payload_when_official_span_exceeds_legacy_preview_limit() -> None:
    # Arrange
    repository = _SpanRepositoryStub()
    complete_input = "i" * 70_000
    complete_output = "o" * 70_000
    payload = {
        "resourceSpans": [{
            "resource": _resource(),
            "scopeSpans": [{
                "spans": [{
                    "traceId": "d" * 32,
                    "spanId": "5" * 16,
                    "name": "claude_code.tool",
                    "startTimeUnixNano": "1786586401000000000",
                    "endTimeUnixNano": "1786586402000000000",
                    "attributes": [
                        {"key": "tool.input", "value": {"stringValue": complete_input}},
                        {"key": "tool.output", "value": {"stringValue": complete_output}},
                    ],
                }],
            }],
        }],
    }

    # Act
    spans = await ingest_traces(payload, repository)  # type: ignore[arg-type]

    # Assert
    assert spans[0].input_preview == complete_input
    assert spans[0].output_preview == complete_output


@pytest.mark.asyncio
async def test_records_structured_api_event_when_log_payload_arrives() -> None:
    # Arrange
    span_repository = _SpanRepositoryStub()
    event_repository = _EventRepositoryStub()
    payload = {
        "resourceLogs": [{
            "resource": _resource(),
            "scopeLogs": [{
                "logRecords": [{
                    "timeUnixNano": "1786586402000000000",
                    "traceId": "a" * 32,
                    "spanId": "2" * 16,
                    "body": {"stringValue": "claude_code.api_request"},
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "api_request"}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.012}},
                    ],
                }],
            }],
        }],
    }

    # Act
    events = await ingest_logs(
        payload,
        span_repository,  # type: ignore[arg-type]
        event_repository,  # type: ignore[arg-type]
    )

    # Assert
    assert events[0].payload["event_name"] == "api_request"
    assert events[0].payload["attributes"]["cost_usd"] == 0.012


@pytest.mark.asyncio
async def test_records_token_sample_when_metric_payload_arrives() -> None:
    # Arrange
    span_repository = _SpanRepositoryStub()
    event_repository = _EventRepositoryStub()
    payload = {
        "resourceMetrics": [{
            "resource": _resource(),
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.token.usage",
                    "unit": "tokens",
                    "sum": {
                        "dataPoints": [{
                            "timeUnixNano": "1786586402000000000",
                            "asInt": "450",
                            "attributes": [
                                {"key": "type", "value": {"stringValue": "input"}},
                            ],
                        }],
                    },
                }],
            }],
        }],
    }

    # Act
    events = await ingest_metrics(
        payload,
        span_repository,  # type: ignore[arg-type]
        event_repository,  # type: ignore[arg-type]
    )

    # Assert
    assert events[0].payload["metric_name"] == "claude_code.token.usage"
    assert events[0].payload["value"] == 450


@pytest.mark.asyncio
async def test_uses_velpos_session_when_metric_contains_claude_session_uuid() -> None:
    # Arrange
    span_repository = _SpanRepositoryStub()
    event_repository = _EventRepositoryStub()
    payload = {
        "resourceMetrics": [{
            "resource": _resource(),
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.cost.usage",
                    "sum": {
                        "dataPoints": [{
                            "timeUnixNano": "1786586402000000000",
                            "asDouble": 0.012,
                            "attributes": [{
                                "key": "session.id",
                                "value": {
                                    "stringValue": "d973ac41-7107-43d2-8dc5-ee3848b0f147"
                                },
                            }],
                        }],
                    },
                }],
            }],
        }],
    }

    # Act
    events = await ingest_metrics(
        payload,
        span_repository,  # type: ignore[arg-type]
        event_repository,  # type: ignore[arg-type]
    )

    # Assert
    assert events[0].session_id == "session1"
