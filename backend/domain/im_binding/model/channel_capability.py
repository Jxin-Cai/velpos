from __future__ import annotations

import enum


class ChannelCapability(str, enum.Enum):
    """IM 渠道能力枚举 — 以飞书为能力全集的基准.

    渠道在 ``ImChannelSpec.capabilities`` 中声明自己支持的子集。门面据此
    决定是调用适配器原语还是安全降级为空操作，编排层不再判断渠道类型。
    """

    # -- 消息收发 --
    INBOUND_LISTEN = "inbound_listen"
    """能够主动接收消息 (长连接 / 长轮询 / webhook)."""

    OUTBOUND_TEXT = "outbound_text"
    """能够发送纯文本消息. 所有可用渠道都应具备."""

    INBOUND_ATTACHMENT = "inbound_attachment"
    """入站消息能够携带已下载落盘的附件."""

    OUTBOUND_ATTACHMENT = "outbound_attachment"
    """能够上传并发送图片 / 文件 / 音视频."""

    RICH_CARD = "rich_card"
    """能够发送富文本或交互式卡片."""

    CARD_CALLBACK = "card_callback"
    """能够接收卡片按钮回调事件."""

    # -- 路由 --
    THREAD_REPLY = "thread_reply"
    """能够针对特定消息发起线程内回复."""

    GROUP_CHAT = "group_chat"
    """能够在群聊中收发消息, 而不仅是单聊."""

    # -- 进度反馈 --
    REACTION = "reaction"
    """能够对消息添加 / 移除表情回应."""

    TYPING_INDICATOR = "typing_indicator"
    """能够展示"正在输入"状态."""

    PROGRESS_ACK = "progress_ack"
    """渠道无原生进度提示, 需要用文本消息回报任务进度."""

    # -- 投递保障 --
    IDEMPOTENCY = "idempotency"
    """发送接口支持幂等键, 网络超时重试不会重复投递."""

    MESSAGE_ID_ECHO = "message_id_echo"
    """发送成功后会返回渠道侧消息标识, 可用于校验投递结果."""


#: 飞书具备的能力全集, 作为其余渠道的对齐基准.
FULL_CAPABILITIES: frozenset[ChannelCapability] = frozenset(ChannelCapability)
