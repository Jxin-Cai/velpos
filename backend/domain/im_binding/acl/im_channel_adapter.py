from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    InboundMessage,
    OutboundMessage,
    SendReceipt,
)

#: 入站消息回调. 适配器把平台私有格式翻译成 InboundMessage 后调用.
InboundHandler = Callable[[InboundMessage], Awaitable[None]]

_LAST_SENDER_KEY = "last_sender_id"
_LAST_GROUP_KEY = "last_group_id"
_EXTRA_KEY_PREFIX = "last_route_"


@dataclass
class BindResult:
    """渠道适配器绑定操作的返回结果"""
    status: BindingStatus
    channel_address: str = ""
    config: dict = field(default_factory=dict)
    ui_data: dict = field(default_factory=dict)


@dataclass
class InitResult:
    """渠道初始化操作的返回结果"""
    status: ChannelInitStatus
    config: dict = field(default_factory=dict)
    error_message: str = ""
    ui_data: dict = field(default_factory=dict)


class ImChannelAdapter(ABC):
    """IM 渠道适配器 — 由 infr 层为每种渠道类型实现.

    适配器只提供渠道原语, 不做能力判断: 是否调用某个原语由
    :class:`~application.im_binding.im_channel_facade.ImChannelFacade`
    依据 ``ImChannelSpec.capabilities`` 决定。因此渠道不支持的能力保留
    基类的空实现即可, 无需抛异常。

    适配器应把平台异常翻译成 :mod:`domain.im_binding.acl.channel_errors`
    中的类型, 否则门面只能按瞬时故障重试。
    """

    # -- Binding lifecycle --

    @abstractmethod
    async def bind(
        self, session_id: str, binding: ImBinding, params: dict,
    ) -> BindResult:
        """发起绑定流程."""
        ...

    @abstractmethod
    async def complete_bind(
        self, binding: ImBinding, params: dict,
    ) -> BindResult:
        """完成多步骤绑定."""
        ...

    @abstractmethod
    async def unbind(self, binding: ImBinding) -> None:
        """解除绑定, 清理渠道侧资源."""
        ...

    # -- Channel initialization --

    @abstractmethod
    async def check_init_status(self, config: dict) -> bool:
        """检查已存储的凭证/配置是否仍然有效. 返回 True 表示渠道可用."""
        ...

    @abstractmethod
    async def initialize(self, params: dict) -> InitResult:
        """启动或推进初始化流程. 返回 InitResult."""
        ...

    # -- Outbound --

    @abstractmethod
    async def send(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> SendReceipt:
        """发送一条消息.

        传入的 *message* 已由门面按渠道能力裁剪, 只包含本渠道支持的片段,
        且 ``route`` 已补齐兜底路由。实现方必须在渠道返回业务错误时抛出
        对应的 :class:`ChannelError`, 不得把失败当成功返回。
        """
        ...

    # -- Inbound (默认空实现: 无监听能力的渠道无需覆写) --

    async def start_listening(
        self, binding: ImBinding, on_message: InboundHandler | None = None,
    ) -> None:
        """开始接收消息."""

    async def stop_listening(self, binding: ImBinding) -> None:
        """停止接收消息."""

    # -- Progress feedback (默认空实现) --

    async def add_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> str:
        """添加表情并返回可用于移除的标识."""
        return ""

    async def remove_reaction(
        self, binding: ImBinding, message_id: str, reaction_id: str,
    ) -> None:
        """移除表情."""

    async def start_typing(self, binding: ImBinding, route: ChannelRoute) -> str:
        """展示"正在输入", 返回可用于停止的票据."""
        return ""

    async def stop_typing(self, binding: ImBinding, ticket: str) -> None:
        """停止"正在输入"."""

    # -- Routing --

    def route_extra_keys(self) -> tuple[str, ...]:
        """声明本渠道路由所需的私有字段名, 如微信的 ``context_token``.

        这些字段会随入站事件与出站消息一起持久化, 并在换绑时自动继承。
        """
        return ()

    def restore_route(self, binding: ImBinding) -> ChannelRoute:
        """从 ``binding.config`` 兜底重建路由.

        仅在入站事件未携带路由时使用（如绑定通知、Web 侧主动推送）。
        """
        extras = {
            key: str(binding.config.get(f"{_EXTRA_KEY_PREFIX}{key}", ""))
            for key in self.route_extra_keys()
        }
        return ChannelRoute(
            sender_id=str(binding.config.get(_LAST_SENDER_KEY, "")),
            group_id=str(binding.config.get(_LAST_GROUP_KEY, "")),
            extras={k: v for k, v in extras.items() if v},
        )

    def persist_route(self, route: ChannelRoute) -> dict[str, str]:
        """把路由折叠成要写回 ``binding.config`` 的键值对."""
        updates: dict[str, str] = {}
        if route.sender_id:
            updates[_LAST_SENDER_KEY] = route.sender_id
        if route.group_id:
            updates[_LAST_GROUP_KEY] = route.group_id
        for key in self.route_extra_keys():
            value = route.extras.get(key, "")
            if value:
                updates[f"{_EXTRA_KEY_PREFIX}{key}"] = value
        return updates

    def route_config_keys(self) -> tuple[str, ...]:
        """换绑时需要继承的 config key 全集."""
        return (_LAST_SENDER_KEY, _LAST_GROUP_KEY) + tuple(
            f"{_EXTRA_KEY_PREFIX}{key}" for key in self.route_extra_keys()
        )

    # -- Shutdown --

    async def close(self) -> None:
        """释放适配器持有的长连接与后台任务."""
