"""QQ Open Platform REST API client.

Handles access-token lifecycle and message sending.
Supports per-channel credentials: each (app_id, app_secret) pair
gets its own token cache so multiple QQ bots can coexist.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from domain.message.model.attachment import ensure_within_attachment_limit

logger = logging.getLogger(__name__)

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE = "https://api.sgroup.qq.com"
API_TIMEOUT = 10.0
MEDIA_TIMEOUT = 30.0


def _normalize_media_url(url: str) -> str:
    """补齐 QQ 富媒体链接的协议头 — 下发的链接可能是 ``//host/path`` 或裸 host."""
    candidate = (url or "").strip()
    if not candidate:
        return ""
    if candidate.startswith(("http://", "https://")):
        return candidate
    if candidate.startswith("//"):
        return f"https:{candidate}"
    return f"https://{candidate}"


@dataclass
class _TokenEntry:
    """Cached access token for one set of credentials."""
    access_token: str = ""
    expires_at: float = 0


class QqApiClient:
    """QQ Open Platform REST API client.

    Uses per-channel credentials: each (app_id, app_secret) pair
    gets its own token cache so multiple QQ bots can coexist.
    """

    def __init__(self) -> None:
        # Per-credential token cache: key = app_id
        self._tokens: dict[str, _TokenEntry] = {}
        self._token_lock = asyncio.Lock()

    def has_credentials_for(self, app_id: str, app_secret: str) -> bool:
        """Check if specific credentials are non-empty."""
        return bool(app_id and app_secret)

    # ── Token management ──

    async def ensure_token(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> str:
        """Return a valid access_token, refreshing if needed."""
        if not app_id or not app_secret:
            raise RuntimeError(
                "QQ API credentials not configured (app_id/app_secret missing)"
            )

        entry = self._tokens.get(app_id)
        if entry and entry.access_token and time.time() < entry.expires_at - 60:
            return entry.access_token

        async with self._token_lock:
            entry = self._tokens.get(app_id)
            if entry and entry.access_token and time.time() < entry.expires_at - 60:
                return entry.access_token
            return await self._refresh_token(app_id, app_secret)

    async def _refresh_token(self, app_id: str, app_secret: str) -> str:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(
                TOKEN_URL,
                json={"appId": app_id, "clientSecret": app_secret},
            )
            resp.raise_for_status()
            data = resp.json()

        token = data.get("access_token", "")
        expires_in = int(data.get("expires_in", 7200))
        if not token:
            logger.error("QQ API returned empty access_token, response: %s", data)
            raise RuntimeError(f"QQ API returned empty access_token: {data}")

        self._tokens[app_id] = _TokenEntry(
            access_token=token,
            expires_at=time.time() + expires_in,
        )
        logger.info("QQ access_token refreshed for app_id=%s, expires_in=%d", app_id, expires_in)
        return token

    # ── Gateway URL ──

    async def get_gateway_url(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> str:
        token = await self.ensure_token(app_id, app_secret)
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{API_BASE}/gateway",
                headers={"Authorization": f"QQBot {token}"},
            )
            resp.raise_for_status()
            return resp.json().get("url", "")

    # ── Send messages ──

    async def send_c2c_message(
        self, user_openid: str, content: str, msg_id: str = "",
        app_id: str | None = None, app_secret: str | None = None,
        msg_seq: int | None = None,
    ) -> dict:
        """Send a text reply to a C2C (private) conversation."""
        logger.info(
            "[QQ-API] send_c2c_message: user=%s msg_id=%s content=%.100s",
            user_openid, msg_id, content,
        )
        token = await self.ensure_token(app_id, app_secret)
        body: dict = {"content": content, "msg_type": 0}
        if msg_id:
            body["msg_id"] = msg_id
        if msg_seq is not None:
            body["msg_seq"] = msg_seq
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(
                f"{API_BASE}/v2/users/{user_openid}/messages",
                json=body,
                headers={"Authorization": f"QQBot {token}"},
            )
            logger.info("[QQ-API] send_c2c_message response: status=%d body=%.200s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()

    # ── Rich media download ──

    async def download_attachment(self, url: str) -> bytes:
        """下载入站附件.

        QQ 把富媒体放在自带签名的公开 CDN 链接上, 不需要 bot token; 但下发的
        链接常常省略协议头, 且大小不受我们控制, 所以这里补齐 scheme 并在流式
        读取时守住附件上限。
        """
        resolved = _normalize_media_url(url)
        if not resolved:
            raise ValueError("QQ attachment url is empty")

        chunks: list[bytes] = []
        downloaded = 0
        async with httpx.AsyncClient(
            timeout=MEDIA_TIMEOUT, follow_redirects=True,
        ) as client:
            async with client.stream("GET", resolved) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    downloaded += len(chunk)
                    ensure_within_attachment_limit(downloaded)
                    chunks.append(chunk)
        return b"".join(chunks)

    async def send_group_message(
        self, group_openid: str, content: str, msg_id: str = "",
        app_id: str | None = None, app_secret: str | None = None,
        msg_seq: int | None = None,
    ) -> dict:
        """Send a text reply to a group conversation."""
        logger.info(
            "[QQ-API] send_group_message: group=%s msg_id=%s content=%.100s",
            group_openid, msg_id, content,
        )
        token = await self.ensure_token(app_id, app_secret)
        body: dict = {"content": content, "msg_type": 0}
        if msg_id:
            body["msg_id"] = msg_id
        if msg_seq is not None:
            body["msg_seq"] = msg_seq
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(
                f"{API_BASE}/v2/groups/{group_openid}/messages",
                json=body,
                headers={"Authorization": f"QQBot {token}"},
            )
            logger.info("[QQ-API] send_group_message response: status=%d body=%.200s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()
