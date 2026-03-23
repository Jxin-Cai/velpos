from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator
from uuid import uuid4

import websockets
from websockets.asyncio.client import ClientConnection

from domain.im_binding.acl.im_ws_gateway import ImWsGateway
from domain.shared.business_exception import BusinessException
from infr.config.im_config import ImConfig

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10
_RECONNECT_BASE_DELAY = 1.0
_RECONNECT_MAX_DELAY = 30.0
_RECONNECT_MAX_ATTEMPTS = 10
_WS_PUSH_MSG_IDENTIFIER = 2001
_PLATFORM_ID = 5


class ImWsClient(ImWsGateway):

    def __init__(self, config: ImConfig) -> None:
        self._config = config
        self._connections: dict[str, ClientConnection] = {}
        self._message_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}
        self._listen_tasks: dict[str, asyncio.Task[None]] = {}
        self._should_reconnect: dict[str, bool] = {}
        self._tokens: dict[str, str] = {}

    def _build_ws_url(self, im_user_id: str, im_token: str) -> str:
        operation_id = str(uuid4())
        return (
            f"{self._config.ws_addr}"
            f"/?sendID={im_user_id}"
            f"&token={im_token}"
            f"&platformID={_PLATFORM_ID}"
            f"&operationID={operation_id}"
        )

    async def connect(self, im_user_id: str, im_token: str) -> None:
        if self.is_connected(im_user_id):
            return

        url = self._build_ws_url(im_user_id, im_token)
        try:
            ws = await asyncio.wait_for(
                websockets.connect(url),
                timeout=_CONNECT_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
            logger.error(
                "IM WS connect failed: im_user_id=%s, error=%s",
                im_user_id,
                exc,
            )
            raise BusinessException(
                f"IM WebSocket connection failed: {exc}",
                code="IM_WS_CONNECT_FAILED",
            ) from exc

        self._connections[im_user_id] = ws
        self._tokens[im_user_id] = im_token
        self._message_queues[im_user_id] = asyncio.Queue()
        self._should_reconnect[im_user_id] = True

        task = asyncio.create_task(self._listen_loop(im_user_id))
        self._listen_tasks[im_user_id] = task
        logger.info("IM WS connected: im_user_id=%s", im_user_id)

    async def disconnect(self, im_user_id: str) -> None:
        if im_user_id not in self._connections and im_user_id not in self._listen_tasks:
            return

        self._should_reconnect[im_user_id] = False

        task = self._listen_tasks.pop(im_user_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        ws = self._connections.pop(im_user_id, None)
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

        queue = self._message_queues.get(im_user_id)
        if queue is not None:
            await queue.put(None)

        self._message_queues.pop(im_user_id, None)
        self._tokens.pop(im_user_id, None)
        self._should_reconnect.pop(im_user_id, None)

        logger.info("IM WS disconnected: im_user_id=%s", im_user_id)

    def is_connected(self, im_user_id: str) -> bool:
        ws = self._connections.get(im_user_id)
        if ws is None:
            return False
        try:
            return ws.protocol.state.name == "OPEN"
        except AttributeError:
            return False

    async def listen_messages(
        self, im_user_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        queue = self._message_queues.get(im_user_id)
        if queue is None:
            raise BusinessException(
                "No active IM WS connection for the user",
                code="IM_WS_NOT_CONNECTED",
            )

        while True:
            msg = await queue.get()
            if msg is None:
                break
            yield msg

    async def _listen_loop(self, im_user_id: str) -> None:
        while True:
            ws = self._connections.get(im_user_id)
            if ws is None:
                break

            try:
                async for raw in ws:
                    self._handle_raw_message(im_user_id, raw)
            except websockets.ConnectionClosed:
                logger.warning(
                    "IM WS connection closed: im_user_id=%s", im_user_id
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception(
                    "IM WS unexpected error in listen loop: im_user_id=%s",
                    im_user_id,
                )

            if not self._should_reconnect.get(im_user_id, False):
                break

            reconnected = await self._reconnect(im_user_id)
            if not reconnected:
                break

        queue = self._message_queues.get(im_user_id)
        if queue is not None:
            await queue.put(None)

    def _handle_raw_message(
        self, im_user_id: str, raw: str | bytes
    ) -> None:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        req_identifier = data.get("reqIdentifier")
        if req_identifier != _WS_PUSH_MSG_IDENTIFIER:
            return

        msg_data = data.get("data", {})
        if isinstance(msg_data, str):
            try:
                msg_data = json.loads(msg_data)
            except (json.JSONDecodeError, TypeError):
                return

        sender_id = msg_data.get("sendID", "")
        send_time = msg_data.get("sendTime", 0)
        raw_content = msg_data.get("content", "")

        content = raw_content
        if isinstance(raw_content, str):
            try:
                content_obj = json.loads(raw_content)
                if isinstance(content_obj, dict) and "content" in content_obj:
                    content = content_obj["content"]
            except (json.JSONDecodeError, TypeError):
                pass

        parsed: dict[str, Any] = {
            "sender_id": sender_id,
            "content": content,
            "send_time": send_time,
        }

        queue = self._message_queues.get(im_user_id)
        if queue is not None:
            try:
                queue.put_nowait(parsed)
            except asyncio.QueueFull:
                logger.warning(
                    "IM WS message queue full, dropping message: im_user_id=%s",
                    im_user_id,
                )

    async def _reconnect(self, im_user_id: str) -> bool:
        token = self._tokens.get(im_user_id)
        if token is None:
            return False

        delay = _RECONNECT_BASE_DELAY
        for attempt in range(1, _RECONNECT_MAX_ATTEMPTS + 1):
            if not self._should_reconnect.get(im_user_id, False):
                return False

            logger.warning(
                "IM WS reconnecting: im_user_id=%s, attempt=%d, delay=%.1fs",
                im_user_id,
                attempt,
                delay,
            )
            await asyncio.sleep(delay)

            url = self._build_ws_url(im_user_id, token)
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(url),
                    timeout=_CONNECT_TIMEOUT,
                )
                self._connections[im_user_id] = ws
                logger.info(
                    "IM WS reconnected: im_user_id=%s, attempt=%d",
                    im_user_id,
                    attempt,
                )
                return True
            except (
                OSError,
                asyncio.TimeoutError,
                websockets.WebSocketException,
            ):
                delay = min(delay * 2, _RECONNECT_MAX_DELAY)

        logger.error(
            "IM WS reconnect failed after %d attempts: im_user_id=%s",
            _RECONNECT_MAX_ATTEMPTS,
            im_user_id,
        )
        return False

    async def close_all(self) -> None:
        user_ids = list(self._connections.keys())
        for im_user_id in user_ids:
            await self.disconnect(im_user_id)
        logger.info("IM WS all connections closed")
