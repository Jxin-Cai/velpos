from __future__ import annotations

from application.session.llm_request_query_service import LlmRequestPage
from domain.session.model.llm_request import LlmRequestRecord, LlmToolDefinition
from ohs.http.dto.llm_request_dto import (
    LlmRequestDetailDto,
    LlmRequestListResponse,
    LlmRequestSummaryDto,
    LlmToolDefinitionDto,
)


class LlmRequestAssembler:
    """Converts decomposed provider requests to response DTOs."""

    @staticmethod
    def to_list_response(page: LlmRequestPage) -> LlmRequestListResponse:
        return LlmRequestListResponse(
            requests=[LlmRequestAssembler.to_summary(record) for record in page.records],
            has_more=page.has_more,
        )

    @staticmethod
    def to_summary(record: LlmRequestRecord) -> LlmRequestSummaryDto:
        return LlmRequestSummaryDto(**LlmRequestAssembler._summary_fields(record))

    @staticmethod
    def to_detail(record: LlmRequestRecord) -> LlmRequestDetailDto:
        return LlmRequestDetailDto(
            **LlmRequestAssembler._summary_fields(record),
            system=record.system,
            tools=[LlmRequestAssembler._to_tool_dto(tool) for tool in record.tools],
            messages=list(record.messages),
            temperature=record.temperature,
            max_tokens=record.max_tokens,
            stream=record.stream,
        )

    @staticmethod
    def _summary_fields(record: LlmRequestRecord) -> dict:
        return {
            "event_id": record.event_id,
            "sequence": record.sequence,
            "event_time": record.event_time,
            "span_id": record.span_id,
            "model": record.model,
            "change": record.change.value,
            "system_char_count": record.system_char_count,
            "system_preview": record.system_preview,
            "tool_count": len(record.tools),
            "tool_names": list(record.tool_names),
            "message_count": record.message_count,
            "message_char_count": record.message_char_count,
        }

    @staticmethod
    def _to_tool_dto(tool: LlmToolDefinition) -> LlmToolDefinitionDto:
        return LlmToolDefinitionDto(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
