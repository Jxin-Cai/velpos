from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from domain.im_binding.acl.im_message_handler import ImMessageHandler
from application.session.command.run_query_command import RunQueryCommand
from application.session.session_application_service import SessionApplicationService

logger = logging.getLogger(__name__)


class ImMessageHandlerImpl(ImMessageHandler):

    def __init__(
        self,
        session_service_factory: Callable[..., Awaitable[SessionApplicationService]],
    ) -> None:
        self._session_service_factory = session_service_factory

    async def handle_prompt(self, session_id: str, prompt: str) -> None:
        from infr.config.database import async_session_factory

        try:
            async with async_session_factory() as db_session:
                service = await self._session_service_factory(db_session)

                try:
                    session = await service.get_session(session_id)
                except Exception:
                    logger.warning(
                        "IM handle_prompt: session %s not found, skipping", session_id
                    )
                    return

                if session.is_running:
                    logger.warning(
                        "IM handle_prompt: session %s is running, skipping", session_id
                    )
                    return

                command = RunQueryCommand(session_id=session_id, prompt=prompt)
                await service.run_claude_query(command)
                await db_session.commit()

        except Exception:
            logger.error(
                "IM handle_prompt failed for session %s",
                session_id,
                exc_info=True,
            )
