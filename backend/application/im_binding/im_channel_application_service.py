from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable

from domain.shared.async_utils import safe_create_task
from typing import Any

from domain.im_binding.acl.im_channel_adapter import ImChannelAdapter, InitResult
from application.session.command.run_query_command import RunQueryCommand
from domain.session.acl.connection_manager import ConnectionManager
from application.session.session_application_service import SessionApplicationService
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_init import ChannelInit
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.repository.channel_init_repository import ChannelInitRepository
from domain.im_binding.repository.im_binding_repository import ImBindingRepository
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


class _RetryableInboundError(RuntimeError):
    pass


class ImChannelApplicationService:
    """统一 IM 渠道应用服务 — 渠道发现 / 实例管理 / 初始化 / 绑定 / 解绑 / 出站同步 / 入站消息"""

    def __init__(
        self,
        registry: ImChannelRegistry,
        binding_repo: ImBindingRepository,
        init_repo: ChannelInitRepository,
        session_service_factory: Callable[..., Awaitable[SessionApplicationService]] | None = None,
        connection_manager: ConnectionManager | None = None,
        get_pending_request_context_fn: Callable[[str], Awaitable[dict[str, Any] | None]] | None = None,
        resolve_user_response_fn: Callable[[str, dict[str, Any]], Awaitable[bool]] | None = None,
        accept_inbound_fn: Callable[..., Awaitable[bool]] | None = None,
        enqueue_outbound_fn: Callable[..., Awaitable[int | None]] | None = None,
    ) -> None:
        self._registry = registry
        self._binding_repo = binding_repo
        self._init_repo = init_repo
        self._session_service_factory = session_service_factory
        self._connection_manager = connection_manager
        self._get_pending_request_context = get_pending_request_context_fn
        self._resolve_user_response = resolve_user_response_fn
        self._accept_inbound = accept_inbound_fn
        self._enqueue_outbound = enqueue_outbound_fn

    # ── 渠道发现 ──

    async def list_available_channels(self) -> list[dict[str, Any]]:
        """返回所有已注册渠道类型, 每个类型下嵌套其实例列表."""
        all_inits = await self._init_repo.find_all()
        all_bindings = await self._binding_repo.find_all_bound()
        binding_by_channel_id = {b.channel_id: b for b in all_bindings}

        # Group instances by channel_type
        inits_by_type: dict[ImChannelType, list[ChannelInit]] = {}
        for ci in all_inits:
            inits_by_type.setdefault(ci.channel_type, []).append(ci)

        specs = self._registry.list_all()
        result = []
        for s in specs:
            instances = []
            for ci in inits_by_type.get(s.channel_type, []):
                b = binding_by_channel_id.get(ci.id)
                app_id = ci.config.get("app_id") or ci.config.get("appid") or ""
                instances.append({
                    "id": ci.id,
                    "name": ci.name,
                    "app_id": str(app_id),
                    "init_status": ci.init_status.value,
                    "error_message": ci.error_message,
                    "bound_session_id": b.session_id if b else "",
                })
            result.append({
                "channel_type": s.channel_type.value,
                "display_name": s.display_name,
                "icon": s.icon,
                "binding_mode": s.binding_mode.value,
                "init_mode": s.init_mode,
                "init_fields": list(s.init_fields),
                "description": s.description,
                "instances": instances,
            })
        return result

    # ── 渠道实例管理 ──

    async def create_channel_instance(
        self, channel_type: str, name: str = "",
    ) -> dict[str, Any]:
        """创建一个新的渠道实例."""
        ct = ImChannelType(channel_type)
        spec = self._registry.get_spec(ct)
        ci = ChannelInit.create(ct, name=name)
        # 默认名: DisplayName-短ID, 如 "QQ-a3f8"
        if not name:
            ci.rename(f"{spec.display_name}-{ci.id[:4]}")
        await self._init_repo.save(ci)
        return {
            "id": ci.id,
            "channel_type": ct.value,
            "name": ci.name,
            "init_status": ci.init_status.value,
        }

    async def delete_channel_instance(self, channel_id: str) -> None:
        """删除渠道实例, 若已绑定则先解绑."""
        ci = await self._init_repo.find_by_id(channel_id)
        if ci is None:
            return

        # If bound, unbind first
        binding = await self._binding_repo.find_by_channel_id(channel_id)
        if binding and binding.binding_status != BindingStatus.UNBOUND:
            try:
                adapter = self._create_adapter(ci.channel_type)
                await adapter.unbind(binding)
            except Exception:
                logger.warning("Adapter unbind failed during instance delete", exc_info=True)
            await self._binding_repo.remove(binding.session_id)
            if self._connection_manager:
                await self._connection_manager.broadcast(
                    binding.session_id,
                    {"event": "im_unbound", "channel_type": ci.channel_type.value},
                )

        await self._init_repo.remove(channel_id)

    async def rename_channel_instance(self, channel_id: str, name: str) -> dict[str, Any]:
        """重命名渠道实例."""
        ci = await self._init_repo.find_by_id(channel_id)
        if ci is None:
            raise BusinessException("Channel instance not found", "CHANNEL_NOT_FOUND")
        ci.rename(name)
        await self._init_repo.save(ci)
        return {
            "id": ci.id,
            "channel_type": ci.channel_type.value,
            "name": ci.name,
        }

    # ── 渠道初始化 ──

    async def get_channel_init_status(self, channel_id: str) -> dict[str, Any]:
        ci = await self._init_repo.find_by_id(channel_id)
        if ci is None:
            raise BusinessException("Channel instance not found", "CHANNEL_NOT_FOUND")
        spec = self._registry.get_spec(ci.channel_type)
        return {
            "channel_id": channel_id,
            "channel_type": ci.channel_type.value,
            "name": ci.name,
            "init_status": ci.init_status.value,
            "error_message": ci.error_message,
            "init_mode": spec.init_mode,
            "init_fields": list(spec.init_fields),
            "description": spec.description,
        }

    async def initialize_channel(
        self, channel_id: str, params: dict,
    ) -> dict[str, Any]:
        ci = await self._init_repo.find_by_id(channel_id)
        if ci is None:
            raise BusinessException("Channel instance not found", "CHANNEL_NOT_FOUND")

        ct = ci.channel_type
        logger.info("[IM-init] Initializing channel_id=%s type=%s", channel_id, ct.value)
        adapter = self._create_adapter(ct)

        if ci.init_status not in (
            ChannelInitStatus.NOT_INITIALIZED,
            ChannelInitStatus.ERROR,
            ChannelInitStatus.INITIALIZING,
        ):
            raise BusinessException(
                f"Channel instance {channel_id} is already initialized",
                "CHANNEL_ALREADY_INITIALIZED",
            )

        if ci.init_status != ChannelInitStatus.INITIALIZING:
            ci.start_init()

        result: InitResult = await adapter.initialize(params)
        logger.info(
            "[IM-init] Result: channel_id=%s status=%s error=%s",
            channel_id, result.status.value, result.error_message or "",
        )

        if result.status == ChannelInitStatus.READY:
            ci.complete_init(result.config)
            # 初始化成功后, 从 config 提取 app_id/appid 作为默认名
            auto_name = result.config.get("app_id") or result.config.get("appid") or ""
            if auto_name:
                ci.rename(str(auto_name))
        elif result.status == ChannelInitStatus.ERROR:
            ci.fail_init(result.error_message)

        await self._init_repo.save(ci)
        return {
            "channel_id": channel_id,
            "channel_type": ct.value,
            "init_status": ci.init_status.value,
            "error_message": ci.error_message,
            "ui_data": result.ui_data,
        }

    async def reset_channel(self, channel_id: str) -> None:
        ci = await self._init_repo.find_by_id(channel_id)
        if ci is None:
            return
        ci.reset()
        await self._init_repo.save(ci)

    # ── 绑定状态 ──

    async def get_binding(self, session_id: str) -> ImBinding | None:
        return await self._binding_repo.find_by_session_id(session_id)

    async def list_all_bindings(self) -> list[dict[str, Any]]:
        """Return summary of all active bindings for session list enrichment."""
        bindings = await self._binding_repo.find_all_bound()
        return [
            {
                "session_id": b.session_id,
                "channel_type": b.channel_type.value,
                "channel_id": b.channel_id,
                "binding_status": b.binding_status.value,
            }
            for b in bindings
        ]

    # ── 绑定 ──

    async def bind(
        self, session_id: str, channel_id: str, params: dict,
    ) -> dict[str, Any]:
        ci = await self._init_repo.find_by_id(channel_id)
        if ci is None:
            raise BusinessException("Channel instance not found", "CHANNEL_NOT_FOUND")

        ct = ci.channel_type
        logger.info("[IM-bind] Starting: session=%s channel_id=%s type=%s", session_id, channel_id, ct.value)

        # 检查实例是否已初始化
        if not ci.is_ready:
            adapter = self._create_adapter(ct)
            config = ci.config
            if await adapter.check_init_status(config):
                ci.start_init()
                ci.complete_init(config)
                await self._init_repo.save(ci)
            else:
                spec = self._registry.get_spec(ct)
                return {
                    "action": "init_required",
                    "channel_id": channel_id,
                    "channel_type": ct.value,
                    "display_name": spec.display_name,
                    "init_status": ci.init_status.value,
                    "init_fields": list(spec.init_fields),
                    "init_mode": spec.init_mode,
                    "description": spec.description,
                }

        # 检查实例是否已绑定其他会话
        existing_binding = await self._binding_repo.find_by_channel_id(channel_id)
        if existing_binding and existing_binding.session_id != session_id:
            raise BusinessException(
                f"Channel instance already bound to session {existing_binding.session_id}",
                "CHANNEL_ALREADY_BOUND",
            )

        # 检查会话是否已有其他绑定 → 先解绑
        current_binding = await self._binding_repo.find_by_session_id(session_id)
        if current_binding and current_binding.channel_id != channel_id:
            logger.info(
                "[IM-bind] Session %s already bound to channel_id=%s, unbinding first",
                session_id, current_binding.channel_id,
            )
            try:
                await self._create_adapter(current_binding.channel_type).unbind(current_binding)
            except Exception:
                logger.warning("[IM-bind] Old binding unbind failed", exc_info=True)
            await self._binding_repo.remove(session_id)
            if self._connection_manager:
                await self._connection_manager.broadcast(
                    session_id,
                    {"event": "im_unbound", "channel_type": current_binding.channel_type.value},
                )

        adapter = self._create_adapter(ct)

        # 收集路由上下文
        routing_carry_over: dict[str, str] = {}
        if ci.config:
            for key in adapter.routing_config_keys():
                val = ci.config.get(key, "")
                if val:
                    routing_carry_over[key] = val

        # 执行绑定
        binding = existing_binding or ImBinding.create(session_id, ct, channel_id=channel_id)
        if existing_binding is None or existing_binding.binding_status != BindingStatus.BINDING:
            binding.start_binding_process()

        bind_params = {**ci.config, **params}
        result = await adapter.bind(session_id, binding, bind_params)

        if result.status == BindingStatus.BOUND:
            binding.complete_channel_binding(result.channel_address, result.config)
            if routing_carry_over:
                binding.update_config(routing_carry_over)
                logger.info("[IM-bind] Routing context carried over: %s", list(routing_carry_over.keys()))
        elif result.status == BindingStatus.BINDING:
            binding.start_binding_process()
            if result.channel_address:
                binding.set_channel_address(result.channel_address)
            if result.config:
                binding.update_config(result.config)

        await self._binding_repo.save(binding)

        if binding.binding_status == BindingStatus.BOUND:
            logger.info("[IM-bind] Binding complete: session=%s channel_id=%s", session_id, channel_id)
            await self.start_channel_listener(binding)
            await self._send_bind_notification(binding, adapter)

        return {
            "id": binding.id,
            "session_id": binding.session_id,
            "channel_type": binding.channel_type.value,
            "channel_id": binding.channel_id,
            "binding_status": binding.binding_status.value,
            "channel_address": binding.channel_address,
            "ui_data": result.ui_data,
        }

    # ── 完成绑定 ──

    async def complete_binding(
        self, session_id: str, channel_id: str, params: dict,
    ) -> dict[str, Any]:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None or binding.channel_id != channel_id:
            raise BusinessException("No pending binding found", "IM_BINDING_NOT_FOUND")

        adapter = self._create_adapter(binding.channel_type)
        result = await adapter.complete_bind(binding, params)

        if result.status == BindingStatus.BOUND:
            binding.complete_channel_binding(result.channel_address, result.config)
        await self._binding_repo.save(binding)

        if binding.binding_status == BindingStatus.BOUND:
            await self.start_channel_listener(binding)
            await self._send_bind_notification(binding, adapter)

        return {
            "id": binding.id,
            "session_id": binding.session_id,
            "channel_type": binding.channel_type.value,
            "channel_id": binding.channel_id,
            "binding_status": binding.binding_status.value,
            "channel_address": binding.channel_address,
            "ui_data": result.ui_data,
        }

    # ── 解绑 ──

    async def unbind(self, session_id: str) -> None:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None:
            return

        try:
            adapter = self._create_adapter(binding.channel_type)
            await adapter.unbind(binding)
        except Exception:
            logger.warning(
                "Adapter unbind failed for session %s",
                session_id, exc_info=True,
            )

        await self._binding_repo.remove(session_id)

    # ── 出站消息同步 ──

    async def sync_outbound(self, session_id: str, content: str) -> None:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None or binding.binding_status != BindingStatus.BOUND:
            return
        reply_ctx = self._build_reply_context(binding)
        if self._enqueue_outbound is not None:
            await self._enqueue_outbound(
                session_id,
                content,
                reply_context=reply_ctx,
                binding=binding,
            )
            return
        adapter = self._create_adapter(binding.channel_type)
        await adapter.send_message(binding, content, reply_context=reply_ctx)

    # ── 同步会话上下文到 IM ──

    async def sync_session_context(self, session_id: str) -> dict[str, Any]:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None or binding.binding_status != BindingStatus.BOUND:
            raise BusinessException("No active IM binding for this session", "IM_NOT_BOUND")

        from infr.config.database import async_session_factory
        from infr.repository.session_repository_impl import SessionRepositoryImpl

        entries: list[str] = []
        async with async_session_factory() as bg_session:
            repo = SessionRepositoryImpl(bg_session)
            session = await repo.find_by_id(session_id)
            if session is None:
                raise BusinessException("Session not found")

            for msg in session.messages:
                role = msg.message_type.value
                if role not in ("user", "assistant"):
                    continue
                t = self._extract_text_from_content(msg.content)
                if not t:
                    continue
                label = "User" if role == "user" else "Claude"
                entries.append(f"[{label}]\n{t}")

        if not entries:
            return {"synced": 0}

        reply_ctx = self._build_reply_context(binding)

        chunk: list[str] = []
        chunk_len = 0
        sent = 0
        failed = 0
        max_chunk = 1500
        sync_operation_id = uuid.uuid4().hex
        chunk_index = 0

        async def _flush() -> None:
            nonlocal sent, failed, chunk_index
            if not chunk:
                return
            text = "\n\n---\n\n".join(chunk)
            current_chunk_index = chunk_index
            chunk_index += 1
            try:
                payload = f"[Context Sync]\n\n{text}"
                if self._enqueue_outbound is not None:
                    await self._enqueue_outbound(
                        session_id,
                        payload,
                        deduplication_key=(
                            f"context:{session_id}:{sync_operation_id}:{current_chunk_index}"
                        ),
                        reply_context=reply_ctx,
                        binding=binding,
                    )
                else:
                    adapter = self._create_adapter(binding.channel_type)
                    await adapter.send_message(
                        binding,
                        payload,
                        reply_context=reply_ctx,
                    )
                sent += len(chunk)
            except Exception:
                logger.warning("[sync-context] Chunk send failed for session=%s", session_id, exc_info=True)
                failed += len(chunk)

        for entry in entries:
            entry_len = len(entry)
            if chunk and chunk_len + entry_len > max_chunk:
                await _flush()
                chunk.clear()
                chunk_len = 0
                await asyncio.sleep(0.2)
            chunk.append(entry)
            chunk_len += entry_len

        await _flush()

        if failed and sent == 0:
            raise BusinessException(
                f"Failed to send all {failed} messages to IM channel",
                "IM_SYNC_FAILED",
            )

        return {"synced": sent, "failed": failed}

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        if isinstance(content, dict):
            plain = content.get("text", "")
            if plain and isinstance(plain, str):
                return plain.strip()
            blocks = content.get("blocks", [])
        elif isinstance(content, list):
            blocks = content
        else:
            return ""
        if blocks:
            texts = [
                b.get("text", "")
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            return "".join(texts).strip()
        return ""

    # ── 入站消息处理 ──

    async def _process_inbound(
        self,
        binding: ImBinding,
        message_id: str,
        content: str,
        sender_id: str,
        group_id: str,
    ) -> None:
        if not self._session_service_factory:
            logger.error("[IM-process] No session_service_factory — cannot process inbound")
            return

        await self._persist_reply_context(binding, sender_id, group_id)

        adapter = self._create_adapter(binding.channel_type)
        reply_ctx_base = {"msg_id": message_id, "sender_id": sender_id, "group_id": group_id}
        delivery_channel_id = binding.channel_id or binding.id
        source_digest = hashlib.sha256(
            f"{delivery_channel_id}:{message_id}".encode("utf-8")
        ).hexdigest()
        source_message_id = f"im:{source_digest}"[:64]

        # Add "working" reaction for Lark channels
        reaction_id = ""
        if hasattr(adapter, 'add_reaction') and message_id:
            try:
                reaction_id = await adapter.add_reaction(binding, message_id, "OnIt")
            except Exception:
                logger.debug("[IM-process] add_reaction failed, continuing", exc_info=True)

        from infr.config.database import async_session_factory

        try:
            async with async_session_factory() as db_session:
                session_service = await self._session_service_factory(db_session)
                # Disable IM sync callbacks — this inbound flow handles its own
                # reply via adapter.send_message; letting the callbacks fire would
                # cause duplicate messages back to the IM channel.
                session_service._query_engine._on_assistant_response = None
                session_service._query_engine._on_user_message = None
                try:
                    session = await session_service.get_session(binding.session_id)
                except BusinessException:
                    logger.warning("[IM-process] Session %s no longer exists, skipping", binding.session_id)
                    return
                if session.is_running:
                    # Check if waiting for user input (AskUserQuestion / permission)
                    if await self._try_resolve_pending_response(binding.session_id, content):
                        logger.info("[IM-process] Resolved pending user response via IM: session=%s", binding.session_id)
                        return
                    raise _RetryableInboundError("Session is busy")

                existing_index = next(
                    (
                        index
                        for index, message in enumerate(session.messages)
                        if message.message_type == MessageType.USER
                        and message.content.get("message_id") == source_message_id
                    ),
                    None,
                )
                if existing_index is not None:
                    response = self._extract_response_after(session, existing_index)
                    if response:
                        await self._send_inbound_reply(
                            binding,
                            response,
                            reply_ctx_base,
                            f"inbox:{delivery_channel_id}:{message_id}:response",
                        )
                        return
                    result_error = self._extract_result_error_after(
                        session,
                        existing_index,
                    )
                    if result_error:
                        await self._send_inbound_reply(
                            binding,
                            f"[Error] {result_error[:500]}",
                            reply_ctx_base,
                            f"inbox:{delivery_channel_id}:{message_id}:query-error",
                        )
                        return

                if self._connection_manager:
                    user_msg = Message.create(
                        message_type=MessageType.USER,
                        content={
                            "message_id": source_message_id,
                            "text": content,
                            "source": binding.channel_type.value,
                        },
                    )
                    await self._connection_manager.broadcast(
                        binding.session_id,
                        {"event": "message", "data": {"type": user_msg.message_type.value, "content": user_msg.content}},
                    )

                command = RunQueryCommand(
                    session_id=binding.session_id,
                    prompt=content,
                    client_message_id=source_message_id,
                )
                msg_count_before = session.message_count
                await session_service.run_claude_query(command)
                try:
                    await db_session.commit()
                except Exception:
                    logger.warning("[IM-process] db_session commit failed after query: session=%s", binding.session_id, exc_info=True)

            # Use a fresh DB session to read result — the previous session
            # may be invalidated if run_claude_query hit a DB error internally
            async with async_session_factory() as db_session2:
                session_service2 = await self._session_service_factory(db_session2)
                session = await session_service2.get_session(binding.session_id)

                user_index = next(
                    (
                        index
                        for index, message in enumerate(session.messages)
                        if message.message_type == MessageType.USER
                        and message.content.get("message_id") == source_message_id
                    ),
                    None,
                )
                response = (
                    self._extract_response_after(session, user_index)
                    if user_index is not None
                    else ""
                )
                if not response:
                    result_error = (
                        self._extract_result_error_after(session, user_index)
                        if user_index is not None
                        else ""
                    )
                    if result_error:
                        await self._send_inbound_reply(
                            binding,
                            f"[Error] {result_error[:500]}",
                            reply_ctx_base,
                            f"inbox:{delivery_channel_id}:{message_id}:query-error",
                        )
                        return
                    logger.warning(
                        "[IM-process] No response for inbound request: "
                        "session=%s message_id=%s before=%s after=%s",
                        binding.session_id,
                        source_message_id,
                        msg_count_before,
                        session.message_count,
                    )
                    raise _RetryableInboundError(
                        "Inbound query did not produce an assistant response"
                    )

            if response:
                await self._send_inbound_reply(
                    binding,
                    response,
                    reply_ctx_base,
                    f"inbox:{delivery_channel_id}:{message_id}:response",
                )
            else:
                logger.warning("[IM-process] No response extracted: session=%s", binding.session_id)

        except _RetryableInboundError:
            raise
        except Exception as exc:
            logger.error("[IM-process] Failed to process inbound: session=%s", binding.session_id, exc_info=True)
            try:
                await self._send_inbound_reply(
                    binding,
                    f"[Error] {str(exc)[:200]}",
                    reply_ctx_base,
                    f"inbox:{delivery_channel_id}:{message_id}:processing-error",
                )
            except Exception:
                logger.warning("[IM-process] Failed to send error notification to IM", exc_info=True)
            raise
        finally:
            # Remove "working" reaction
            if reaction_id and hasattr(adapter, 'remove_reaction'):
                try:
                    await adapter.remove_reaction(binding, message_id, reaction_id)
                except Exception:
                    logger.debug("[IM-process] remove_reaction failed", exc_info=True)

    @staticmethod
    def _extract_last_response(session: Any) -> str:
        for msg in reversed(session.messages):
            if msg.message_type.value == "assistant":
                text = ImChannelApplicationService._extract_text_from_content(msg.content)
                if text:
                    return text
        return ""

    @staticmethod
    def _extract_response_after(session: Any, message_index: int) -> str:
        response = ""
        completed = False
        failed = False
        for message in session.messages[message_index + 1:]:
            if message.message_type == MessageType.USER:
                break
            if message.message_type == MessageType.ASSISTANT:
                text = ImChannelApplicationService._extract_text_from_content(message.content)
                if text:
                    response = text
            elif message.message_type == MessageType.RESULT:
                completed = True
                failed = message.content.get("is_error") is True
        return response if completed and not failed else ""

    @staticmethod
    def _extract_result_error_after(session: Any, message_index: int) -> str:
        for message in session.messages[message_index + 1:]:
            if message.message_type == MessageType.USER:
                break
            if (
                message.message_type == MessageType.RESULT
                and message.content.get("is_error") is True
            ):
                error_text = str(message.content.get("text", "")).strip()
                return error_text or "Query failed"
        return ""

    async def process_inbound_event(
        self,
        binding: ImBinding,
        message_id: str,
        content: str,
        sender_id: str,
        group_id: str,
    ) -> None:
        await self._process_inbound(binding, message_id, content, sender_id, group_id)

    async def _send_inbound_reply(
        self,
        binding: ImBinding,
        content: str,
        reply_context: dict[str, Any],
        deduplication_key: str,
    ) -> None:
        adapter = self._create_adapter(binding.channel_type)
        resolved_context = adapter.build_reply_context(binding) or {}
        resolved_context.update(reply_context)
        if self._enqueue_outbound is not None:
            await self._enqueue_outbound(
                binding.session_id,
                content,
                deduplication_key=deduplication_key,
                reply_context=resolved_context,
                binding=binding,
            )
            return
        await adapter.send_message(
            binding,
            content,
            reply_context=resolved_context,
            idempotency_key=deduplication_key,
        )

    # ── Channel listener lifecycle ──

    async def start_channel_listener(self, binding: ImBinding) -> None:
        adapter = self._create_adapter(binding.channel_type)
        if not hasattr(adapter, "start_listening"):
            return

        channel_type_val = binding.channel_type.value
        session_id = binding.session_id

        async def on_message(
            msg_id: str, content: str, sender_id: str, group_id: str | None,
        ) -> None:
            logger.info(
                "[IM-listener] Message received: channel=%s session=%s msg_id=%s",
                channel_type_val, session_id, msg_id,
            )
            if self._accept_inbound is not None:
                for attempt in range(5):
                    try:
                        await self._accept_inbound(
                            binding,
                            msg_id,
                            content,
                            sender_id,
                            group_id or "",
                        )
                        break
                    except Exception:
                        if attempt == 4:
                            logger.error(
                                "[IM-listener] Failed to persist inbound after retries: "
                                "channel=%s message_id=%s",
                                channel_type_val,
                                msg_id,
                                exc_info=True,
                            )
                            raise
                        logger.warning(
                            "[IM-listener] Inbound persistence retry: "
                            "channel=%s message_id=%s attempt=%s",
                            channel_type_val,
                            msg_id,
                            attempt + 1,
                            exc_info=True,
                        )
                        await asyncio.sleep(min(8, 2 ** attempt))
            else:
                safe_create_task(
                    self._process_inbound(binding, msg_id, content, sender_id, group_id or "")
                )

        try:
            await adapter.start_listening(binding, on_message)
            logger.info("[IM-listener] Listener started: channel=%s session=%s", channel_type_val, session_id)
        except Exception:
            logger.error("[IM-listener] Failed to start listener: channel=%s session=%s", channel_type_val, session_id, exc_info=True)

    # ── Internal ──

    async def _send_bind_notification(
        self, binding: ImBinding, adapter: ImChannelAdapter,
    ) -> None:
        reply_ctx = adapter.build_reply_context(binding)
        if not reply_ctx:
            return
        try:
            await adapter.send_message(
                binding,
                f"已绑定会话: {binding.session_id}",
                reply_context=reply_ctx,
            )
        except Exception:
            logger.warning("[IM-bind] Failed to send binding notification", exc_info=True)

    def _build_reply_context(self, binding: ImBinding) -> dict[str, str] | None:
        adapter = self._create_adapter(binding.channel_type)
        return adapter.build_reply_context(binding)

    async def _try_resolve_pending_response(self, session_id: str, im_text: str) -> bool:
        """Try to resolve a pending AskUserQuestion/permission from IM text reply.

        Returns True if a pending request was resolved.
        """
        if not self._get_pending_request_context or not self._resolve_user_response:
            return False

        ctx = await self._get_pending_request_context(session_id)
        if ctx is None:
            return False

        tool_name = ctx.get("tool_name", "")
        if tool_name == "AskUserQuestion":
            answers = self._parse_im_choice_answers(ctx.get("questions", []), im_text)
            return await self._resolve_user_response(session_id, {"answers": answers})
        else:
            # Permission request: "y"/"yes"/"allow"/"1" → allow, anything else → deny
            decision = "allow" if im_text.strip().lower() in ("y", "yes", "allow", "1", "是", "允许") else "deny"
            return await self._resolve_user_response(session_id, {"decision": decision})

    @staticmethod
    def _parse_im_choice_answers(questions: list[dict], im_text: str) -> dict[str, str]:
        """Parse IM text reply into AskUserQuestion answers.

        Supports:
        - Single question: "1" or "2" (option number) or exact option label
        - Multiple questions: "1,2" or "1\\n2" (one answer per question, in order)
        """
        text = im_text.strip()
        answers: dict[str, str] = {}

        # Split by newline or comma for multi-question
        parts = [p.strip() for p in text.replace(",", "\n").replace("，", "\n").split("\n") if p.strip()]

        for i, q in enumerate(questions):
            question_text = q.get("question", "")
            options = q.get("options", [])
            part = parts[i] if i < len(parts) else parts[0] if parts else text

            # Try as number (1-based index)
            try:
                idx = int(part) - 1
                if 0 <= idx < len(options):
                    answers[question_text] = options[idx].get("label", "")
                    continue
            except ValueError:
                pass

            # Try as exact label match (case-insensitive)
            for opt in options:
                if opt.get("label", "").lower() == part.lower():
                    answers[question_text] = opt["label"]
                    break
            else:
                # Fallback: use raw text as "Other" answer
                answers[question_text] = part

        return answers

    async def _persist_reply_context(
        self, binding: ImBinding, sender_id: str, group_id: str,
    ) -> None:
        adapter = self._create_adapter(binding.channel_type)
        routing_ctx = adapter.extract_routing_context(sender_id, group_id)

        for key in adapter.routing_config_keys():
            if key not in routing_ctx:
                val = binding.config.get(key, "")
                if val:
                    routing_ctx[key] = val

        if not routing_ctx:
            return

        binding.update_config(routing_ctx)

        from infr.config.database import async_session_factory
        from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
        from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl

        try:
            async with async_session_factory() as db_session:
                repo = ImBindingRepositoryImpl(db_session)
                fresh = await repo.find_by_session_id(binding.session_id)
                if fresh:
                    fresh.update_config(routing_ctx)
                    await repo.save(fresh)

                # Persist to channel instance (实例级路由)
                if binding.channel_id:
                    init_repo = ChannelInitRepositoryImpl(db_session)
                    ci = await init_repo.find_by_id(binding.channel_id)
                    if ci:
                        ci.update_config(routing_ctx)
                        await init_repo.save(ci)

                await db_session.commit()
        except Exception:
            logger.warning(
                "[IM-process] Failed to persist reply context for session=%s",
                binding.session_id, exc_info=True,
            )

    def _create_adapter(self, channel_type: ImChannelType) -> ImChannelAdapter:
        factory = self._registry.get_adapter_factory(channel_type)
        return factory()
