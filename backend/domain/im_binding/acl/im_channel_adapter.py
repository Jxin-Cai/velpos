from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.im_binding import ImBinding


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
    """IM 渠道适配器 -- 由 infr 层为每种渠道类型实现"""

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

    @abstractmethod
    async def send_message(
        self, binding: ImBinding, content: str,
        reply_context: dict | None = None,
    ) -> None:
        """向 IM 渠道发送消息. reply_context 携带回复路由信息."""
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

    # -- Message lifecycle (default no-op for prompt-based channels) --

    async def start_listening(
        self,
        binding: ImBinding,
        on_message: Callable[[str, str, str, str], Awaitable[None]] | None = None,
    ) -> None:
        """开始接收消息.

        *on_message* 回调签名: ``(msg_id, content, sender_id, group_id)``
        -- 4 个字符串, 覆盖所有 IM 场景.  Prompt 模式适配器无需实现.
        """

    async def stop_listening(self, binding: ImBinding) -> None:
        """停止接收消息."""

    # -- Routing context --

    def extract_routing_context(
        self, sender_id: str, group_id: str,
    ) -> dict[str, str]:
        """从入站消息提取路由字段, 用于持久化到 binding.config."""
        ctx: dict[str, str] = {}
        if sender_id:
            ctx["last_sender_id"] = sender_id
        if group_id:
            ctx["last_group_id"] = group_id
        return ctx

    def build_reply_context(self, binding: ImBinding) -> dict[str, str] | None:
        """从 binding.config 读取已持久化的路由信息, 构建 reply_context."""
        s = binding.config.get("last_sender_id", "")
        g = binding.config.get("last_group_id", "")
        return {"sender_id": s, "group_id": g} if s or g else None

    def routing_config_keys(self) -> tuple[str, ...]:
        """声明本渠道路由相关的 config key, 换绑时自动继承."""
        return ("last_sender_id", "last_group_id")

    # -- Reactions (optional) --

    async def add_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> None:
        """添加表情."""

    async def remove_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> None:
        """移除表情."""
