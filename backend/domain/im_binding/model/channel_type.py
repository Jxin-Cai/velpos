from __future__ import annotations

import enum


class ImChannelType(str, enum.Enum):
    OPENIM = "openim"
    LARK = "lark"
    QQ = "qq"
    WEIXIN = "weixin"
