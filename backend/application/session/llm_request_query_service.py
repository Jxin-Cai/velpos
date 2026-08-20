from __future__ import annotations

from dataclasses import dataclass

from domain.session.model.execution_ledger_event import ExecutionLedgerEventType
from domain.session.model.llm_request import LlmRequestRecord
from domain.session.repository.execution_ledger_event_repository import (
    ExecutionLedgerEventRepository,
)
from domain.session.service.llm_request_decomposer import (
    API_REQUEST_BODY_EVENT_NAME,
    LlmRequestDecomposer,
)

# One raw request body runs to hundreds of kilobytes. Bound the scan so opening
# a long run cannot pull an unbounded amount of telemetry text into memory.
MAX_REQUEST_SCAN = 200


@dataclass(frozen=True)
class LlmRequestPage:
    records: tuple[LlmRequestRecord, ...]
    has_more: bool


class LlmRequestQueryService:
    """Reads raw provider request bodies and returns them decomposed."""

    def __init__(
        self,
        event_repository: ExecutionLedgerEventRepository,
        decomposer: LlmRequestDecomposer | None = None,
    ) -> None:
        self._event_repository = event_repository
        self._decomposer = decomposer or LlmRequestDecomposer()

    async def list_requests(
        self,
        session_id: str,
        run_id: str,
        limit: int = MAX_REQUEST_SCAN,
    ) -> LlmRequestPage:
        events = await self._event_repository.find_by_event_names(
            session_id,
            run_id,
            ExecutionLedgerEventType.OTEL_LOG,
            (API_REQUEST_BODY_EVENT_NAME,),
            limit=limit + 1,
        )
        has_more = len(events) > limit
        return LlmRequestPage(
            records=self._decomposer.decompose(events[:limit]),
            has_more=has_more,
        )

    async def get_request(
        self,
        session_id: str,
        event_id: str,
    ) -> LlmRequestRecord | None:
        event = await self._event_repository.find_by_event_id(session_id, event_id)
        if event is None or event.event_name != API_REQUEST_BODY_EVENT_NAME:
            return None
        return self._decomposer.decompose_one(event)
