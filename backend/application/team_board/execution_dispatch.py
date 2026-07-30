from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from application.session.command.run_query_command import RunQueryCommand

if TYPE_CHECKING:
    from application.session.session_application_service import SessionApplicationService


async def dispatch_execution_query(
    session_service_factory: Callable[..., Awaitable["SessionApplicationService"]],
    session_id: str,
    prompt: str,
) -> None:
    """Submit a query to a session using a fresh service factory instance.

    Callers that require an isolated DB-session scope for fire-and-forget
    dispatch tasks get one automatically each time this function is called.
    The factory is responsible for all session lifecycle management (commit /
    close).  The ``finally`` block guarantees ``close`` is called even when
    ``submit_query`` raises.
    """
    service = await session_service_factory()
    try:
        await service.submit_query(RunQueryCommand(session_id=session_id, prompt=prompt))
        await service.commit()
    finally:
        await service.close()
