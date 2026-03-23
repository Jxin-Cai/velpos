"""QQ Open Platform REST API client.

Handles access-token lifecycle and message sending.
Supports per-channel credentials: each (app_id, app_secret) pair
gets its own token cache so multiple QQ bots can coexist.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE = "https://api.sgroup.qq.com"
API_TIMEOUT = 10.0


@dataclass
class _TokenEntry:
    """Cached access token for one set of credentials."""
    access_token: str = ""
    expires_at: float = 0


class QqApiClient:
    """QQ Open Platform REST API client.

    Supports two modes:
    1. Legacy global credentials via ``set_credentials`` (for ``initialize``/
       ``check_init_status`` which validate a single credential pair).
    2. Per-channel credentials via explicit ``app_id``/``app_secret`` parameters
       on ``ensure_token``, ``get_gateway_url``, ``send_*`` methods.
    """

    def __init__(self) -> None:
        # Legacy global credentials (used by adapter init/bind)
        self._app_id = ""
        self._app_secret = ""
        # Per-credential token cache: key = app_id
        self._tokens: dict[str, _TokenEntry] = {}

    def set_credentials(self, app_id: str, app_secret: str) -> None:
        """Set global fallback credentials (legacy interface)."""
        self._app_id = app_id
        self._app_secret = app_secret

    @property
    def has_credentials(self) -> bool:
        return bool(self._app_id and self._app_secret)

    def has_credentials_for(self, app_id: str, app_secret: str) -> bool:
        """Check if specific credentials are non-empty."""
        return bool(app_id and app_secret)

    # ── Token management ──

    async def ensure_token(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> str:
        """Return a valid access_token, refreshing if needed.

        If *app_id*/*app_secret* are given they are used directly;
        otherwise falls back to the global credentials set via
        ``set_credentials``.
        """
        aid = app_id or self._app_id
        asec = app_secret or self._app_secret
        if not aid or not asec:
            raise RuntimeError(
                "QQ API credentials not configured (app_id/app_secret missing)"
            )

        entry = self._tokens.get(aid)
        if entry and entry.access_token and time.time() < entry.expires_at - 60:
            return entry.access_token

        return await self._refresh_token(aid, asec)

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
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(
                f"{API_BASE}/v2/users/{user_openid}/messages",
                json=body,
                headers={"Authorization": f"QQBot {token}"},
            )
            logger.info("[QQ-API] send_c2c_message response: status=%d body=%.200s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()

    async def send_group_message(
        self, group_openid: str, content: str, msg_id: str = "",
        app_id: str | None = None, app_secret: str | None = None,
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
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(
                f"{API_BASE}/v2/groups/{group_openid}/messages",
                json=body,
                headers={"Authorization": f"QQBot {token}"},
            )
            logger.info("[QQ-API] send_group_message response: status=%d body=%.200s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()
