"""Lark/Feishu Open API client — direct HTTP calls, no lark-cli dependency.

Covers:
- App Registration device flow (QR code binding)
- Tenant access token management (auto-refresh)
- IM message send / reply
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# ── Brand endpoints (mirrors cli/internal/core/types.go) ──

BRAND_ENDPOINTS = {
    "feishu": {
        "open": "https://open.feishu.cn",
        "accounts": "https://accounts.feishu.cn",
    },
    "lark": {
        "open": "https://open.larksuite.com",
        "accounts": "https://accounts.larksuite.com",
    },
}


def _ep(brand: str, kind: str) -> str:
    return BRAND_ENDPOINTS.get(brand, BRAND_ENDPOINTS["feishu"])[kind]


class LarkApiClient:
    """Async HTTP client for Feishu/Lark Open API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout
        # Tenant token cache: {app_id: (token, expire_ts)}
        self._token_cache: dict[str, tuple[str, float]] = {}
        self._token_lock = asyncio.Lock()

    # ── App Registration (Device Flow) ──────────────────────────

    async def app_registration_begin(self, brand: str = "feishu") -> dict:
        """Start app registration device flow.

        Always uses feishu accounts endpoint for begin (matches cli behavior).
        Returns: device_code, user_code, verification_uri, expires_in, interval.
        """
        # Registration begin always hits feishu endpoint (cli/internal/auth/app_registration.go:49)
        endpoint = _ep("feishu", "accounts") + "/oauth/v1/app/registration"
        form = {
            "action": "begin",
            "archetype": "PersonalAgent",
            "auth_method": "client_secret",
            "request_user_info": "open_id tenant_brand",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                endpoint,
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            desc = data.get("error_description") or data.get("error", "Unknown error")
            raise LarkApiError(f"App registration begin failed: {desc}")

        user_code = data.get("user_code", "")
        open_base = _ep(brand, "open")
        verification_url = f"{open_base}/page/cli?user_code={user_code}"

        return {
            "device_code": data.get("device_code", ""),
            "user_code": user_code,
            "verification_uri": data.get("verification_uri", ""),
            "verification_url": verification_url,
            "expires_in": data.get("expires_in", 300),
            "interval": data.get("interval", 5),
        }

    async def app_registration_poll(
        self, device_code: str, brand: str = "feishu",
    ) -> dict:
        """Poll app registration status.

        Returns on success: client_id, client_secret, tenant_brand.
        Returns on pending: {"status": "authorization_pending"}.
        """
        endpoint = _ep(brand, "accounts") + "/oauth/v1/app/registration"
        form = {
            "action": "poll",
            "device_code": device_code,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                endpoint,
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            data = resp.json()

        err = data.get("error", "")

        # Success: client_id present
        if not err and data.get("client_id"):
            result = {
                "status": "ok",
                "client_id": data["client_id"],
                "client_secret": data.get("client_secret", ""),
            }
            user_info = data.get("user_info")
            if isinstance(user_info, dict):
                result["tenant_brand"] = user_info.get("tenant_brand", brand)
                result["open_id"] = user_info.get("open_id", "")
            return result

        if err == "authorization_pending":
            return {"status": "authorization_pending"}
        if err == "slow_down":
            return {"status": "slow_down"}
        if err in ("access_denied",):
            raise LarkApiError("App registration denied by user")
        if err in ("expired_token", "invalid_grant"):
            raise LarkApiError("Device code expired, please try again")

        desc = data.get("error_description") or err or "Unknown error"
        raise LarkApiError(f"App registration poll failed: {desc}")

    # ── Tenant Access Token ─────────────────────────────────────

    async def get_tenant_token(
        self, app_id: str, app_secret: str, brand: str = "feishu",
    ) -> str:
        """Get tenant access token (cached, auto-refresh before expiry)."""
        # Check cache without lock first (fast path)
        cached = self._token_cache.get(app_id)
        if cached:
            token, expire_ts = cached
            if time.time() < expire_ts - 300:  # 5 min buffer
                return token

        async with self._token_lock:
            # Double-check after acquiring lock
            cached = self._token_cache.get(app_id)
            if cached:
                token, expire_ts = cached
                if time.time() < expire_ts - 300:
                    return token

            endpoint = _ep(brand, "open") + "/open-apis/auth/v3/tenant_access_token/internal"
            body = {"app_id": app_id, "app_secret": app_secret}

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json=body)
                data = resp.json()

            if data.get("code") != 0:
                msg = data.get("msg", "Unknown error")
                raise LarkApiError(f"Failed to get tenant token: {msg}")

            token = data["tenant_access_token"]
            expire = data.get("expire", 7200)
            self._token_cache[app_id] = (token, time.time() + expire)
            return token

    # ── Messaging ───────────────────────────────────────────────

    async def send_message(
        self,
        token: str,
        receive_id: str,
        content: str,
        msg_type: str = "text",
        receive_id_type: str = "chat_id",
        brand: str = "feishu",
    ) -> dict:
        """Send a message to a chat or user.

        For text messages, content should be the raw text (will be JSON-wrapped).
        *receive_id_type* can be ``"chat_id"`` (default) or ``"open_id"``.
        """
        endpoint = (
            _ep(brand, "open")
            + f"/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
        )
        if msg_type == "text":
            content_body = json.dumps({"text": content})
        else:
            content_body = content

        body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content_body,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                endpoint,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()

        if data.get("code") != 0:
            msg = data.get("msg", "Unknown error")
            logger.warning("[Lark-api] send_message failed: %s", msg)
            raise LarkApiError(f"Send message failed: {msg}")

        return data.get("data", {})

    async def reply_message(
        self,
        token: str,
        message_id: str,
        content: str,
        msg_type: str = "text",
        brand: str = "feishu",
    ) -> dict:
        """Reply to a specific message."""
        endpoint = (
            _ep(brand, "open")
            + f"/open-apis/im/v1/messages/{message_id}/reply"
        )
        if msg_type == "text":
            content_body = json.dumps({"text": content})
        else:
            content_body = content

        body = {
            "msg_type": msg_type,
            "content": content_body,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                endpoint,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()

        if data.get("code") != 0:
            msg = data.get("msg", "Unknown error")
            logger.warning("[Lark-api] reply_message failed: %s", msg)
            raise LarkApiError(f"Reply message failed: {msg}")

        return data.get("data", {})

    async def add_reaction(
        self,
        token: str,
        message_id: str,
        reaction_type: str,
        brand: str = "feishu",
    ) -> str:
        """Add an emoji reaction to a message. Returns reaction_id."""
        endpoint = (
            _ep(brand, "open")
            + f"/open-apis/im/v1/messages/{message_id}/reactions"
        )
        body = {"reaction_type": {"emoji_type": reaction_type}}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                endpoint,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()

        if data.get("code") != 0:
            msg = data.get("msg", "Unknown error")
            logger.warning("[Lark-api] add_reaction failed: %s", msg)
            raise LarkApiError(f"Add reaction failed: {msg}")

        return data.get("data", {}).get("reaction_id", "")

    async def delete_reaction(
        self,
        token: str,
        message_id: str,
        reaction_id: str,
        brand: str = "feishu",
    ) -> None:
        """Remove an emoji reaction from a message."""
        endpoint = (
            _ep(brand, "open")
            + f"/open-apis/im/v1/messages/{message_id}/reactions/{reaction_id}"
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.delete(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()

        if data.get("code") != 0:
            msg = data.get("msg", "Unknown error")
            logger.warning("[Lark-api] delete_reaction failed: %s", msg)
            raise LarkApiError(f"Delete reaction failed: {msg}")


class LarkApiError(Exception):
    pass
