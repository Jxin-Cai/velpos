from __future__ import annotations

import json
import logging
from uuid import uuid4

import httpx

from domain.im_binding.acl.im_gateway import ImGateway
from domain.shared.business_exception import BusinessException
from infr.config.im_config import ImConfig

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)

_TOKEN_ERROR_KEYWORDS = ("token", "expired", "invalid token", "not authorized")


class ImApiGateway(ImGateway):

    def __init__(self, config: ImConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._admin_token: str | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def _ensure_admin_token(self) -> str:
        if self._admin_token:
            return self._admin_token

        client = self._ensure_client()
        url = f"{self._config.api_addr}/auth/get_admin_token"
        operation_id = str(uuid4())
        payload = {
            "secret": self._config.admin_secret,
            "userID": self._config.admin_user_id,
        }
        headers = {"operationID": operation_id}

        try:
            resp = await client.post(url, json=payload, headers=headers)
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("IM admin token request failed: %s", exc)
            raise BusinessException(
                "Failed to obtain IM admin token", code="IM_AUTH_FAILED"
            ) from exc

        if data.get("errCode") != 0:
            detail = data.get("errMsg", "unknown error")
            logger.error("IM admin token error: %s", detail)
            raise BusinessException(
                f"Failed to obtain IM admin token: {detail}",
                code="IM_AUTH_FAILED",
            )

        self._admin_token = data["data"]["token"]
        logger.info("IM admin token acquired")
        return self._admin_token

    async def _post(
        self,
        path: str,
        payload: dict,
        error_code: str,
        error_prefix: str,
    ) -> dict:
        client = self._ensure_client()
        url = f"{self._config.api_addr}{path}"

        for attempt in range(2):
            token = await self._ensure_admin_token()
            operation_id = str(uuid4())
            headers = {"token": token, "operationID": operation_id}

            try:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.error("IM API request failed: path=%s, error=%s", path, exc)
                raise BusinessException(
                    f"{error_prefix}: network error", code=error_code
                ) from exc

            err_code = data.get("errCode", -1)
            if err_code == 0:
                return data

            err_msg = data.get("errMsg", "")
            if (
                attempt == 0
                and err_code != 0
                and any(kw in err_msg.lower() for kw in _TOKEN_ERROR_KEYWORDS)
            ):
                logger.warning(
                    "IM token possibly expired, refreshing: path=%s, errMsg=%s",
                    path,
                    err_msg,
                )
                self._admin_token = None
                continue

            logger.error("IM API error: path=%s, errCode=%s, errMsg=%s", path, err_code, err_msg)
            raise BusinessException(
                f"{error_prefix}: {err_msg}", code=error_code
            )

        raise BusinessException(
            f"{error_prefix}: token refresh retry exhausted", code=error_code
        )

    async def register_user(self, im_user_id: str, nickname: str) -> None:
        logger.info("register_user: im_user_id=%s, nickname=%s", im_user_id, nickname)
        await self._post(
            path="/user/user_register",
            payload={"users": [{"userID": im_user_id, "nickname": nickname}]},
            error_code="IM_REGISTER_FAILED",
            error_prefix="IM user registration failed",
        )

    async def get_user_token(self, im_user_id: str) -> str:
        logger.info("get_user_token: im_user_id=%s", im_user_id)
        data = await self._post(
            path="/auth/get_user_token",
            payload={"userID": im_user_id, "platformID": 5},
            error_code="IM_TOKEN_FAILED",
            error_prefix="IM get user token failed",
        )
        return data["data"]["token"]

    async def import_friend(
        self, owner_user_id: str, friend_user_id: str
    ) -> None:
        logger.info(
            "import_friend: owner=%s, friend=%s", owner_user_id, friend_user_id
        )
        await self._post(
            path="/friend/import_friend",
            payload={
                "ownerUserID": owner_user_id,
                "friendUserIDs": [friend_user_id],
            },
            error_code="IM_IMPORT_FRIEND_FAILED",
            error_prefix="IM import friend failed",
        )

    async def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: str,
    ) -> None:
        logger.info(
            "send_message: sender=%s, receiver=%s", sender_id, receiver_id
        )
        await self._post(
            path="/msg/send_msg",
            payload={
                "sendID": sender_id,
                "recvID": receiver_id,
                "senderPlatformID": 5,
                "content": json.dumps({"content": content}),
                "contentType": 101,
                "sessionType": 1,
            },
            error_code="IM_SEND_MESSAGE_FAILED",
            error_prefix="IM send message failed",
        )

    async def generate_add_friend_link(self, im_user_id: str) -> str:
        link = f"{self._config.api_addr}/user/find/{im_user_id}"
        logger.info("generate_add_friend_link: im_user_id=%s, link=%s", im_user_id, link)
        return link

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("IM API client closed")
