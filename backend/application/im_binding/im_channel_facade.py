from __future__ import annotations

import logging

from domain.im_binding.acl.channel_errors import (
    ChannelAuthError,
    ChannelError,
    ChannelRoutingError,
    ChannelTransientError,
)
from domain.im_binding.acl.im_channel_adapter import (
    BindResult,
    ImChannelAdapter,
    InboundHandler,
    InitResult,
)
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_registry import ImChannelRegistry
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_spec import ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    MessageSegment,
    OutboundMessage,
    SegmentType,
    SendReceipt,
)

logger = logging.getLogger(__name__)

_MEDIA_PLACEHOLDER_LABEL = {
    SegmentType.IMAGE: "图片",
    SegmentType.AUDIO: "音频",
    SegmentType.VIDEO: "视频",
    SegmentType.FILE: "文件",
}


class ImChannelFacade:
    """IM 渠道统一门面 — 编排层与渠道之间的唯一通道.

    职责边界:

    - **能力路由**: 渠道未声明的能力直接安全降级, 不进适配器
    - **内容裁剪**: 按能力过滤消息片段, 不支持的媒体降级成文本占位
    - **结果校验**: 声明会回传消息标识的渠道必须真的回传, 否则判定投递失败
    - **错误归一**: 把渠道异常收敛成瞬时/永久/凭证失效三类
    - **路由兜底**: 出站消息缺路由时用 binding.config 中持久化的路由补齐

    编排层因此不需要知道任何渠道的名字。
    """

    def __init__(self, registry: ImChannelRegistry) -> None:
        self._registry = registry

    # ── 能力查询 ──

    def spec(self, channel_type: ImChannelType) -> ImChannelSpec:
        return self._registry.get_spec(channel_type)

    def supports(
        self, channel_type: ImChannelType, capability: ChannelCapability,
    ) -> bool:
        try:
            return self._registry.get_spec(channel_type).supports(capability)
        except ValueError:
            return False

    def adapter(self, channel_type: ImChannelType) -> ImChannelAdapter:
        return self._registry.get_adapter_factory(channel_type)()

    # ── 绑定生命周期 ──

    async def bind(
        self, session_id: str, binding: ImBinding, params: dict,
    ) -> BindResult:
        return await self.adapter(binding.channel_type).bind(
            session_id, binding, params,
        )

    async def complete_bind(self, binding: ImBinding, params: dict) -> BindResult:
        return await self.adapter(binding.channel_type).complete_bind(binding, params)

    async def unbind(self, binding: ImBinding) -> None:
        await self.adapter(binding.channel_type).unbind(binding)

    async def initialize(
        self, channel_type: ImChannelType, params: dict,
    ) -> InitResult:
        return await self.adapter(channel_type).initialize(params)

    async def check_init_status(
        self, channel_type: ImChannelType, config: dict,
    ) -> bool:
        return await self.adapter(channel_type).check_init_status(config)

    # ── 监听 ──

    async def start_listening(
        self, binding: ImBinding, on_message: InboundHandler,
    ) -> bool:
        """启动入站监听. 渠道不支持监听时返回 False 且不做任何事."""
        if not self.supports(binding.channel_type, ChannelCapability.INBOUND_LISTEN):
            return False
        await self.adapter(binding.channel_type).start_listening(binding, on_message)
        return True

    async def stop_listening(self, binding: ImBinding) -> None:
        if not self.supports(binding.channel_type, ChannelCapability.INBOUND_LISTEN):
            return
        await self.adapter(binding.channel_type).stop_listening(binding)

    # ── 发送 ──

    async def send(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> SendReceipt:
        """发送消息, 并校验渠道是否真的收下了.

        抛出 :class:`ChannelError` 的某个子类, 调用方据此决定重试或死信。
        """
        adapter = self.adapter(binding.channel_type)
        spec = self.spec(binding.channel_type)

        prepared = self._prepare(spec, adapter, binding, message)
        if prepared.is_empty:
            return SendReceipt.skip("no sendable segment for this channel")

        try:
            receipt = await adapter.send(binding, prepared)
        except ChannelError:
            raise
        except Exception as exc:
            # 未翻译的异常按瞬时故障处理, 宁可重试也不要误判成死信.
            raise ChannelTransientError(
                f"{spec.display_name} send failed: {exc}",
                channel_type=spec.channel_type.value,
                detail=repr(exc),
            ) from exc

        return self._validate_receipt(spec, binding, receipt)

    def _prepare(
        self,
        spec: ImChannelSpec,
        adapter: ImChannelAdapter,
        binding: ImBinding,
        message: OutboundMessage,
    ) -> OutboundMessage:
        # 以持久化的"最后已知路由"打底, 消息自带的字段逐个覆盖上去.
        route = adapter.restore_route(binding).merge(message.route)
        if not spec.supports(ChannelCapability.THREAD_REPLY):
            route = route.with_reply_to("")
        return message.with_route(route).with_segments(
            self._degrade_segments(spec, message.segments),
        )

    @staticmethod
    def _degrade_segments(
        spec: ImChannelSpec, segments: tuple[MessageSegment, ...],
    ) -> tuple[MessageSegment, ...]:
        """把渠道不支持的片段降级, 而不是静默丢弃内容."""
        result: list[MessageSegment] = []
        for segment in segments:
            if spec.supports(segment.required_capability):
                result.append(segment)
                continue
            placeholder = _placeholder_text(segment)
            if placeholder and spec.supports(ChannelCapability.OUTBOUND_TEXT):
                result.append(MessageSegment.of_text(placeholder))
        return tuple(result)

    @staticmethod
    def _validate_receipt(
        spec: ImChannelSpec, binding: ImBinding, receipt: SendReceipt,
    ) -> SendReceipt:
        if receipt.skipped:
            return receipt
        if (
            not spec.supports(ChannelCapability.MESSAGE_ID_ECHO)
            or receipt.external_message_id
        ):
            return receipt

        # 渠道承诺回传消息标识却没有回传, 这次投递结果不可信.
        if not spec.supports(ChannelCapability.IDEMPOTENCY):
            # 渠道不去重时重试可能发出第二条, 重复打扰比一条状态未知更糟,
            # 因此只记录不重试。
            logger.warning(
                "%s delivery unconfirmed and cannot be safely retried: binding=%s",
                spec.display_name,
                binding.id,
            )
            return receipt
        raise ChannelTransientError(
            f"{spec.display_name} accepted the request without returning "
            "a message id, delivery is unconfirmed",
            channel_type=spec.channel_type.value,
            detail=f"binding={binding.id}",
        )

    # ── 进度反馈原语 ──

    async def add_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> str:
        if not (
            message_id
            and self.supports(binding.channel_type, ChannelCapability.REACTION)
        ):
            return ""
        return await self.adapter(binding.channel_type).add_reaction(
            binding, message_id, reaction,
        )

    async def remove_reaction(
        self, binding: ImBinding, message_id: str, reaction_id: str,
    ) -> None:
        if not (
            reaction_id
            and self.supports(binding.channel_type, ChannelCapability.REACTION)
        ):
            return
        await self.adapter(binding.channel_type).remove_reaction(
            binding, message_id, reaction_id,
        )

    async def start_typing(self, binding: ImBinding, route: ChannelRoute) -> str:
        if not self.supports(
            binding.channel_type, ChannelCapability.TYPING_INDICATOR,
        ):
            return ""
        return await self.adapter(binding.channel_type).start_typing(binding, route)

    async def stop_typing(self, binding: ImBinding, ticket: str) -> None:
        if not (
            ticket
            and self.supports(
                binding.channel_type, ChannelCapability.TYPING_INDICATOR,
            )
        ):
            return
        await self.adapter(binding.channel_type).stop_typing(binding, ticket)

    # ── 路由 ──

    def restore_route(self, binding: ImBinding) -> ChannelRoute:
        return self.adapter(binding.channel_type).restore_route(binding)

    def persist_route(
        self, binding: ImBinding, route: ChannelRoute,
    ) -> dict[str, str]:
        return self.adapter(binding.channel_type).persist_route(route)

    def route_config_keys(self, channel_type: ImChannelType) -> tuple[str, ...]:
        return self.adapter(channel_type).route_config_keys()

    # ── 停机 ──

    async def close_all(self) -> None:
        """关闭所有已注册渠道的长连接与后台任务.

        新增渠道无需改动停机流程: 适配器自己在 ``close`` 里释放资源。
        """
        for channel_type in self._registry.registered_types:
            try:
                await self.adapter(channel_type).close()
            except Exception:
                logger.error(
                    "Failed to close IM channel adapter: channel=%s",
                    channel_type.value,
                    exc_info=True,
                )


def _placeholder_text(segment: MessageSegment) -> str:
    """为渠道不支持的片段生成文本占位, 避免内容悄无声息地消失."""
    if segment.segment_type is SegmentType.CARD:
        return segment.text
    label = _MEDIA_PLACEHOLDER_LABEL.get(segment.segment_type, "附件")
    name = segment.filename or segment.path.rsplit("/", 1)[-1]
    return f"[{label}: {name}]" if name else f"[{label}]"


__all__ = [
    "ChannelAuthError",
    "ChannelRoutingError",
    "ImChannelFacade",
]
