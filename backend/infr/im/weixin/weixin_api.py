"""WeChat (iLink) HTTP API client.

Ported from Claude-to-IM-skill/src/adapters/weixin/weixin-api.ts.
"""

from __future__ import annotations

import logging
import secrets
from base64 import b64encode
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "velpos-weixin/1.0"
API_TIMEOUT = 15.0
LONG_POLL_TIMEOUT = 40.0


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
            resp = await client.get(url)
            logger.info("[WeChat-API] poll response: status=%d body=%.200s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()

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
    ) -> dict[str, Any]:
        """POST /ilink/bot/sendmessage — send text message."""
        client_id = f"vp-weixin-{secrets.token_hex(4)}"
        return await self._post(
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

    async def send_typing(
        self,
        bot_token: str,
        ilink_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> None:
        """POST /ilink/bot/sendtyping — send typing indicator."""
        try:
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
        except Exception:
            pass  # typing is best-effort

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
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text:
                return {}
            return resp.json()
