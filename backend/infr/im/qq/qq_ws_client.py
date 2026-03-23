"""QQ Gateway WebSocket client — multi-connection model.

Manages one persistent WebSocket connection *per channel_id* to the QQ
bot gateway.  Handles: identify, heartbeat, dispatch events, and
auto-reconnection — all scoped to individual connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from infr.im.qq.qq_api import QqApiClient

# Transient network errors that are expected during reconnection
_TRANSIENT_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ConnectError,
    httpx.ReadTimeout,
    OSError,
    ConnectionError,
)

logger = logging.getLogger(__name__)

_RECONNECT_BASE_DELAY = 2.0
_RECONNECT_MAX_DELAY = 30.0
_CONNECT_TIMEOUT = 15

# Intents: GROUP_AND_C2C_EVENT (1 << 25)
_INTENTS = 1 << 25

# Gateway opcodes
_OP_DISPATCH = 0
_OP_HEARTBEAT = 1
_OP_IDENTIFY = 2
_OP_RESUME = 6
_OP_RECONNECT = 7
_OP_INVALID_SESSION = 9
_OP_HELLO = 10
_OP_HEARTBEAT_ACK = 11

OnMessageCallback = Callable[
    [str, str, str, str | None],  # msg_id, content, sender_openid, group_openid
    Awaitable[None],
]


@dataclass
class _QqConnection:
    """Per-channel WebSocket connection state."""
    channel_id: str
    session_id: str
    app_id: str = ""
    app_secret: str = ""
    ws: ClientConnection | None = None
    task: asyncio.Task | None = None
    heartbeat_task: asyncio.Task | None = None
    running: bool = False
    sequence: int | None = None
    session_ws_id: str | None = None  # QQ session ID for resume
    on_message: OnMessageCallback | None = None


class QqWsClient:
    """QQ Gateway WebSocket client — supports multiple concurrent channels.

    Each ``channel_id`` gets its own WebSocket connection, heartbeat, and
    message callback, allowing several QQ bot bindings to run in parallel.
    """

    def __init__(self, api_client: QqApiClient) -> None:
        self._api = api_client
        self._connections: dict[str, _QqConnection] = {}

    def is_channel_running(self, channel_id: str) -> bool:
        """Check whether a specific channel's WS connection is running."""
        conn = self._connections.get(channel_id)
        return conn is not None and conn.running

    async def start(
        self,
        channel_id: str,
        session_id: str,
        on_message: OnMessageCallback,
        app_id: str = "",
        app_secret: str = "",
    ) -> None:
        """Start a WebSocket event loop for a specific channel.

        If a connection already exists for this *channel_id* it is stopped
        first, then a fresh connection is created.
        """
        # Stop existing connection for this channel if any
        if channel_id in self._connections:
            logger.info("[QQ-WS] Stopping existing connection for channel=%s before restart", channel_id)
            await self.stop(channel_id)

        conn = _QqConnection(
            channel_id=channel_id,
            session_id=session_id,
            app_id=app_id,
            app_secret=app_secret,
            on_message=on_message,
            running=True,
        )
        self._connections[channel_id] = conn
        conn.task = asyncio.create_task(
            self._run_loop(conn),
            name=f"qq-ws-{channel_id[:8]}",
        )
        logger.info("[QQ-WS] Client started for channel=%s session=%s", channel_id, session_id)

    async def stop(self, channel_id: str) -> None:
        """Stop a specific channel's WebSocket connection and clean up."""
        conn = self._connections.pop(channel_id, None)
        if conn is None:
            return
        await self._stop_connection(conn)
        logger.info("[QQ-WS] Client stopped for channel=%s", channel_id)

    async def stop_all(self) -> None:
        """Stop all active connections — used during shutdown."""
        channel_ids = list(self._connections.keys())
        for cid in channel_ids:
            await self.stop(cid)
        logger.info("[QQ-WS] All connections stopped (%d)", len(channel_ids))

    # ── Internal helpers ──

    async def _stop_connection(self, conn: _QqConnection) -> None:
        """Cleanly stop a single connection."""
        conn.running = False
        if conn.heartbeat_task and not conn.heartbeat_task.done():
            conn.heartbeat_task.cancel()
        if conn.ws:
            try:
                await conn.ws.close()
            except Exception:
                pass
            conn.ws = None
        if conn.task and not conn.task.done():
            conn.task.cancel()
            try:
                await conn.task
            except (asyncio.CancelledError, Exception):
                pass
        conn.task = None

    async def _run_loop(self, conn: _QqConnection) -> None:
        """Main loop with exponential-backoff reconnection for *conn*."""
        delay = _RECONNECT_BASE_DELAY
        while conn.running:
            creds_ok = self._api.has_credentials_for(conn.app_id, conn.app_secret)
            if not creds_ok and not self._api.has_credentials:
                logger.warning(
                    "[QQ-WS] channel=%s stopping: no credentials configured",
                    conn.channel_id,
                )
                conn.running = False
                break
            try:
                await self._connect_and_listen(conn)
                delay = _RECONNECT_BASE_DELAY  # reset on clean disconnect
            except asyncio.CancelledError:
                break
            except _TRANSIENT_ERRORS as e:
                if not conn.running:
                    break
                logger.warning(
                    "[QQ-WS] channel=%s transient error (%s), reconnecting in %.1fs",
                    conn.channel_id, type(e).__name__, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX_DELAY)
            except Exception:
                if not conn.running:
                    break
                logger.warning(
                    "[QQ-WS] channel=%s connection lost, reconnecting in %.1fs",
                    conn.channel_id, delay,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX_DELAY)

    async def _connect_and_listen(self, conn: _QqConnection) -> None:
        # 1. Get gateway URL (also refreshes token)
        gw_url = await self._api.get_gateway_url(conn.app_id or None, conn.app_secret or None)
        if not gw_url:
            raise RuntimeError("QQ gateway returned empty URL")

        logger.info("[QQ-WS] channel=%s connecting to gateway: %s", conn.channel_id, gw_url)

        async with websockets.connect(gw_url, close_timeout=5) as ws:
            conn.ws = ws

            # 2. Receive Hello (op=10)
            hello_raw = await asyncio.wait_for(ws.recv(), timeout=_CONNECT_TIMEOUT)
            hello = json.loads(hello_raw)
            if hello.get("op") != _OP_HELLO:
                raise RuntimeError(f"Expected Hello (op=10), got: {hello}")
            heartbeat_interval = hello["d"]["heartbeat_interval"]
            logger.info(
                "[QQ-WS] channel=%s Hello received, heartbeat_interval=%dms",
                conn.channel_id, heartbeat_interval,
            )

            # 3. Send Identify (op=2)
            token = await self._api.ensure_token(conn.app_id or None, conn.app_secret or None)
            identify_payload = {
                "op": _OP_IDENTIFY,
                "d": {
                    "token": f"QQBot {token}",
                    "intents": _INTENTS,
                    "shard": [0, 1],
                },
            }
            await ws.send(json.dumps(identify_payload))

            # 4. Receive Ready (op=0, t=READY)
            ready_raw = await asyncio.wait_for(ws.recv(), timeout=_CONNECT_TIMEOUT)
            ready = json.loads(ready_raw)
            if ready.get("op") == _OP_DISPATCH and ready.get("t") == "READY":
                conn.session_ws_id = ready.get("d", {}).get("session_id")
                conn.sequence = ready.get("s")
                logger.info(
                    "[QQ-WS] channel=%s Ready: session_ws_id=%s",
                    conn.channel_id, conn.session_ws_id,
                )
            else:
                raise RuntimeError(f"Expected READY event, got: {ready}")

            # 5. Start heartbeat loop
            conn.heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(conn, ws, heartbeat_interval / 1000.0),
                name=f"qq-hb-{conn.channel_id[:8]}",
            )

            # 6. Listen for events
            try:
                async for msg_raw in ws:
                    data = json.loads(msg_raw)
                    op = data.get("op")

                    if op == _OP_DISPATCH:
                        seq = data.get("s")
                        if seq is not None:
                            conn.sequence = seq
                        await self._handle_dispatch(conn, data)
                    elif op == _OP_HEARTBEAT_ACK:
                        pass
                    elif op == _OP_RECONNECT:
                        logger.info("[QQ-WS] channel=%s server requested reconnect", conn.channel_id)
                        break
                    elif op == _OP_INVALID_SESSION:
                        logger.warning("[QQ-WS] channel=%s invalid session, will re-identify", conn.channel_id)
                        conn.session_ws_id = None
                        break
                    else:
                        logger.debug("[QQ-WS] channel=%s unhandled op=%s", conn.channel_id, op)
            finally:
                if conn.heartbeat_task and not conn.heartbeat_task.done():
                    conn.heartbeat_task.cancel()

    async def _heartbeat_loop(
        self, conn: _QqConnection, ws: ClientConnection, interval_s: float,
    ) -> None:
        """Send periodic heartbeats for a specific connection."""
        try:
            while True:
                await asyncio.sleep(interval_s)
                payload = json.dumps({"op": _OP_HEARTBEAT, "d": conn.sequence})
                await ws.send(payload)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("[QQ-WS] channel=%s heartbeat error", conn.channel_id, exc_info=True)

    async def _handle_dispatch(self, conn: _QqConnection, data: dict[str, Any]) -> None:
        event_type = data.get("t", "")
        event_data = data.get("d", {})
        logger.info("[QQ-WS] channel=%s Dispatch event: t=%s", conn.channel_id, event_type)

        if event_type in ("C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"):
            msg_id = event_data.get("id", "")
            content = (event_data.get("content") or "").strip()
            logger.info(
                "[QQ-WS] channel=%s Message event: t=%s msg_id=%s content=%.100s",
                conn.channel_id, event_type, msg_id, content,
            )
            if not content or not msg_id:
                logger.warning("[QQ-WS] channel=%s Skipping: empty content or msg_id", conn.channel_id)
                return

            if event_type == "C2C_MESSAGE_CREATE":
                sender_openid = event_data.get("author", {}).get("user_openid", "")
                group_openid = None
            else:
                sender_openid = event_data.get("author", {}).get("member_openid", "")
                group_openid = event_data.get("group_openid", "")

            logger.info(
                "[QQ-WS] channel=%s Parsed: sender=%s group=%s",
                conn.channel_id, sender_openid, group_openid,
            )

            if conn.on_message:
                try:
                    logger.info("[QQ-WS] channel=%s Calling on_message callback...", conn.channel_id)
                    await conn.on_message(msg_id, content, sender_openid, group_openid)
                    logger.info("[QQ-WS] channel=%s on_message callback returned", conn.channel_id)
                except Exception:
                    logger.error(
                        "[QQ-WS] channel=%s on_message callback failed for msg %s",
                        conn.channel_id, msg_id,
                        exc_info=True,
                    )
            else:
                logger.warning("[QQ-WS] channel=%s No on_message callback registered!", conn.channel_id)
        elif event_type == "READY":
            pass  # Already handled during connect
        else:
            logger.info("[QQ-WS] channel=%s Unhandled dispatch: t=%s", conn.channel_id, event_type)
