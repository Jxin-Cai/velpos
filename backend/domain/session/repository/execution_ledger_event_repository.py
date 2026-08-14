from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.execution_ledger_event import ExecutionLedgerEvent


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
