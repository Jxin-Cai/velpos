from __future__ import annotations

import enum
from dataclasses import dataclass

from domain.im_binding.model.channel_type import ImChannelType


class BindingMode(str, enum.Enum):
    """绑定交互模式"""
    QR_CODE = "qr_code"
    PROMPT = "prompt"
    WEBHOOK = "webhook"
    OAUTH = "oauth"


@dataclass(frozen=True)
class ImChannelSpec:
    """渠道能力声明 — 由适配器实现注册到 Registry"""
    channel_type: ImChannelType
    display_name: str
    icon: str
    required_plugin: str | None   # None = 始终可用, 无需额外插件
    binding_mode: BindingMode
    init_fields: tuple[str, ...] = ()     # 初始化所需凭证字段, 如 ("app_id", "app_secret")
    init_mode: str = "credentials"         # "credentials" | "qr_login"
    description: str = ""
