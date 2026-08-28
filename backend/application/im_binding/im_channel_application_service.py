from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, AsyncContextManager

from domain.shared.async_utils import safe_create_task

from application.im_binding.im_channel_facade import ImChannelFacade
from application.im_binding.inbound_progress_reporter import (
    InboundProgressReporter,
    TaskOutcome,
)
from domain.im_binding.acl.im_channel_adapter import InitResult
from application.session.command.run_query_command import RunQueryCommand
from domain.session.acl.connection_manager import ConnectionManager
from application.session.session_application_service import SessionApplicationService
from application.session.session_presenter import SessionPresenter
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_init import ChannelInit
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_delivery import ImInboxEvent
from domain.im_binding.model.im_message import (
    InboundMessage,
    MessageSegment,
    OutboundMessage,
)
from domain.im_binding.repository.channel_init_repository import ChannelInitRepository
from domain.im_binding.repository.im_binding_repository import ImBindingRepository
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.service.message_conversion_service import MessageConversionService
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)

_SESSION_BUSY_REASON = "Session is busy"


class RetryableInboundError(RuntimeError):
    pass


class SessionBusyError(RetryableInboundError):
    """会话正在执行其他任务 — 延后重试即可, 不是本事件的失败."""


class TerminalInboundError(RuntimeError):
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
        stage_inbound_attachments_fn: Callable[
            [Any, list[dict[str, Any]]],
            Awaitable[list[dict[str, Any]]],
        ] | None = None,
        # DIP-compliant factories: Application layer obtains independent-scoped
        # repositories/services via these injected factories rather than importing
        # infr implementations directly.
        session_service_context_factory: Callable[[], AsyncContextManager[SessionApplicationService]] | None = None,
        binding_context_factory: Callable[[], AsyncContextManager[tuple[ImBindingRepository, ChannelInitRepository]]] | None = None,
        # Commits the caller's unit of work. Required to make state visible to
        # other DB connections before a broadcast invites clients to re-read it.
        commit_unit_of_work: Callable[[], Awaitable[None]] | None = None,
        mode: str = "dev",
    ) -> None:
        self._registry = registry
        self._facade = ImChannelFacade(registry)
        self._binding_repo = binding_repo
        self._init_repo = init_repo
        self._session_service_factory = session_service_factory
        self._connection_manager = connection_manager
        self._get_pending_request_context = get_pending_request_context_fn
        self._resolve_user_response = resolve_user_response_fn
        self._accept_inbound = accept_inbound_fn
        self._enqueue_outbound = enqueue_outbound_fn
        self._stage_inbound_attachments = stage_inbound_attachments_fn
        self._session_service_context_factory = session_service_context_factory
        self._binding_context_factory = binding_context_factory
        self._commit_unit_of_work = commit_unit_of_work
        self._mode = mode

    # ── 渠道发现 ──

    async def list_available_channels(self, user_id: int | None = None) -> list[dict[str, Any]]:
        """返回所有已注册渠道类型, 每个类型下嵌套其实例列表."""
        if user_id is not None and self._mode == "pro":
            all_inits = await self._init_repo.find_all_by_user_id(user_id)
        else:
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
                "capabilities": sorted(c.value for c in s.capabilities),
                "missing_capabilities": sorted(
                    c.value for c in s.missing_capabilities
                ),
                "instances": instances,
            })
        return result

    # ── 渠道实例管理 ──

    async def create_channel_instance(
        self, channel_type: str, name: str = "", user_id: int = 1,
    ) -> dict[str, Any]:
        """创建一个新的渠道实例."""
        ct = ImChannelType(channel_type)
        spec = self._registry.get_spec(ct)
        ci = ChannelInit.create(ct, name=name, user_id=user_id)
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

        # If bound, unbind first — but announce it only once the instance row
        # is gone too, so clients reload against the final state.
        binding = await self._binding_repo.find_by_channel_id(channel_id)
        if binding is not None and binding.binding_status == BindingStatus.UNBOUND:
            binding = None
        if binding is not None:
            await self._force_unbind(binding, notify=False)

        await self._init_repo.remove(channel_id)

        if binding is not None:
            await self._notify_unbound(binding)

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

        result: InitResult = await self._facade.initialize(ct, params)
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
            config = ci.config
            if await self._facade.check_init_status(ct, config):
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
            # No im_unbound broadcast: the session is being rebound, not
            # unbound, and this response already carries the resulting state.
            await self._force_unbind(current_binding, notify=False)

        # 换绑时继承已有的路由上下文, 否则新绑定要等用户先发一条消息才能回复
        routing_carry_over: dict[str, str] = {}
        if ci.config:
            for key in self._facade.route_config_keys(ct):
                val = ci.config.get(key, "")
                if val:
                    routing_carry_over[key] = val

        # 执行绑定
        binding = existing_binding or ImBinding.create(session_id, ct, channel_id=channel_id)
        if existing_binding is None or existing_binding.binding_status != BindingStatus.BINDING:
            binding.start_binding_process()

        bind_params = {**ci.config, **params}
        result = await self._facade.bind(session_id, binding, bind_params)

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
            await self._send_bind_notification(binding)

        return self._binding_result_dict(binding, result.ui_data)

    # ── 完成绑定 ──

    async def complete_binding(
        self, session_id: str, channel_id: str, params: dict,
    ) -> dict[str, Any]:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None or binding.channel_id != channel_id:
            raise BusinessException("No pending binding found", "IM_BINDING_NOT_FOUND")

        result = await self._facade.complete_bind(binding, params)

        if result.status == BindingStatus.BOUND:
            binding.complete_channel_binding(result.channel_address, result.config)
        await self._binding_repo.save(binding)

        if binding.binding_status == BindingStatus.BOUND:
            await self.start_channel_listener(binding)
            await self._send_bind_notification(binding)

        return self._binding_result_dict(binding, result.ui_data)

    # ── 解绑 ──

    async def unbind(self, session_id: str) -> None:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None:
            return

        await self._force_unbind(binding)

    # ── 出站消息同步 ──

    async def sync_outbound(
        self,
        session_id: str,
        content: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None or binding.binding_status != BindingStatus.BOUND:
            return
        await self._dispatch_outbound(
            binding,
            OutboundMessage.of_text_with_attachments(
                content,
                attachments,
                route=self._facade.restore_route(binding),
            ),
        )

    async def _dispatch_outbound(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> None:
        """经持久化队列投递出站消息; 未装配队列时（测试）直接调门面发送."""
        if self._enqueue_outbound is not None:
            await self._enqueue_outbound(
                binding.session_id,
                message.plain_text,
                attachments=[
                    segment.to_attachment() for segment in message.media_segments
                ],
                deduplication_key=message.idempotency_key or None,
                route=message.route,
                binding=binding,
            )
            return
        await self._facade.send(binding, message)

    # ── 同步会话上下文到 IM ──

    async def sync_session_context(self, session_id: str) -> dict[str, Any]:
        binding = await self._binding_repo.find_by_session_id(session_id)
        if binding is None or binding.binding_status != BindingStatus.BOUND:
            raise BusinessException("No active IM binding for this session", "IM_NOT_BOUND")

        if self._session_service_context_factory is None:
            raise BusinessException("No session service context factory configured for context sync")

        entries: list[str] = []
        async with self._session_service_context_factory() as _svc:
            session = await _svc.get_session(session_id)

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

        route = self._facade.restore_route(binding)

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
                await self._dispatch_outbound(
                    binding,
                    OutboundMessage.of_text(
                        f"[Context Sync]\n\n{text}",
                        route=route,
                        idempotency_key=(
                            f"context:{session_id}:{sync_operation_id}:"
                            f"{current_chunk_index}"
                        ),
                    ),
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
        message: InboundMessage,
        *,
        is_final_attempt: bool = False,
    ) -> None:
        if not self._session_service_factory:
            logger.error("[IM-process] No session_service_factory — cannot process inbound")
            return

        route = message.route.with_reply_to(message.external_message_id)
        await self._persist_route(binding, route)

        delivery_channel_id = binding.channel_id or binding.id
        source_digest = hashlib.sha256(
            f"{delivery_channel_id}:{message.external_message_id}".encode("utf-8")
        ).hexdigest()
        source_message_id = f"im:{source_digest}"[:64]

        async def reply(content: str, purpose: str) -> None:
            await self._dispatch_outbound(
                binding,
                OutboundMessage.of_text(
                    content,
                    route=route,
                    idempotency_key=(
                        f"inbox:{delivery_channel_id}:"
                        f"{message.external_message_id}:{purpose}"
                    ),
                ),
            )

        reporter = InboundProgressReporter(
            facade=self._facade,
            binding=binding,
            route=route,
            source_message_id=message.external_message_id,
            task_code=source_digest[:6].upper(),
            send_text=reply,
        )

        async with reporter:
            try:
                response = await self._execute_inbound(
                    binding, message, source_message_id, route,
                )
                if response:
                    await reply(
                        reporter.decorate(TaskOutcome.COMPLETED, response),
                        "response",
                    )
            except TerminalInboundError as exc:
                await reply(
                    reporter.decorate(
                        TaskOutcome.FAILED, f"原因：{str(exc)[:500]}",
                    )
                    if reporter.uses_task_framing
                    else f"[Error] {str(exc)[:500]}",
                    "query-error",
                )
            except SessionBusyError:
                await reporter.report_waiting(
                    "当前会话仍有任务在执行。这条消息已收到，系统会稍后自动重试。",
                )
                raise
            except RetryableInboundError:
                raise
            except Exception as exc:
                logger.error(
                    "[IM-process] Failed to process inbound: session=%s",
                    binding.session_id,
                    exc_info=True,
                )
                # 中间几次失败保持安静, 只在不会再重试时才打扰用户.
                if is_final_attempt:
                    await self._notify_inbound_failure(reporter, reply, exc)
                raise

    @staticmethod
    async def _notify_inbound_failure(
        reporter: InboundProgressReporter,
        reply: Callable[[str, str], Awaitable[None]],
        exc: Exception,
    ) -> None:
        try:
            await reply(
                reporter.decorate(TaskOutcome.FAILED, f"原因：{str(exc)[:200]}")
                if reporter.uses_task_framing
                else f"[Error] {str(exc)[:200]}",
                "processing-error",
            )
        except Exception:
            logger.warning(
                "[IM-process] Failed to send error notification to IM", exc_info=True,
            )

    async def _execute_inbound(
        self,
        binding: ImBinding,
        message: InboundMessage,
        source_message_id: str,
        route: ChannelRoute,
    ) -> str:
        """Execute the inbound query and return the assistant response text."""
        if self._session_service_context_factory is None:
            raise RuntimeError(
                "IM inbound processing requires a session service context factory"
            )
        async with self._session_service_context_factory() as session_service:
            # 结果由入站编排层统一回投, 抑制引擎侧回调避免双发
            session_service.suppress_outbound_callbacks()
            try:
                session = await session_service.get_session(binding.session_id)
            except BusinessException:
                logger.warning("[IM-process] Session %s no longer exists, skipping", binding.session_id)
                return ""

            content = message.plain_text
            attachment_refs = await self._stage_attachments(binding, session, message)

            if session.is_running:
                if await self._try_resolve_pending_response(binding.session_id, content):
                    logger.info("[IM-process] Resolved pending user response via IM: session=%s", binding.session_id)
                    return ""
                raise SessionBusyError(_SESSION_BUSY_REASON)

            cached = self._try_cached_inbound_response(session, source_message_id)
            if cached is not None:
                return cached

            await self._broadcast_inbound_user_message(binding, content, source_message_id, attachment_refs)

            command = self._build_inbound_query_command(binding, content, source_message_id, attachment_refs)
            msg_count_before = session.message_count
            await session_service.run_claude_query(command)
            try:
                await session_service.commit()
            except Exception:
                logger.warning("[IM-process] commit failed after query: session=%s", binding.session_id, exc_info=True)

        return await self._read_inbound_result(
            binding, source_message_id, msg_count_before,
        )

    async def _stage_attachments(
        self, binding: ImBinding, session: Any, message: InboundMessage,
    ) -> list[dict[str, Any]]:
        """把渠道下载到本地的附件搬进会话工作区.

        仅对声明了入站附件能力的渠道执行; 其余渠道的入站消息不会带附件。
        """
        if not self._facade.supports(
            binding.channel_type, ChannelCapability.INBOUND_ATTACHMENT,
        ):
            return []
        refs = message.attachments(binding.channel_type.value)
        if not refs or self._stage_inbound_attachments is None:
            return refs
        return await self._stage_inbound_attachments(session, refs)

    def _try_cached_inbound_response(
        self, session: Any, source_message_id: str,
    ) -> str | None:
        """Check if this message was already processed. Returns the response, or None if not cached."""
        existing_index = next(
            (
                index
                for index, message in enumerate(session.messages)
                if message.message_type == MessageType.USER
                and message.content.get("message_id") == source_message_id
            ),
            None,
        )
        if existing_index is None:
            return None

        response = self._extract_response_after(session, existing_index)
        if response:
            return response
        result_error = self._extract_result_error_after(session, existing_index)
        if result_error:
            raise TerminalInboundError(result_error[:500])
        return None

    async def _broadcast_inbound_user_message(
        self, binding: ImBinding, content: str, source_message_id: str, attachment_refs: list,
    ) -> None:
        if not self._connection_manager:
            return
        user_msg = Message.create(
            message_type=MessageType.USER,
            content={
                "message_id": source_message_id,
                "text": content,
                "source": binding.channel_type.value,
                "attachments": attachment_refs,
            },
        )
        await self._connection_manager.broadcast(
            binding.session_id,
            {"event": "message", "data": SessionPresenter.message_to_dict(user_msg)},
        )

    async def _read_inbound_result(
        self,
        binding: ImBinding,
        source_message_id: str,
        msg_count_before: int,
    ) -> str:
        """Read query result from a fresh DB session after execution."""
        async with self._session_service_context_factory() as session_service:
            session = await session_service.get_session(binding.session_id)

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
            if response:
                return response

            result_error = (
                self._extract_result_error_after(session, user_index)
                if user_index is not None
                else ""
            )
            if result_error:
                raise TerminalInboundError(result_error[:500])

            logger.warning(
                "[IM-process] No response for inbound request: "
                "session=%s message_id=%s before=%s after=%s",
                binding.session_id,
                source_message_id,
                msg_count_before,
                session.message_count,
            )
            raise RetryableInboundError(
                "Inbound query did not produce an assistant response"
            )

    @staticmethod
    def _build_inbound_query_command(
        binding: ImBinding,
        content: str,
        source_message_id: str,
        attachments: list[dict[str, Any]] | None,
    ) -> RunQueryCommand:
        attachment_refs = list(attachments or [])
        return RunQueryCommand(
            session_id=binding.session_id,
            prompt=content,
            client_message_id=source_message_id,
            image_paths=[
                str(item.get("path", ""))
                for item in attachment_refs
                if str(item.get("mime_type", "")).startswith("image/")
                and item.get("path")
            ],
            attachments=attachment_refs,
        )

    @staticmethod
    def _extract_response_after(session: Any, message_index: int) -> str:
        """返回该用户消息之后的最终回复文本; 未完成或失败时返回空串."""
        response = ""
        completed = False
        failed = False
        for message in session.messages[message_index + 1:]:
            if message.message_type == MessageType.USER:
                break
            if message.message_type == MessageType.ASSISTANT:
                text = MessageConversionService.assistant_text_of(message)
                if text:
                    response = text
            elif message.message_type == MessageType.RESULT:
                completed = True
                failed = message.content.get("is_error") is True
        if completed and not failed:
            return response
        return ""

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
        event: ImInboxEvent,
        *,
        is_final_attempt: bool = False,
    ) -> None:
        await self._process_inbound(
            binding,
            self._to_inbound_message(binding, event),
            is_final_attempt=is_final_attempt,
        )

    @staticmethod
    def _to_inbound_message(
        binding: ImBinding, event: ImInboxEvent,
    ) -> InboundMessage:
        return InboundMessage(
            channel_id=event.channel_id,
            channel_type=event.channel_type,
            external_message_id=event.external_message_id,
            route=event.route,
            segments=(
                MessageSegment.of_text(event.content),
                *(
                    MessageSegment.from_attachment(item)
                    for item in event.attachments
                ),
            ),
        )

    # ── Channel listener lifecycle ──

    async def start_channel_listener(self, binding: ImBinding) -> None:
        channel_type_val = binding.channel_type.value
        session_id = binding.session_id

        async def on_message(message: InboundMessage) -> None:
            logger.info(
                "[IM-listener] Message received: channel=%s session=%s msg_id=%s",
                channel_type_val, session_id, message.external_message_id,
            )
            if self._accept_inbound is None:
                safe_create_task(self._process_inbound(binding, message))
                return
            await self._persist_inbound_with_retry(binding, message)

        try:
            started = await self._facade.start_listening(binding, on_message)
        except Exception:
            logger.error(
                "[IM-listener] Failed to start listener: channel=%s session=%s",
                channel_type_val, session_id, exc_info=True,
            )
            return
        if started:
            logger.info(
                "[IM-listener] Listener started: channel=%s session=%s",
                channel_type_val, session_id,
            )

    async def _persist_inbound_with_retry(
        self, binding: ImBinding, message: InboundMessage,
    ) -> None:
        """入队失败必须重试到底: 此时消息只存在于内存, 丢了就永远收不到."""
        for attempt in range(5):
            try:
                await self._accept_inbound(binding, message)
                return
            except Exception:
                if attempt == 4:
                    logger.error(
                        "[IM-listener] Failed to persist inbound after retries: "
                        "channel=%s message_id=%s",
                        binding.channel_type.value,
                        message.external_message_id,
                        exc_info=True,
                    )
                    raise
                logger.warning(
                    "[IM-listener] Inbound persistence retry: "
                    "channel=%s message_id=%s attempt=%s",
                    binding.channel_type.value,
                    message.external_message_id,
                    attempt + 1,
                    exc_info=True,
                )
                await asyncio.sleep(min(8, 2 ** attempt))

    # ── Internal ──

    async def _force_unbind(self, binding: ImBinding, *, notify: bool = True) -> None:
        """Unbind adapter, remove persistence, and optionally notify clients.

        Single Point of Truth for the complete unbind operation: adapter call,
        repo removal, and WebSocket broadcast. All three call-sites (delete_channel_instance,
        bind re-bind, unbind) delegate here so the flow is consistent.

        Callers that still have more work to persist pass ``notify=False`` and
        invoke :meth:`_notify_unbound` once their unit of work is complete.
        """
        try:
            await self._facade.stop_listening(binding)
            await self._facade.unbind(binding)
        except Exception:
            logger.warning(
                "Adapter unbind failed for session %s", binding.session_id, exc_info=True,
            )
        await self._binding_repo.remove(binding.session_id)
        if notify:
            await self._notify_unbound(binding)

    async def _notify_unbound(self, binding: ImBinding) -> None:
        """Announce that *binding* is gone, once the removal is durable.

        Clients react to ``im_unbound`` by re-reading the binding state on a
        different DB connection. Broadcasting while the delete is still
        uncommitted hands them the row we just removed, and that stale read
        overwrites the fresh state they already applied.
        """
        if self._connection_manager is None:
            return
        if self._commit_unit_of_work is not None:
            await self._commit_unit_of_work()
        await self._connection_manager.broadcast(
            binding.session_id,
            {"event": "im_unbound", "channel_type": binding.channel_type.value},
        )

    @staticmethod
    def _binding_result_dict(binding: ImBinding, ui_data: Any) -> dict[str, Any]:
        """Build the canonical binding result dict returned by bind() and complete_binding()."""
        return {
            "id": binding.id,
            "session_id": binding.session_id,
            "channel_type": binding.channel_type.value,
            "channel_id": binding.channel_id,
            "binding_status": binding.binding_status.value,
            "channel_address": binding.channel_address,
            "ui_data": ui_data,
        }

    async def _send_bind_notification(self, binding: ImBinding) -> None:
        """绑定成功通知. 与其他出站消息一样走持久化队列, 进程重启不会丢."""
        route = self._facade.restore_route(binding)
        if route.is_empty:
            return
        try:
            await self._dispatch_outbound(
                binding,
                OutboundMessage.of_text(
                    f"已绑定会话: {binding.session_id}",
                    route=route,
                    idempotency_key=f"bind:{binding.id}:{binding.channel_id}",
                ),
            )
        except Exception:
            logger.warning("[IM-bind] Failed to send binding notification", exc_info=True)

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

    async def _persist_route(self, binding: ImBinding, route: ChannelRoute) -> None:
        """把入站路由写回 binding 与 channel_init.

        出站消息通常自带路由, 这里持久化的是"最后一次已知路由", 供绑定通知、
        Web 侧主动推送等没有入站上下文的场景兜底。
        """
        updates = self._facade.persist_route(binding, route)
        if not updates:
            return
        if all(binding.config.get(key) == value for key, value in updates.items()):
            # 同一个人连续发消息时路由不会变, 跳过可以省掉每条消息 2 读 2 写,
            # 也避免多个 inbox worker 争抢同一行 binding。
            return

        binding.update_config(updates)

        if not self._binding_context_factory:
            logger.warning("[IM-process] No binding_context_factory, cannot persist route")
            return

        try:
            async with self._binding_context_factory() as (binding_repo, init_repo):
                fresh = await binding_repo.find_by_session_id(binding.session_id)
                if fresh:
                    fresh.update_config(updates)
                    await binding_repo.save(fresh)

                if binding.channel_id:
                    ci = await init_repo.find_by_id(binding.channel_id)
                    if ci:
                        ci.update_config(updates)
                        await init_repo.save(ci)
        except Exception:
            logger.warning(
                "[IM-process] Failed to persist route for session=%s",
                binding.session_id, exc_info=True,
            )
