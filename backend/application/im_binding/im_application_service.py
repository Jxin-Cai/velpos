from __future__ import annotations

import asyncio
import logging
from typing import Any

from domain.shared.async_utils import safe_create_task

from application.im_binding.command.bind_im_command import BindImCommand
from application.im_binding.command.complete_binding_command import CompleteBindingCommand
from application.im_binding.command.sync_message_to_im_command import SyncMessageToImCommand
from application.im_binding.command.unbind_im_command import UnbindImCommand
from domain.im_binding.acl.im_message_handler import ImMessageHandler
from domain.im_binding.acl.im_gateway import ImGateway
from domain.im_binding.acl.im_ws_gateway import ImWsGateway
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.repository.im_binding_repository import ImBindingRepository
from domain.session.model.message import Message
from domain.session.repository.session_repository import SessionRepository
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


class ImApplicationService:

    def __init__(
        self,
        im_binding_repository: ImBindingRepository,
        im_gateway: ImGateway,
        im_ws_gateway: ImWsGateway,
        session_repository: SessionRepository,
        im_message_handler: ImMessageHandler,
    ) -> None:
        self._im_binding_repository = im_binding_repository
        self._im_gateway = im_gateway
        self._im_ws_gateway = im_ws_gateway
        self._session_repository = session_repository
        self._im_message_handler = im_message_handler

    async def bind_im(self, command: BindImCommand) -> ImBinding:
        binding = await self._im_binding_repository.find_by_session_id(command.session_id)

        if binding is not None and binding.binding_status != BindingStatus.UNBOUND:
            raise BusinessException(
                "IM binding already exists for this session", "IM_ALREADY_BOUND"
            )

        if binding is None:
            binding = ImBinding.create(command.session_id)

        await self._im_gateway.register_user(
            binding.im_user_id, f"Session {command.session_id}"
        )
        im_token = await self._im_gateway.get_user_token(binding.im_user_id)
        qr_code_data = await self._im_gateway.generate_add_friend_link(binding.im_user_id)

        binding.start_binding(im_token, qr_code_data)
        await self._im_binding_repository.save(binding)

        return binding

    async def complete_binding(self, command: CompleteBindingCommand) -> ImBinding:
        binding = await self._im_binding_repository.find_by_session_id(command.session_id)

        if binding is None:
            raise BusinessException("IM binding not found", "IM_BINDING_NOT_FOUND")

        binding.complete_binding(command.friend_user_id)
        await self._im_binding_repository.save(binding)

        await self._im_gateway.import_friend(binding.im_user_id, command.friend_user_id)

        try:
            await self._im_ws_gateway.connect(binding.im_user_id, binding.im_token)
        except Exception:
            logger.warning(
                "Failed to establish WS connection for %s, will retry later",
                binding.im_user_id,
            )

        try:
            session = await self._session_repository.find_by_id(command.session_id)
            if session is not None and session.messages:
                for msg in session.messages:
                    await self._im_gateway.send_message(
                        binding.im_user_id,
                        command.friend_user_id,
                        self._format_message_for_im(msg),
                    )
        except Exception:
            logger.warning(
                "Failed to sync history messages for session %s",
                command.session_id,
            )

        safe_create_task(self._listen_im_messages(binding))

        return binding

    async def unbind_im(self, command: UnbindImCommand) -> None:
        binding = await self._im_binding_repository.find_by_session_id(command.session_id)

        if binding is None:
            raise BusinessException("IM binding not found", "IM_BINDING_NOT_FOUND")

        try:
            await self._im_ws_gateway.disconnect(binding.im_user_id)
        except Exception:
            logger.warning(
                "Failed to disconnect WS for %s, proceeding with unbind",
                binding.im_user_id,
            )

        binding.unbind()
        await self._im_binding_repository.save(binding)

    async def get_binding_status(self, session_id: str) -> ImBinding | None:
        return await self._im_binding_repository.find_by_session_id(session_id)

    async def sync_message_to_im(self, command: SyncMessageToImCommand) -> None:
        binding = await self._im_binding_repository.find_by_session_id(command.session_id)

        if binding is None or binding.binding_status != BindingStatus.BOUND:
            logger.debug(
                "Skipping IM sync for session %s: no active binding",
                command.session_id,
            )
            return

        content = command.message
        if command.skills:
            content += f"\n\n---\nSkills: {', '.join(command.skills)}"

        try:
            await self._im_gateway.send_message(
                binding.im_user_id, binding.friend_user_id, content
            )
        except BusinessException:
            logger.warning(
                "Failed to sync message to IM for session %s",
                command.session_id,
            )

    async def handle_im_message(
        self, session_id: str, message: dict[str, Any]
    ) -> None:
        content = message.get("content", "")

        if not content or not content.strip():
            return

        try:
            await self._im_message_handler.handle_prompt(session_id, content)
        except Exception:
            logger.error(
                "Failed to handle IM message for session %s",
                session_id,
                exc_info=True,
            )

    @staticmethod
    def _format_message_for_im(message: Message) -> str:
        msg_type = message.message_type.value
        content = message.content

        if msg_type == "user":
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            return f"[User] {text}"

        if msg_type == "assistant":
            if isinstance(content, dict):
                blocks = content.get("blocks", [])
                text_parts = []
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                return f"[Assistant] {''.join(text_parts)}"
            return f"[Assistant] {content}"

        if msg_type == "tool_result":
            if isinstance(content, dict):
                results = content.get("results", [])
                return f"[Tool Result] {len(results)} result(s)"
            return f"[Tool Result] {content}"

        return f"[{msg_type}] {content}"

    async def _listen_im_messages(self, binding: ImBinding) -> None:
        try:
            message_iterator = await self._im_ws_gateway.listen_messages(
                binding.im_user_id
            )
            async for msg in message_iterator:
                sender_id = msg.get("sender_id", "")
                if sender_id == binding.im_user_id:
                    continue

                try:
                    await self.handle_im_message(binding.session_id, msg)
                except Exception:
                    logger.warning(
                        "Failed to process single IM message for %s",
                        binding.im_user_id,
                    )
        except BusinessException:
            logger.warning(
                "IM WS not connected for %s, listener stopped",
                binding.im_user_id,
            )
        except Exception:
            logger.info(
                "IM WS listener stopped for %s",
                binding.im_user_id,
            )
