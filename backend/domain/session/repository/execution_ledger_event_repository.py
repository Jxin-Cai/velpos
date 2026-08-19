from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from domain.session.model.execution_ledger_event import (
    ExecutionLedgerEvent,
    ExecutionLedgerEventType,
    RunEventCounts,
)


class ExecutionLedgerEventRepository(ABC):

    @abstractmethod
    async def save_batch(self, events: list[ExecutionLedgerEvent]) -> None: ...

    @abstractmethod
    async def find_by_run_after(
        self,
        session_id: str,
        run_id: str,
        after_position: int = 0,
        limit: int = 500,
    ) -> list[ExecutionLedgerEvent]: ...

    @abstractmethod
    async def count_by_run(self, session_id: str, run_id: str) -> RunEventCounts:
        """Tally a run's events without reading their payloads."""

    @abstractmethod
    async def find_by_event_names(
        self,
        session_id: str,
        run_id: str,
        event_type: ExecutionLedgerEventType,
        event_names: Sequence[str],
        limit: int = 500,
    ) -> list[ExecutionLedgerEvent]: ...

    @abstractmethod
    async def find_recent_by_type(
        self,
        session_id: str,
        run_id: str,
        event_type: ExecutionLedgerEventType,
        limit: int = 100,
    ) -> list[ExecutionLedgerEvent]:
        """Return the newest events of a type, oldest first."""

    @abstractmethod
    async def find_by_event_id(
        self,
        session_id: str,
        event_id: str,
    ) -> ExecutionLedgerEvent | None: ...
