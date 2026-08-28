"""WeChat (iLink) HTTP API client.

Ported from Claude-to-IM-skill/src/adapters/weixin/weixin-api.ts.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from base64 import b64encode
from typing import Any

import httpx

from domain.im_binding.acl.channel_errors import (
    ChannelAuthError,
    ChannelPermanentError,
    ChannelTransientError,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "velpos-weixin/1.0"
API_TIMEOUT = 15.0
LONG_POLL_TIMEOUT = 40.0
_CHANNEL = "weixin"

#: iLink 在 HTTP 200 的响应体里回报业务结果. 优先认微信约定的错误码键;
#: ``errcode`` 缺失或为 0 时回退检查 ``ret`` — 协议规范约定 ``ret != 0``
#: 即失败 (官方 openclaw-weixin 插件同时检查两者), 只看 errcode 会把
#: ``{"ret": -14}`` 这类会话过期响应当成功, 轮询静默空转.
_ERROR_CODE_KEYS = ("errcode", "err_code")
_ERROR_MESSAGE_KEYS = ("errmsg", "err_msg", "message", "msg")

#: 会话/token 陈旧 (session timeout) — 官方插件称 stale token.
#: 可先通过 notifystart 重建服务端会话, 仍失败才需要重新扫码.
STALE_TOKEN_ERROR_CODE = -14

#: 判定为凭证失效的业务错误码 — 需要重建会话或重新扫码.
_AUTH_ERROR_CODES = frozenset({STALE_TOKEN_ERROR_CODE, -1000, 40001, 40014, 42001})

#: 限流与系统繁忙 — 退避后重试即可, 不应死信.
_TRANSIENT_ERROR_CODES = frozenset({-1, 45009, 45011})


def _generate_wechat_uin() -> str:
    return b64encode(secrets.token_bytes(4)).decode()


def _build_headers(bot_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {bot_token}",
        "X-WECHAT-UIN": _generate_wechat_uin(),
    }


class WeixinApiClient:

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")

    async def start_login_qr(self) -> dict[str, Any]:
        """GET /ilink/bot/get_bot_qrcode?bot_type=3"""
        url = f"{self._base_url}/ilink/bot/get_bot_qrcode?bot_type=3"
        logger.info("[WeChat-API] start_login_qr: url=%s", url)
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(url)
            logger.info("[WeChat-API] start_login_qr response: status=%d len=%d", resp.status_code, len(resp.text))
            resp.raise_for_status()
            data = resp.json()
            logger.info("[WeChat-API] start_login_qr data keys: %s", list(data.keys()))
            return data

    async def poll_login_qr_status(self, qrcode: str) -> dict[str, Any]:
        """GET /ilink/bot/get_qrcode_status?qrcode=..."""
        from urllib.parse import quote
        url = f"{self._base_url}/ilink/bot/get_qrcode_status?qrcode={quote(qrcode)}"
        logger.info("[WeChat-API] poll_login_qr_status: url=%.100s", url)
        async with httpx.AsyncClient(timeout=LONG_POLL_TIMEOUT) as client:
            resp = await client.get(
                url, headers={"iLink-App-ClientVersion": "1"},
            )
            logger.info("[WeChat-API] poll response: status=%d body=%.200s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()

    async def notify_start(self, bot_token: str) -> dict[str, Any]:
        """POST /ilink/bot/msg/notifystart — 上报客户端上线.

        官方 openclaw-weixin 插件在每次渠道启动时调用, 让 iLink 服务端
        同步该账号的在线状态并重建会话; 也是 -14 (stale token) 后不重新
        扫码即可恢复收发的手段.
        """
        return await self._post(
            bot_token,
            "msg/notifystart",
            {"base_info": {"channel_version": CHANNEL_VERSION}},
        )

    async def notify_stop(self, bot_token: str) -> dict[str, Any]:
        """POST /ilink/bot/msg/notifystop — 上报客户端下线."""
        return await self._post(
            bot_token,
            "msg/notifystop",
            {"base_info": {"channel_version": CHANNEL_VERSION}},
        )

    async def get_updates(
        self, bot_token: str, get_updates_buf: str = "",
    ) -> dict[str, Any]:
        """POST /ilink/bot/getupdates — long-poll for new messages."""
        return await self._post(
            bot_token,
            "getupdates",
            {
                "get_updates_buf": get_updates_buf or "",
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            timeout=LONG_POLL_TIMEOUT,
        )

    async def send_text_message(
        self,
        bot_token: str,
        to_user_id: str,
        text: str,
        context_token: str = "",
        idempotency_key: str = "",
    ) -> str:
        """POST /ilink/bot/sendmessage — 返回渠道侧消息标识.

        拿不到 message_id 视为投递失败并抛出 :class:`ChannelError`。
        """
        client_id = (
            f"vp-{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:48]}"
            if idempotency_key
            else f"vp-weixin-{secrets.token_hex(4)}"
        )
        response = await self._post(
            bot_token,
            "sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                    "context_token": context_token or None,
                },
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )
        message_id = str(
            response.get("message_id") or response.get("msg_id") or ""
        )
        if not message_id:
            # iLink 对被拒绝的消息也会返回 HTTP 200, 只是不带 message_id.
            # 不校验就会把静默丢弃当成投递成功。
            raise ChannelTransientError(
                "WeChat accepted the request without returning a message id",
                channel_type=_CHANNEL,
                detail=f"response_keys={sorted(response)}",
            )
        return message_id

    async def send_typing(
        self,
        bot_token: str,
        ilink_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> None:
        """POST /ilink/bot/sendtyping — send typing indicator."""
        await self._post(
            bot_token,
            "sendtyping",
            {
                "ilink_user_id": ilink_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )

    async def get_config(
        self,
        bot_token: str,
        ilink_user_id: str,
        context_token: str = "",
    ) -> dict[str, Any]:
        """POST /ilink/bot/getconfig"""
        return await self._post(
            bot_token,
            "getconfig",
            {
                "ilink_user_id": ilink_user_id,
                "context_token": context_token,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )

    async def _post(
        self,
        bot_token: str,
        endpoint: str,
        body: dict,
        timeout: float = API_TIMEOUT,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/ilink/bot/{endpoint}"
        headers = _build_headers(bot_token)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ChannelTransientError(
                f"WeChat {endpoint} request failed: {exc}",
                channel_type=_CHANNEL,
                detail=repr(exc),
            ) from exc

        _raise_for_http_status(endpoint, resp)

        text = resp.text.strip()
        if not text:
            return {}
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ChannelTransientError(
                f"WeChat {endpoint} returned a non-JSON body",
                channel_type=_CHANNEL,
                detail=text[:200],
            ) from exc
        if not isinstance(payload, dict):
            return {}
        _raise_for_business_error(endpoint, payload)
        return payload


def _raise_for_http_status(endpoint: str, resp: httpx.Response) -> None:
    status = resp.status_code
    if status < 400:
        return
    detail = resp.text[:200]
    if status in (401, 403):
        raise ChannelAuthError(
            f"WeChat credentials rejected on {endpoint} (HTTP {status})",
            channel_type=_CHANNEL,
            detail=detail,
        )
    if status == 429 or status >= 500:
        raise ChannelTransientError(
            f"WeChat {endpoint} temporarily unavailable (HTTP {status})",
            channel_type=_CHANNEL,
            detail=detail,
        )
    raise ChannelPermanentError(
        f"WeChat rejected {endpoint} (HTTP {status})",
        channel_type=_CHANNEL,
        detail=detail,
    )


def _raise_for_business_error(endpoint: str, payload: dict[str, Any]) -> None:
    """iLink 用 HTTP 200 + 响应体错误码回报业务失败, 必须显式检查."""
    code = next(
        (
            payload[key]
            for key in _ERROR_CODE_KEYS
            if isinstance(payload.get(key), int) and payload[key] != 0
        ),
        0,
    )
    if code == 0 and isinstance(payload.get("ret"), int):
        code = payload["ret"]
    if code == 0:
        return
    message = next(
        (
            str(payload[key])
            for key in _ERROR_MESSAGE_KEYS
            if isinstance(payload.get(key), str) and payload[key]
        ),
        "",
    )
    summary = f"WeChat {endpoint} failed: code={code} message={message or 'n/a'}"
    if code in _AUTH_ERROR_CODES:
        raise ChannelAuthError(summary, channel_type=_CHANNEL, detail=message)
    if code in _TRANSIENT_ERROR_CODES:
        raise ChannelTransientError(summary, channel_type=_CHANNEL, detail=message)
    raise ChannelPermanentError(summary, channel_type=_CHANNEL, detail=message)
