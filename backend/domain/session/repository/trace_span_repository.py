from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.trace_span import TraceSpan


class TraceSpanRepository(ABC):

    @abstractmethod
    async def save(self, span: TraceSpan) -> None: ...

    @abstractmethod
    async def save_batch(self, spans: list[TraceSpan]) -> None: ...

    @abstractmethod
    async def update(self, span: TraceSpan) -> None: ...

    @abstractmethod
    async def update_batch(self, spans: list[TraceSpan]) -> None: ...

    @abstractmethod
    async def find_by_id(self, span_id: str) -> TraceSpan | None: ...

    @abstractmethod
    async def find_by_run(self, session_id: str, run_id: str) -> list[TraceSpan]: ...

    @abstractmethod
    async def find_by_session(self, session_id: str, limit: int = 1000) -> list[TraceSpan]: ...

    @abstractmethod
    async def find_running(self) -> list[TraceSpan]: ...

    @abstractmethod
    async def find_running_by_tool_use_id(self, session_id: str, tool_use_id: str) -> TraceSpan | None: ...

    @abstractmethod
    async def find_running_by_agent_id(self, session_id: str, agent_id: str) -> TraceSpan | None: ...

    @abstractmethod
    async def delete_by_session(self, session_id: str) -> int: ...

    @abstractmethod
    async def commit(self) -> None: ...
