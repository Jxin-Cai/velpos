"""Lark IM channel adapter — direct Feishu API + lark-oapi WebSocket.

No lark-cli dependency.  Singleton instance registered in dependencies.py.
Supports multiple concurrent channel instances, each with its own WS listener.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field

from domain.im_binding.acl.im_channel_adapter import (
    BindResult,
    ImChannelAdapter,
    InitResult,
)
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from infr.im.lark.lark_api import LarkApiClient, LarkApiError

logger = logging.getLogger(__name__)

LARK_CHANNEL_SPEC = ImChannelSpec(
    channel_type=ImChannelType.LARK,
    display_name="Lark",
    icon="lark",
    required_plugin=None,       # no external plugin dependency
    binding_mode=BindingMode.QR_CODE,
    init_fields=(),
    init_mode="qr_login",
    description="Feishu/Lark bot. Scan QR code to create or select an app.",
)


@dataclass
class _WsConnection:
    """Per-channel WS connection state."""
    channel_id: str
    session_id: str
    thread: threading.Thread | None = None
    client: object | None = None  # lark_oapi.ws.Client
    stop: bool = False
    on_message: object | None = None
    main_loop: asyncio.AbstractEventLoop | None = None
    ws_loop: asyncio.AbstractEventLoop | None = None


class LarkAdapter(ImChannelAdapter):
    """Lark IM adapter — singleton, supports multiple simultaneous WS listeners.

    Each channel instance (identified by channel_id) gets its own WS connection.
    This allows multiple Lark apps to be bound to different sessions simultaneously.
    """

    def __init__(self) -> None:
        self._api = LarkApiClient()
        # Multiple WS connections keyed by channel_id
        self._connections: dict[str, _WsConnection] = {}
        self._lock = threading.Lock()

    # ── Initialization ──────────────────────────────────────────

    async def check_init_status(self, config: dict) -> bool:
        app_id = config.get("app_id", "")
        app_secret = config.get("app_secret", "")
        brand = config.get("brand", "feishu")
        if not app_id or not app_secret:
            return False
        try:
            await self._api.get_tenant_token(app_id, app_secret, brand)
            return True
        except Exception:
            return False

    async def initialize(self, params: dict) -> InitResult:
        step = params.get("step", "start")
        brand = params.get("brand", "feishu")
        logger.info("[Lark-adapter] initialize: step=%s brand=%s", step, brand)

        if step == "start":
            return await self._init_start(brand)
        elif step == "poll":
            return await self._init_poll(params, brand)

        return InitResult(
            status=ChannelInitStatus.ERROR,
            error_message=f"Unknown init step: {step}",
        )

    async def _init_start(self, brand: str) -> InitResult:
        try:
            data = await self._api.app_registration_begin(brand)
            verification_url = data["verification_url"]
            device_code = data["device_code"]

            logger.info(
                "[Lark-adapter] App registration started: device_code=%s",
                bool(device_code),
            )
            return InitResult(
                status=ChannelInitStatus.INITIALIZING,
                ui_data={
                    "verification_url": verification_url,
                    "qrcode": device_code,
                    "step": "poll",
                    "login_status": "waiting",
                    "expires_in": data.get("expires_in", 300),
                },
            )
        except LarkApiError as e:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message=str(e),
            )
        except Exception as e:
            logger.error("[Lark-adapter] init start failed", exc_info=True)
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message=f"Failed to start app registration: {e}",
            )

    async def _init_poll(self, params: dict, brand: str) -> InitResult:
        device_code = params.get("qrcode", "")
        if not device_code:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message="Missing device_code for polling.",
            )

        try:
            result = await self._api.app_registration_poll(device_code, brand)
        except LarkApiError as e:
            return InitResult(
                status=ChannelInitStatus.ERROR,
                error_message=str(e),
            )

        status = result.get("status", "")

        if status in ("authorization_pending", "slow_down"):
            return InitResult(
                status=ChannelInitStatus.INITIALIZING,
                ui_data={
                    "login_status": "waiting",
                    "qrcode": device_code,
                    "step": "poll",
                },
            )

        if status == "ok":
            client_id = result["client_id"]
            client_secret = result.get("client_secret", "")
            tenant_brand = result.get("tenant_brand", brand)

            if not client_secret and tenant_brand == "lark":
                logger.info("[Lark-adapter] No secret with feishu, retrying with lark endpoint")
                try:
                    result2 = await self._api.app_registration_poll(device_code, "lark")
                    if result2.get("status") == "ok":
                        client_secret = result2.get("client_secret", "")
                        tenant_brand = "lark"
                except Exception:
                    logger.debug("Lark endpoint retry failed", exc_info=True)

            actual_brand = tenant_brand if tenant_brand in ("feishu", "lark") else brand

            try:
                await self._api.get_tenant_token(client_id, client_secret, actual_brand)
            except Exception as e:
                logger.warning("[Lark-adapter] Tenant token validation failed: %s", e)
                return InitResult(
                    status=ChannelInitStatus.ERROR,
                    error_message=f"Credentials obtained but token validation failed: {e}",
                )

            logger.info(
                "[Lark-adapter] App registration complete: app_id=%s brand=%s",
                client_id, actual_brand,
            )
            return InitResult(
                status=ChannelInitStatus.READY,
                config={
                    "app_id": client_id,
                    "app_secret": client_secret,
                    "brand": actual_brand,
                    "open_id": result.get("open_id", ""),
                },
            )

        return InitResult(
            status=ChannelInitStatus.ERROR,
            error_message=f"Unexpected registration status: {status}",
        )

    # ── Binding lifecycle ───────────────────────────────────────

    async def bind(
        self, session_id: str, binding: ImBinding, params: dict,
    ) -> BindResult:
        logger.info("[Lark-adapter] bind: session=%s channel_id=%s", session_id, binding.channel_id)
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=f"lark-{binding.channel_id}-{session_id}",
            config={
                "app_id": params.get("app_id", ""),
                "app_secret": params.get("app_secret", ""),
                "brand": params.get("brand", "feishu"),
            },
            ui_data={
                "mode": "direct",
                "display_name": "Lark",
                "description": "Listening for Feishu/Lark messages.",
            },
        )

    async def complete_bind(
        self, binding: ImBinding, params: dict,
    ) -> BindResult:
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=binding.channel_address or f"lark-{binding.channel_id}-{binding.session_id}",
        )

    async def unbind(self, binding: ImBinding) -> None:
        await self.stop_listening(binding)

    # ── Message listening (lark-oapi WebSocket) ─────────────────

    async def start_listening(self, binding: ImBinding, on_message=None) -> None:
        """Start lark-oapi WebSocket client for this channel instance."""
        channel_id = binding.channel_id
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")
        brand = binding.config.get("brand", "feishu")

        if not app_id or not app_secret:
            logger.error("[Lark-adapter] No app_id/app_secret for start_listening channel=%s", channel_id)
            return

        # Stop existing listener for this specific channel if any
        with self._lock:
            existing = self._connections.get(channel_id)
        if existing and existing.thread and existing.thread.is_alive():
            logger.info("[Lark-adapter] Stopping existing WS for channel=%s before restart", channel_id)
            await self._stop_connection(existing)

        conn = _WsConnection(
            channel_id=channel_id,
            session_id=binding.session_id,
            on_message=on_message,
            main_loop=asyncio.get_running_loop(),
        )

        with self._lock:
            self._connections[channel_id] = conn

        logger.info(
            "[Lark-adapter] Starting WS listener: session=%s channel=%s app_id=%s",
            binding.session_id, channel_id, app_id,
        )

        conn.thread = threading.Thread(
            target=self._run_ws_client,
            args=(conn, app_id, app_secret, brand),
            daemon=True,
            name=f"lark-ws-{channel_id[:8]}",
        )
        conn.thread.start()

    async def stop_listening(self, binding: ImBinding) -> None:
        """Stop the WebSocket listener for a specific channel instance."""
        channel_id = binding.channel_id
        with self._lock:
            conn = self._connections.pop(channel_id, None)
        if conn:
            await self._stop_connection(conn)

    async def _stop_connection(self, conn: _WsConnection) -> None:
        """Stop a single WS connection.

        1. Set stop flag so outer retry loop won't restart.
        2. Disconnect the WebSocket (graceful close).
        3. Stop the event loop — causes SDK's start() to exit.
        """
        logger.info("[Lark-adapter] Stopping WS for channel=%s session=%s", conn.channel_id, conn.session_id)
        conn.stop = True
        ws_loop = conn.ws_loop
        client = conn.client

        if client is not None and ws_loop is not None and not ws_loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(client._disconnect(), ws_loop)
                future.result(timeout=5)
            except Exception:
                logger.debug("[Lark-adapter] WS disconnect error for channel=%s", conn.channel_id, exc_info=True)
            try:
                ws_loop.call_soon_threadsafe(ws_loop.stop)
            except Exception:
                pass

        conn.client = None
        conn.ws_loop = None
        conn.thread = None

    _RECONNECT_DELAYS = (5, 10, 30, 60)  # back-off for catastrophic failures only

    @staticmethod
    def _patch_ws_client(ws_client: object, thread_loop: asyncio.AbstractEventLoop) -> None:
        """Monkey-patch a lark-oapi WS Client instance so all internal methods
        use *thread_loop* directly instead of the module-level ``loop`` global.

        The SDK stores ``loop`` at module scope and every method references it
        via the global name.  When multiple channels each spin up their own
        event-loop thread, concurrent writes/reads to that single global cause
        tasks to land on the wrong loop.

        By patching the *instance* methods we bind ``_loop`` as a closure
        variable — completely sidestepping the global.
        """
        import types
        _loop = thread_loop  # captured by closures below

        # --- _disconnect() (patch first, used by others) ---
        async def patched_disconnect(self_ws):
            try:
                await self_ws._lock.acquire()
                if self_ws._conn is None:
                    return
                await self_ws._conn.close()
                from lark_oapi.core.log import logger as sdk_logger
                sdk_logger.info(self_ws._fmt_log("disconnected to {}", self_ws._conn_url))
            finally:
                self_ws._conn = None
                self_ws._conn_url = ""
                self_ws._conn_id = ""
                self_ws._service_id = ""
                self_ws._lock.release()

        ws_client._disconnect = types.MethodType(patched_disconnect, ws_client)

        # --- _receive_message_loop() ---
        async def patched_receive_message_loop(self_ws):
            try:
                while True:
                    if self_ws._conn is None:
                        from lark_oapi.ws.exception import ConnectionClosedException
                        raise ConnectionClosedException("connection is closed")
                    msg = await self_ws._conn.recv()
                    _loop.create_task(self_ws._handle_message(msg))
            except Exception as e:
                from lark_oapi.core.log import logger as sdk_logger
                sdk_logger.error(self_ws._fmt_log("receive message loop exit, err: {}", e))
                await self_ws._disconnect()
                if self_ws._auto_reconnect:
                    await self_ws._reconnect()
                else:
                    raise

        ws_client._receive_message_loop = types.MethodType(patched_receive_message_loop, ws_client)

        # --- _connect() ---
        async def patched_connect(self_ws):
            await self_ws._lock.acquire()
            if self_ws._conn is not None:
                self_ws._lock.release()
                return
            try:
                conn_url = self_ws._get_conn_url()
                from urllib.parse import urlparse, parse_qs
                from lark_oapi.ws.const import DEVICE_ID, SERVICE_ID
                import websockets

                u = urlparse(conn_url)
                q = parse_qs(u.query)
                conn_id = q[DEVICE_ID][0]
                service_id = q[SERVICE_ID][0]

                conn = await websockets.connect(conn_url)
                self_ws._conn = conn
                self_ws._conn_url = conn_url
                self_ws._conn_id = conn_id
                self_ws._service_id = service_id

                from lark_oapi.core.log import logger as sdk_logger
                sdk_logger.info(self_ws._fmt_log("connected to {}", conn_url))
                _loop.create_task(self_ws._receive_message_loop())
            except Exception as e:
                import websockets
                if isinstance(e, websockets.InvalidStatusCode):
                    from lark_oapi.ws.client import _parse_ws_conn_exception
                    _parse_ws_conn_exception(e)
                else:
                    raise
            finally:
                self_ws._lock.release()

        ws_client._connect = types.MethodType(patched_connect, ws_client)

        # --- _reconnect() ---
        async def _try_connect(self_ws, cnt):
            from lark_oapi.core.log import logger as sdk_logger
            from lark_oapi.ws.exception import ClientException
            from lark_oapi.ws.client import _ordinal
            sdk_logger.info(self_ws._fmt_log("trying to reconnect for the {} time", _ordinal(cnt + 1)))
            try:
                await self_ws._connect()
                return True
            except ClientException as e:
                sdk_logger.error(self_ws._fmt_log("connect failed, err: {}", e))
                raise
            except Exception as e:
                sdk_logger.error(self_ws._fmt_log("connect failed, err: {}", e))
                return False

        async def patched_reconnect(self_ws):
            import random
            if self_ws._reconnect_nonce > 0:
                nonce = random.random() * self_ws._reconnect_nonce
                await asyncio.sleep(nonce)

            if self_ws._reconnect_count >= 0:
                for i in range(self_ws._reconnect_count):
                    if await _try_connect(self_ws, i):
                        return
                    await asyncio.sleep(self_ws._reconnect_interval)
                from lark_oapi.ws.exception import ServerUnreachableException
                raise ServerUnreachableException(
                    f"unable to connect to the server after trying {self_ws._reconnect_count} times")
            else:
                i = 0
                while True:
                    if await _try_connect(self_ws, i):
                        return
                    await asyncio.sleep(self_ws._reconnect_interval)
                    i += 1

        ws_client._reconnect = types.MethodType(patched_reconnect, ws_client)

        # --- start() (patch last — calls patched _connect/_disconnect/_reconnect/_ping_loop) ---
        async def _select():
            while True:
                await asyncio.sleep(3600)

        def patched_start(self_ws):
            try:
                _loop.run_until_complete(self_ws._connect())
            except Exception as e:
                from lark_oapi.ws.exception import ClientException
                if isinstance(e, ClientException):
                    raise
                from lark_oapi.core.log import logger as sdk_logger
                sdk_logger.error(self_ws._fmt_log("connect failed, err: {}", e))
                _loop.run_until_complete(self_ws._disconnect())
                if self_ws._auto_reconnect:
                    _loop.run_until_complete(self_ws._reconnect())
                else:
                    raise
            _loop.create_task(self_ws._ping_loop())
            _loop.run_until_complete(_select())

        ws_client.start = types.MethodType(patched_start, ws_client)

    def _run_ws_client(
        self, conn: _WsConnection, app_id: str, app_secret: str, brand: str,
    ) -> None:
        """Background thread — drives the lark-oapi WS lifecycle.

        Uses the SDK's ``Client.start()`` which blocks and internally handles:
          connect → receive_message_loop → ping_loop → auto-reconnect.

        The outer while loop is a safety net for catastrophic failures where
        the SDK gives up entirely (e.g. credentials expired, max retries
        exceeded).  Normal transient disconnects are handled by the SDK.

        The SDK uses a **module-level** ``loop`` variable for all
        ``create_task()`` / ``run_until_complete()`` calls.  To avoid a race
        condition where multiple WS threads overwrite each other's loop
        reference, we monkey-patch each Client *instance* so every method
        closes over the thread-local event loop directly.
        """
        attempt = 0

        try:
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
            from lark_oapi.ws import Client as LarkWsClient
            from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

            domain = LARK_DOMAIN if brand == "lark" else FEISHU_DOMAIN

            def on_lark_message(data):
                self._on_lark_message(conn, data)

            handler = EventDispatcherHandler.builder("", "") \
                .register_p2_im_message_receive_v1(on_lark_message) \
                .register_p2_im_message_message_read_v1(lambda data: None) \
                .build()

            while not conn.stop:
                thread_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(thread_loop)
                conn.ws_loop = thread_loop

                ws_client = LarkWsClient(
                    app_id=app_id,
                    app_secret=app_secret,
                    event_handler=handler,
                    domain=domain,
                    auto_reconnect=True,
                )
                # Patch instance to use thread-local loop (avoids module-level global race)
                self._patch_ws_client(ws_client, thread_loop)
                conn.client = ws_client

                try:
                    logger.info(
                        "[Lark-adapter] WS starting channel=%s attempt=%d domain=%s",
                        conn.channel_id, attempt, domain,
                    )
                    ws_client.start()   # blocks until loop.stop() or fatal error
                except Exception:
                    if not conn.stop:
                        logger.error(
                            "[Lark-adapter] WS client error channel=%s",
                            conn.channel_id, exc_info=True,
                        )

                conn.client = None

                if not thread_loop.is_closed():
                    try:
                        thread_loop.close()
                    except Exception:
                        pass

                if conn.stop:
                    break

                delay = self._RECONNECT_DELAYS[min(attempt, len(self._RECONNECT_DELAYS) - 1)]
                logger.info(
                    "[Lark-adapter] WS exited, retrying in %ds channel=%s",
                    delay, conn.channel_id,
                )
                attempt += 1
                time.sleep(delay)

        except Exception:
            if not conn.stop:
                logger.error("[Lark-adapter] WS thread fatal channel=%s", conn.channel_id, exc_info=True)
        finally:
            conn.client = None
            if conn.ws_loop is not None and not conn.ws_loop.is_closed():
                try:
                    conn.ws_loop.close()
                except Exception:
                    pass
            conn.ws_loop = None
            logger.info("[Lark-adapter] WS thread exited channel=%s", conn.channel_id)

    def _on_lark_message(self, conn: _WsConnection, data) -> None:
        """Callback from lark-oapi SDK (runs in WS thread), scoped to a specific connection."""
        try:
            logger.info("[Lark-adapter] Raw event received: channel=%s data_type=%s", conn.channel_id, type(data).__name__)

            event = data.event
            if event is None:
                logger.warning("[Lark-adapter] Event is None: channel=%s", conn.channel_id)
                return

            msg = event.message
            if msg is None:
                logger.warning("[Lark-adapter] Event.message is None: channel=%s", conn.channel_id)
                return

            message_id = msg.message_id or ""
            chat_id = msg.chat_id or ""
            msg_type = msg.message_type or "text"

            content = ""
            if msg.content:
                try:
                    content_data = json.loads(msg.content)
                    content = content_data.get("text", "")
                except (json.JSONDecodeError, TypeError):
                    content = msg.content

            sender_id = ""
            if event.sender and event.sender.sender_id:
                sender_id = event.sender.sender_id.open_id or ""

            if not content or not message_id:
                logger.warning(
                    "[Lark-adapter] Skipping event: content=%r message_id=%r msg_type=%s raw_content=%r channel=%s",
                    content, message_id, msg_type, msg.content, conn.channel_id,
                )
                return

            logger.info(
                "[Lark-adapter] Message: channel=%s msg_id=%s chat_id=%s sender=%s type=%s content=%.100s",
                conn.channel_id, message_id, chat_id, sender_id, msg_type, content,
            )

            # Dispatch to main event loop using this connection's callback
            if conn.on_message and conn.main_loop:
                future = asyncio.run_coroutine_threadsafe(
                    conn.on_message(message_id, content, sender_id, chat_id),
                    conn.main_loop,
                )
                logger.info("[Lark-adapter] Dispatched to main loop: channel=%s msg_id=%s", conn.channel_id, message_id)
            else:
                logger.error(
                    "[Lark-adapter] Cannot dispatch: on_message=%s main_loop=%s channel=%s",
                    bool(conn.on_message), bool(conn.main_loop), conn.channel_id,
                )
        except Exception:
            logger.error("[Lark-adapter] Error handling event channel=%s", conn.channel_id, exc_info=True)

    # ── Send message ────────────────────────────────────────────

    async def send_message(
        self, binding: ImBinding, content: str,
        reply_context: dict | None = None,
    ) -> None:
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")
        brand = binding.config.get("brand", "feishu")

        if not app_id or not app_secret:
            logger.warning("[Lark-adapter] No credentials for send_message")
            return

        ctx = reply_context or {}
        chat_id = ctx.get("group_id", "")
        reply_msg_id = ctx.get("msg_id", "")
        open_id = binding.config.get("open_id", "")

        # Determine send target: chat_id > open_id
        receive_id = chat_id
        receive_id_type = "chat_id"
        if not receive_id and open_id:
            receive_id = open_id
            receive_id_type = "open_id"

        if not receive_id:
            logger.warning("[Lark-adapter] send_message: no chat_id or open_id in reply_context")
            return

        try:
            token = await self._api.get_tenant_token(app_id, app_secret, brand)

            sent = False
            # Try reply first if we have a message ID
            if reply_msg_id:
                try:
                    await self._api.reply_message(token, reply_msg_id, content, brand=brand)
                    sent = True
                except Exception:
                    logger.warning(
                        "[Lark-adapter] reply_message failed, falling back to send_message: channel=%s",
                        binding.channel_id, exc_info=True,
                    )

            # Fallback: send as new message
            if not sent:
                await self._api.send_message(
                    token, receive_id, content,
                    receive_id_type=receive_id_type, brand=brand,
                )

            logger.info("[Lark-adapter] Message sent: channel=%s target=%s reply=%s", binding.channel_id, receive_id[:8], bool(reply_msg_id and sent))
        except Exception:
            logger.error("[Lark-adapter] send_message error channel=%s", binding.channel_id, exc_info=True)

    async def close(self) -> None:
        """Shutdown adapter — stop all WS listeners."""
        with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()

        for conn in connections:
            await self._stop_connection(conn)

        logger.info("[Lark-adapter] Adapter closed, %d connections stopped", len(connections))

    # ── Reactions (optional) ────────────────────────────────────

    async def add_reaction(
        self, binding: ImBinding, message_id: str, reaction: str,
    ) -> str:
        """Add emoji reaction. Returns reaction_id for later removal."""
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")
        brand = binding.config.get("brand", "feishu")
        if not app_id or not app_secret:
            logger.warning("[Lark-adapter] No credentials for add_reaction")
            return ""
        try:
            token = await self._api.get_tenant_token(app_id, app_secret, brand)
            reaction_id = await self._api.add_reaction(token, message_id, reaction, brand=brand)
            logger.info("[Lark-adapter] Reaction added: msg=%s type=%s id=%s", message_id, reaction, reaction_id)
            return reaction_id
        except Exception:
            logger.warning("[Lark-adapter] add_reaction failed", exc_info=True)
            return ""

    async def remove_reaction(
        self, binding: ImBinding, message_id: str, reaction_id: str,
    ) -> None:
        """Remove emoji reaction by reaction_id."""
        if not reaction_id:
            return
        app_id = binding.config.get("app_id", "")
        app_secret = binding.config.get("app_secret", "")
        brand = binding.config.get("brand", "feishu")
        if not app_id or not app_secret:
            return
        try:
            token = await self._api.get_tenant_token(app_id, app_secret, brand)
            await self._api.delete_reaction(token, message_id, reaction_id, brand=brand)
            logger.info("[Lark-adapter] Reaction removed: msg=%s id=%s", message_id, reaction_id)
        except Exception:
            logger.warning("[Lark-adapter] remove_reaction failed", exc_info=True)
