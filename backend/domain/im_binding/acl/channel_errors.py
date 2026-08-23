from __future__ import annotations


class ChannelError(RuntimeError):
    """IM 渠道操作失败的基类.

    适配器应把平台原生异常翻译成这三类之一, 门面据此决定重试、进死信,
    还是把绑定标记为需要重新授权。未翻译的异常一律按瞬时故障处理, 以免
    因为漏翻译就把消息直接丢进死信。
    """

    def __init__(self, message: str, *, channel_type: str = "", detail: str = "") -> None:
        super().__init__(message)
        self.channel_type = channel_type
        self.detail = detail


class ChannelTransientError(ChannelError):
    """瞬时故障 — 网络抖动、限流、平台 5xx. 应当重试."""


class ChannelPermanentError(ChannelError):
    """永久故障 — 消息体非法、目标不存在、渠道拒收. 重试无意义, 进死信."""


class ChannelAuthError(ChannelError):
    """凭证失效 — 需要用户重新扫码授权. 绑定应被标记为降级状态."""


class ChannelRoutingError(ChannelPermanentError):
    """路由信息缺失 — 拿不到发送目标.

    单独成类是因为它可以被用户侧动作修复（从 IM 侧发一条消息即可重建路由）,
    值得给出比通用永久故障更明确的提示。
    """
