from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from domain.session.model.execution_ledger_event import ExecutionLedgerEvent
from domain.session.model.llm_request import (
    LlmRequestRecord,
    LlmToolDefinition,
    PromptChangeKind,
)

logger = logging.getLogger(__name__)

API_REQUEST_BODY_EVENT_NAME = "api_request_body"

# Claude Code has moved the raw body between the log body and a few attribute
# names across releases. Probe the known carriers rather than pinning one.
_BODY_ATTRIBUTE_KEYS = (
    "request_body",
    "api_request_body",
    "body",
    "raw_request_body",
    "request",
)


class LlmRequestDecomposer:
    """Splits raw provider request bodies into system, messages, and tools.

    Pure projection over telemetry log records: it never reads the store and
    never mutates its inputs, so it can be exercised directly in tests.
    """

    def decompose(
        self,
        events: Iterable[ExecutionLedgerEvent],
    ) -> tuple[LlmRequestRecord, ...]:
        ordered = sorted(events, key=lambda event: (event.event_time, event.position or 0))
        records: list[LlmRequestRecord] = []
        previous: LlmRequestRecord | None = None
        for event in ordered:
            body = self._request_body(event)
            if body is None:
                continue
            record = self._record(event, body, previous, sequence=len(records) + 1)
            records.append(record)
            previous = record
        return tuple(records)

    def decompose_one(self, event: ExecutionLedgerEvent) -> LlmRequestRecord | None:
        body = self._request_body(event)
        if body is None:
            return None
        return self._record(event, body, previous=None, sequence=0)

    def _record(
        self,
        event: ExecutionLedgerEvent,
        body: Mapping[str, Any],
        previous: LlmRequestRecord | None,
        sequence: int,
    ) -> LlmRequestRecord:
        system = self._system_text(body.get("system"))
        tools = self._tool_definitions(body.get("tools"))
        messages = self._messages(body.get("messages"))
        return LlmRequestRecord(
            event_id=event.event_id,
            event_time=event.event_time,
            span_id=event.span_id or None,
            model=self._text(body.get("model")) or self._model_from_attributes(event),
            system=system,
            tools=tools,
            messages=messages,
            change=self._change(previous, system, tools),
            sequence=sequence,
            temperature=self._number(body.get("temperature")),
            max_tokens=self._integer(body.get("max_tokens")),
            stream=body.get("stream") if isinstance(body.get("stream"), bool) else None,
        )

    @staticmethod
    def _change(
        previous: LlmRequestRecord | None,
        system: str,
        tools: tuple[LlmToolDefinition, ...],
    ) -> PromptChangeKind:
        if previous is None:
            return PromptChangeKind.INITIAL
        system_changed = previous.system != system
        tools_changed = previous.tools != tools
        if system_changed and tools_changed:
            return PromptChangeKind.SYSTEM_AND_TOOLS
        if system_changed:
            return PromptChangeKind.SYSTEM
        if tools_changed:
            return PromptChangeKind.TOOLS
        return PromptChangeKind.UNCHANGED

    @classmethod
    def _request_body(cls, event: ExecutionLedgerEvent) -> Mapping[str, Any] | None:
        payload = event.payload if isinstance(event.payload, Mapping) else {}
        attributes = payload.get("attributes")
        candidates: list[Any] = []
        if isinstance(attributes, Mapping):
            candidates.extend(attributes.get(key) for key in _BODY_ATTRIBUTE_KEYS)
        candidates.append(payload.get("body"))
        for candidate in candidates:
            body = cls._as_body(candidate)
            if body is not None:
                return body
        return None

    @staticmethod
    def _as_body(candidate: Any) -> Mapping[str, Any] | None:
        if isinstance(candidate, Mapping):
            return candidate if "messages" in candidate or "system" in candidate else None
        if not isinstance(candidate, str) or not candidate.strip().startswith("{"):
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            logger.debug("api_request_body attribute is not valid JSON; skipping")
            return None
        if not isinstance(parsed, Mapping):
            return None
        return parsed if "messages" in parsed or "system" in parsed else None

    @classmethod
    def _system_text(cls, value: Any) -> str:
        """Flatten the Anthropic system field, which is text or text blocks."""
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping):
            return cls._text(value.get("text")) or ""
        if isinstance(value, (list, tuple)):
            parts = [cls._system_text(item) for item in value]
            return "\n\n".join(part for part in parts if part)
        return ""

    @classmethod
    def _tool_definitions(cls, value: Any) -> tuple[LlmToolDefinition, ...]:
        if not isinstance(value, (list, tuple)):
            return ()
        definitions: list[LlmToolDefinition] = []
        for item in value:
            if not isinstance(item, Mapping):
                continue
            name = cls._text(item.get("name"))
            if not name:
                continue
            schema = item.get("input_schema") or item.get("inputSchema")
            definitions.append(
                LlmToolDefinition(
                    name=name,
                    description=cls._text(item.get("description")) or None,
                    input_schema=dict(schema) if isinstance(schema, Mapping) else None,
                )
            )
        return tuple(definitions)

    @staticmethod
    def _messages(value: Any) -> tuple[Any, ...]:
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return ()

    @staticmethod
    def _model_from_attributes(event: ExecutionLedgerEvent) -> str | None:
        payload = event.payload if isinstance(event.payload, Mapping) else {}
        attributes = payload.get("attributes")
        if not isinstance(attributes, Mapping):
            return None
        for key in ("model", "gen_ai.request.model"):
            value = attributes.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _text(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return None
