"""Lark IM channel adapter — direct Feishu API + lark-oapi WebSocket.

No lark-cli dependency.  Singleton instance registered in dependencies.py.
Supports multiple concurrent channel instances, each with its own WS listener.
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.im_binding.acl.channel_errors import ChannelRoutingError
from domain.im_binding.acl.im_channel_adapter import (
    BindResult,
    ImChannelAdapter,
    InboundHandler,
    InitResult,
)
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_init_status import ChannelInitStatus
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.channel_spec import BindingMode, ImChannelSpec
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding
from domain.im_binding.model.im_message import (
    InboundMessage,
    MessageSegment,
    OutboundMessage,
    SegmentType,
    SendReceipt,
)
from infr.im.lark.lark_api import LarkApiClient, LarkApiError
from infr.im.lark.lark_message import (
    LarkInboundContent,
    LarkMessageType,
    LarkOutboundMessage,
    parse_inbound_content,
)
from infr.storage.attachment_storage_gateway import AttachmentStorageGateway

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
    # 飞书是能力基准, 其余渠道以此对齐. 唯二不支持的是"正在输入"（平台无此
    # 接口, 用 reaction 表达处理中）和文本进度回报（有 reaction 就不需要）。
    capabilities=frozenset(ChannelCapability)
    - {
        ChannelCapability.TYPING_INDICATOR,
        ChannelCapability.PROGRESS_ACK,
    },
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
    credentials: tuple[str, str, str] | None = None


class LarkAdapter(ImChannelAdapter):
    """Lark IM adapter — singleton, supports multiple simultaneous WS listeners.

    Each channel instance (identified by channel_id) gets its own WS connection.
    This allows multiple Lark apps to be bound to different sessions simultaneously.
    """

    def __init__(self) -> None:
        self._api = LarkApiClient()
        self._sdk_clients: dict[tuple[str, str, str], Any] = {}
        self._attachment_storage = AttachmentStorageGateway()
        # Multiple WS connections keyed by channel_id
        self._connections: dict[str, _WsConnection] = {}
        self._lock = asyncio.Lock()

    def _get_sdk_client(self, app_id: str, app_secret: str, brand: str):
        key = (app_id, app_secret, brand)
        client = self._sdk_clients.get(key)
        if client is not None:
            return client

        import lark_oapi as lark
        from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

        domain = LARK_DOMAIN if brand == "lark" else FEISHU_DOMAIN
        client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .domain(domain)
            .build()
        )
        self._sdk_clients[key] = client
        return client

    def _get_credentials(
        self, binding_or_config: ImBinding | dict,
    ) -> tuple[str, str, str] | None:
        """Extract and validate (app_id, app_secret, brand) from binding or config dict.

        Returns ``(app_id, app_secret, brand)`` or ``None`` if credentials are missing.
        """
        config = binding_or_config if isinstance(binding_or_config, dict) else binding_or_config.config
        app_id = config.get("app_id", "")
        app_secret = config.get("app_secret", "")
        brand = config.get("brand", "feishu")
        if not app_id or not app_secret:
            return None
        return (app_id, app_secret, brand)

    # ── Initialization ──────────────────────────────────────────

    async def check_init_status(self, config: dict) -> bool:
        creds = self._get_credentials(config)
        if not creds:
            return False
        app_id, app_secret, brand = creds
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
        self, binding: ImBinding, _params: dict,
    ) -> BindResult:
        return BindResult(
            status=BindingStatus.BOUND,
            channel_address=binding.channel_address or f"lark-{binding.channel_id}-{binding.session_id}",
        )

    async def unbind(self, binding: ImBinding) -> None:
        await self.stop_listening(binding)

    # ── Message listening (lark-oapi WebSocket) ─────────────────

    async def start_listening(
        self, binding: ImBinding, on_message: InboundHandler | None = None,
    ) -> None:
        """Start lark-oapi WebSocket client for this channel instance."""
        channel_id = binding.channel_id
        creds = self._get_credentials(binding)
        if not creds:
            logger.error("[Lark-adapter] No app_id/app_secret for start_listening channel=%s", channel_id)
            return
        app_id, app_secret, brand = creds

        conn = _WsConnection(
            channel_id=channel_id,
            session_id=binding.session_id,
            on_message=on_message,
            main_loop=asyncio.get_running_loop(),
            credentials=creds,
        )

        # Atomically replace: pop old + insert new inside one lock acquisition
        existing = None
        async with self._lock:
            existing = self._connections.pop(channel_id, None)
            self._connections[channel_id] = conn

        # Stop existing outside lock (new conn is already registered)
        if existing and existing.thread and existing.thread.is_alive():
            logger.info("[Lark-adapter] Stopping existing WS for channel=%s before restart", channel_id)
            await self._stop_connection(existing)

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
        async with self._lock:
            conn = self._connections.pop(channel_id, None)
        if conn:
            await self._stop_connection(conn)

    _DISCONNECT_TIMEOUT_SECONDS = 5

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
                setattr(client, "_velpos_expected_close", True)
                future = asyncio.run_coroutine_threadsafe(client._disconnect(), ws_loop)
                # The WS runs on its own loop, so the handshake must be awaited
                # rather than waited on synchronously: future.result() would
                # freeze the caller's event loop, and with it every other
                # request, for the whole timeout window.
                await asyncio.wait_for(
                    asyncio.wrap_future(future), self._DISCONNECT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    "[Lark-adapter] WS disconnect timed out after %ss for channel=%s",
                    self._DISCONNECT_TIMEOUT_SECONDS, conn.channel_id,
                )
            except Exception:
                logger.debug("[Lark-adapter] WS disconnect error for channel=%s", conn.channel_id, exc_info=True)
            try:
                ws_loop.call_soon_threadsafe(ws_loop.stop)
            except Exception:
                pass

        conn.client = None
        conn.thread = None
        # Leave conn.ws_loop for the WS thread to drain pending tasks
        # (ExpiringCache cron) before close.  Nulling it here races GC.

    @staticmethod
    def _shutdown_event_loop(loop: asyncio.AbstractEventLoop) -> None:
        """Cancel pending tasks, then close *loop*.

        lark-oapi's ``ExpiringCache`` schedules a never-ending
        ``_start_clear_cron`` task on whatever loop is current when the WS
        client is constructed, and cancels that task in ``__del__``.  Closing
        the loop while the task is still pending produces both
        ``RuntimeError: Event loop is closed`` during GC and asyncio's
        ``Task was destroyed but it is pending!`` log.
        """
        if loop.is_closed():
            return
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            logger.warning(
                "[Lark-adapter] Error draining WS event loop",
                exc_info=True,
            )
        finally:
            try:
                if not loop.is_closed():
                    loop.close()
            except Exception:
                logger.warning(
                    "[Lark-adapter] Error closing WS event loop",
                    exc_info=True,
                )

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
                if getattr(self_ws, "_velpos_expected_close", False) or "1000 (OK)" in str(e):
                    sdk_logger.info(self_ws._fmt_log("receive message loop closed, err: {}", e))
                    await self_ws._disconnect()
                    return
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
            from lark_oapi.ws import Client as LarkWsClient
            from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

            domain = LARK_DOMAIN if brand == "lark" else FEISHU_DOMAIN
            handler = self._build_event_handler(conn)

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
                self._shutdown_event_loop(thread_loop)

                if conn.stop:
                    break

                delay = self._RECONNECT_DELAYS[min(attempt, len(self._RECONNECT_DELAYS) - 1)]
                logger.info(
                    "[Lark-adapter] WS exited, retrying in %ds channel=%s",
                    delay, conn.channel_id,
                )
                attempt += 1
                for _ in range(delay):
                    if conn.stop:
                        break
                    time.sleep(1)

        except Exception:
            if not conn.stop:
                logger.error("[Lark-adapter] WS thread fatal channel=%s", conn.channel_id, exc_info=True)
        finally:
            conn.client = None
            if conn.ws_loop is not None:
                self._shutdown_event_loop(conn.ws_loop)
            conn.ws_loop = None
            logger.info("[Lark-adapter] WS thread exited channel=%s", conn.channel_id)

    def _build_event_handler(self, conn: _WsConnection):
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

        def on_lark_message(data):
            self._on_lark_message(conn, data)

        def on_card_action(data):
            return self._on_card_action(conn, data)

        return (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_lark_message)
            .register_p2_im_message_message_read_v1(lambda data: None)
            .register_p2_im_message_reaction_created_v1(lambda data: None)
            .register_p2_im_message_reaction_deleted_v1(lambda data: None)
            .register_p2_card_action_trigger(on_card_action)
            .build()
        )

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

            sender_id = ""
            if event.sender and event.sender.sender_id:
                sender_id = event.sender.sender_id.open_id or ""

            if not message_id:
                logger.warning(
                    "[Lark-adapter] Skipping event without message_id: "
                    "msg_type=%s channel=%s",
                    msg_type,
                    conn.channel_id,
                )
                return

            logger.info(
                "[Lark-adapter] Message: channel=%s msg_id=%s chat_id=%s "
                "sender=%s type=%s",
                conn.channel_id,
                message_id,
                chat_id,
                sender_id,
                msg_type,
            )

            if conn.on_message and conn.main_loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._handle_lark_message(
                        conn,
                        message_id=message_id,
                        message_type=msg_type,
                        raw_content=msg.content or "",
                        sender_id=sender_id,
                        chat_id=chat_id,
                    ),
                    conn.main_loop,
                )
                future.add_done_callback(
                    lambda f, cid=conn.channel_id, mid=message_id: (
                        logger.error(
                            "[Lark-adapter] on_message callback failed: channel=%s msg_id=%s",
                            cid, mid, exc_info=f.exception(),
                        )
                        if not f.cancelled() and f.exception() else None
                    )
                )
            else:
                logger.error(
                    "[Lark-adapter] Cannot dispatch: on_message=%s main_loop=%s channel=%s",
                    bool(conn.on_message), bool(conn.main_loop), conn.channel_id,
                )
        except Exception:
            logger.error("[Lark-adapter] Error handling event channel=%s", conn.channel_id, exc_info=True)

    async def _handle_lark_message(
        self,
        conn: _WsConnection,
        *,
        message_id: str,
        message_type: str,
        raw_content: str,
        sender_id: str,
        chat_id: str,
    ) -> None:
        parsed = parse_inbound_content(message_type, raw_content)
        content, attachments = await self._materialize_inbound_resources(
            conn,
            message_id,
            message_type,
            parsed,
        )
        if not content.strip():
            logger.warning(
                "[Lark-adapter] Skipping empty decoded message: channel=%s "
                "msg_id=%s type=%s",
                conn.channel_id,
                message_id,
                message_type,
            )
            return
        await conn.on_message(
            _inbound_message(
                conn.channel_id,
                message_id,
                content,
                sender_id,
                chat_id,
                attachments,
            )
        )

    async def _materialize_inbound_resources(
        self,
        conn: _WsConnection,
        message_id: str,
        message_type: str,
        parsed: LarkInboundContent,
    ) -> tuple[str, list[dict[str, Any]]]:
        if not parsed.resources:
            return parsed.text, []
        app_credentials = self._connection_credentials(conn.channel_id)
        if app_credentials is None:
            logger.warning(
                "[Lark-adapter] Cannot download message resources without credentials: "
                "channel=%s msg_id=%s",
                conn.channel_id,
                message_id,
            )
            return parsed.text, []
        app_id, app_secret, brand = app_credentials
        client = self._get_sdk_client(app_id, app_secret, brand)
        attachments: list[dict[str, Any]] = []
        for resource_type, file_key in parsed.resources:
            try:
                attachment = await self._download_message_resource(
                    client,
                    conn.session_id,
                    message_id,
                    file_key,
                    resource_type,
                    message_type,
                )
                attachments.append(attachment)
            except LarkApiError:
                logger.error(
                    "[Lark-adapter] Failed to download inbound resource: "
                    "channel=%s msg_id=%s type=%s",
                    conn.channel_id,
                    message_id,
                    resource_type,
                    exc_info=True,
                )
        return parsed.text, attachments

    def _connection_credentials(self, channel_id: str) -> tuple[str, str, str] | None:
        conn = self._connections.get(channel_id)
        if conn is None:
            return None
        return conn.credentials

    async def _download_message_resource(
        self,
        client,
        session_id: str,
        message_id: str,
        file_key: str,
        resource_type: str,
        message_type: str,
    ) -> dict[str, Any]:
        from lark_oapi.api.im.v1 import GetMessageResourceRequest

        request = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type(resource_type)
            .build()
        )
        response = await client.im.v1.message_resource.aget(request)
        if not response.success() or response.file is None:
            raise self._sdk_error("download message resource", response)
        data = response.file.getvalue()
        filename = response.file_name or self._default_resource_name(message_type, file_key)
        filename = self._ensure_resource_suffix(filename, message_type)
        path, digest = self._attachment_storage.save("", session_id, filename, data)
        mime_type = mimetypes.guess_type(filename)[0] or self._default_mime_type(message_type)
        return {
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(data),
            "path": path,
            "sha256": digest,
            "source": "lark",
            "external_key": file_key,
        }

    @staticmethod
    def _default_resource_name(message_type: str, file_key: str) -> str:
        extension = {
            LarkMessageType.IMAGE.value: ".png",
            LarkMessageType.AUDIO.value: ".opus",
            LarkMessageType.MEDIA.value: ".mp4",
        }.get(message_type, ".bin")
        return f"lark-{file_key[:12] or uuid.uuid4().hex[:12]}{extension}"

    @staticmethod
    def _default_mime_type(message_type: str) -> str:
        return {
            LarkMessageType.IMAGE.value: "image/png",
            LarkMessageType.AUDIO.value: "audio/ogg",
            LarkMessageType.MEDIA.value: "video/mp4",
        }.get(message_type, "application/octet-stream")

    @staticmethod
    def _ensure_resource_suffix(filename: str, message_type: str) -> str:
        if Path(filename).suffix:
            return filename
        suffix = {
            LarkMessageType.IMAGE.value: ".png",
            LarkMessageType.AUDIO.value: ".opus",
            LarkMessageType.MEDIA.value: ".mp4",
        }.get(message_type, "")
        return f"{filename}{suffix}" if suffix else filename

    def _on_card_action(self, conn: _WsConnection, data):
        """Convert card interaction callbacks into regular inbound messages."""
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            P2CardActionTriggerResponse,
        )

        try:
            event = data.event
            action = event.action if event else None
            context = event.context if event else None
            operator = event.operator if event else None
            action_body = {
                "tag": getattr(action, "tag", None),
                "name": getattr(action, "name", None),
                "value": getattr(action, "value", None),
                "form_value": getattr(action, "form_value", None),
                "input_value": getattr(action, "input_value", None),
                "option": getattr(action, "option", None),
                "options": getattr(action, "options", None),
                "checked": getattr(action, "checked", None),
            }
            compact = {key: value for key, value in action_body.items() if value not in (None, "", [], {})}
            content = "[飞书卡片操作]\n" + json.dumps(compact, ensure_ascii=False)
            source = ":".join(
                (
                    str(getattr(context, "open_message_id", "") or ""),
                    str(getattr(event, "token", "") or ""),
                    json.dumps(compact, ensure_ascii=False, sort_keys=True),
                )
            )
            message_id = f"card-action:{uuid.uuid5(uuid.NAMESPACE_URL, source)}"
            chat_id = getattr(context, "open_chat_id", "") or ""
            sender_id = getattr(operator, "open_id", "") or ""
            if conn.on_message and conn.main_loop:
                future = asyncio.run_coroutine_threadsafe(
                    conn.on_message(
                        _inbound_message(
                            conn.channel_id,
                            message_id,
                            content,
                            sender_id,
                            chat_id,
                            [],
                        )
                    ),
                    conn.main_loop,
                )
                future.add_done_callback(
                    lambda f, cid=conn.channel_id: (
                        logger.error(
                            "[Lark-adapter] Card action callback failed: channel=%s",
                            cid,
                            exc_info=f.exception(),
                        )
                        if not f.cancelled() and f.exception() else None
                    )
                )
        except Exception:
            logger.error(
                "[Lark-adapter] Error handling card action: channel=%s",
                conn.channel_id,
                exc_info=True,
            )
        return P2CardActionTriggerResponse()

    # ── Send message ────────────────────────────────────────────

    async def send(
        self, binding: ImBinding, message: OutboundMessage,
    ) -> SendReceipt:
        """Send each segment as its own Lark message, newest id wins."""
        route = message.route
        operation_key = message.idempotency_key or uuid.uuid4().hex
        message_ids: list[str] = []
        for index, segment in enumerate(message.segments):
            message_ids.append(
                await self._send_one(
                    binding,
                    _segment_to_lark_message(segment),
                    route,
                    f"{operation_key}:{index}"
                    if len(message.segments) > 1
                    else operation_key,
                )
            )
        return SendReceipt.of(
            next((mid for mid in reversed(message_ids) if mid), ""),
        )

    async def _send_one(
        self,
        binding: ImBinding,
        message: LarkOutboundMessage,
        route: ChannelRoute,
        idempotency_key: str,
    ) -> str:
        creds = self._get_credentials(binding)
        if not creds:
            raise ChannelRoutingError(
                "Lark credentials are unavailable",
                channel_type=ImChannelType.LARK.value,
            )
        app_id, app_secret, brand = creds

        chat_id = route.group_id
        reply_msg_id = route.reply_to_message_id
        open_id = route.sender_id or binding.config.get("open_id", "")

        # Determine send target: chat_id > open_id
        receive_id = chat_id
        receive_id_type = "chat_id"
        if not receive_id and open_id:
            receive_id = open_id
            receive_id_type = "open_id"

        if not receive_id:
            raise ChannelRoutingError(
                "Cannot send Lark message: no chat or user in routing context. "
                "Send one message from Lark first to establish routing.",
                channel_type=ImChannelType.LARK.value,
            )

        client = self._get_sdk_client(app_id, app_secret, brand)
        encoded_content = await self._prepare_outbound_content(client, message)
        sdk_uuid = (
            str(uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key))
            if idempotency_key
            else ""
        )

        sent = False
        response = None
        if reply_msg_id:
            try:
                response = await self._reply_sdk_message(
                    client,
                    reply_msg_id,
                    message.message_type.value,
                    encoded_content,
                    sdk_uuid,
                )
                sent = True
            except LarkApiError:
                logger.warning(
                    "[Lark-adapter] reply_message failed, falling back to send_message: channel=%s",
                    binding.channel_id,
                    exc_info=True,
                )

        if not sent:
            response = await self._create_sdk_message(
                client,
                receive_id,
                receive_id_type,
                message.message_type.value,
                encoded_content,
                sdk_uuid,
            )

        logger.info(
            "[Lark-adapter] Message sent: channel=%s target=%s reply=%s",
            binding.channel_id,
            receive_id[:8],
            bool(reply_msg_id and sent),
        )
        return str(getattr(getattr(response, "data", None), "message_id", "") or "")

    async def _prepare_outbound_content(
        self,
        client,
        message: LarkOutboundMessage,
    ) -> str:
        if message.message_type in (LarkMessageType.TEXT, LarkMessageType.POST, LarkMessageType.INTERACTIVE):
            return message.encoded_content()
        if not message.file_path:
            raise ValueError(f"{message.message_type.value} message requires file_path")
        prepared = message
        temporary_paths: list[Path] = []
        try:
            if message.message_type is LarkMessageType.IMAGE:
                source = Path(message.file_path)
                declared_suffix = Path(message.resolved_file_name()).suffix
                if not source.suffix and declared_suffix:
                    staged_image = self._temporary_media_path(declared_suffix)
                    shutil.copyfile(source, staged_image)
                    temporary_paths.append(staged_image)
                    from dataclasses import replace

                    prepared = replace(prepared, file_path=str(staged_image))
            if message.message_type in (LarkMessageType.AUDIO, LarkMessageType.MEDIA):
                prepared, temporary_paths = await self._prepare_media_for_lark(message)
            if prepared.message_type is LarkMessageType.IMAGE:
                image_key = await self._upload_image(client, prepared.file_path)
                return prepared.encoded_content(image_key=image_key)

            file_key = await self._upload_file(client, prepared)
            if prepared.message_type is LarkMessageType.MEDIA:
                image_key = prepared.image_key
                if not image_key and prepared.image_path:
                    image_key = await self._upload_image(client, prepared.image_path)
                if not image_key:
                    raise ValueError("video message requires a cover image")
                return prepared.encoded_content(file_key=file_key, image_key=image_key)
            return prepared.encoded_content(file_key=file_key)
        finally:
            for path in temporary_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "[Lark-adapter] Failed to remove temporary media file",
                        exc_info=True,
                    )

    async def _prepare_media_for_lark(
        self,
        message: LarkOutboundMessage,
    ) -> tuple[LarkOutboundMessage, list[Path]]:
        from dataclasses import replace

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to send audio and video to Lark")

        temporary_paths: list[Path] = []
        source = Path(message.file_path)
        prepared = message

        if message.message_type is LarkMessageType.AUDIO and source.suffix.lower() != ".opus":
            output = self._temporary_media_path(".opus")
            temporary_paths.append(output)
            await self._run_ffmpeg(
                ffmpeg,
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "libopus",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(output),
            )
            prepared = replace(prepared, file_path=str(output), file_name=f"{source.stem}.opus")

        if message.message_type is LarkMessageType.MEDIA:
            if source.suffix.lower() != ".mp4":
                output = self._temporary_media_path(".mp4")
                temporary_paths.append(output)
                await self._run_ffmpeg(
                    ffmpeg,
                    "-i",
                    str(source),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(output),
                )
                prepared = replace(
                    prepared,
                    file_path=str(output),
                    file_name=f"{source.stem}.mp4",
                )
            if not prepared.image_key and not prepared.image_path:
                cover = self._temporary_media_path(".png")
                temporary_paths.append(cover)
                await self._run_ffmpeg(
                    ffmpeg,
                    "-i",
                    prepared.file_path,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(1280\\,iw):-2",
                    str(cover),
                )
                prepared = replace(prepared, image_path=str(cover))

        if prepared.duration <= 0:
            duration = await self._probe_media_duration(prepared.file_path)
            if duration > 0:
                prepared = replace(prepared, duration=duration)

        return prepared, temporary_paths

    @staticmethod
    def _temporary_media_path(suffix: str) -> Path:
        file = tempfile.NamedTemporaryFile(
            prefix="velpos-lark-",
            suffix=suffix,
            delete=False,
        )
        file.close()
        return Path(file.name)

    @staticmethod
    async def _run_ffmpeg(ffmpeg: str, *arguments: str) -> None:
        process = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *arguments,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"Failed to prepare media for Lark: {detail}")

    @staticmethod
    async def _probe_media_duration(file_path: str) -> int:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0
        process = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _stderr = await process.communicate()
        if process.returncode != 0:
            return 0
        try:
            return max(0, round(float(stdout.decode("utf-8").strip()) * 1000))
        except ValueError:
            return 0

    async def _upload_image(self, client, file_path: str) -> str:
        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody

        path = Path(file_path)
        if not path.is_file():
            raise ValueError(f"Image file does not exist: {file_path}")
        with path.open("rb") as image:
            body = (
                CreateImageRequestBody.builder()
                .image_type("message")
                .image(image)
                .build()
            )
            request = CreateImageRequest.builder().request_body(body).build()
            response = await client.im.v1.image.acreate(request)
        if not response.success():
            raise self._sdk_error("upload image", response)
        image_key = getattr(getattr(response, "data", None), "image_key", "")
        if not image_key:
            raise LarkApiError("Lark upload image returned no image_key")
        return str(image_key)

    async def _upload_file(self, client, message: LarkOutboundMessage) -> str:
        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody

        path = Path(message.file_path)
        if not path.is_file():
            raise ValueError(f"Media file does not exist: {message.file_path}")
        file_type = self._lark_file_type(message.message_type, path.suffix)
        with path.open("rb") as file:
            builder = (
                CreateFileRequestBody.builder()
                .file_type(file_type)
                .file_name(message.resolved_file_name())
                .file(file)
            )
            if message.duration > 0:
                builder = builder.duration(message.duration)
            request = CreateFileRequest.builder().request_body(builder.build()).build()
            response = await client.im.v1.file.acreate(request)
        if not response.success():
            raise self._sdk_error("upload file", response)
        file_key = getattr(getattr(response, "data", None), "file_key", "")
        if not file_key:
            raise LarkApiError("Lark upload file returned no file_key")
        return str(file_key)

    @staticmethod
    def _lark_file_type(message_type: LarkMessageType, suffix: str) -> str:
        if message_type is LarkMessageType.AUDIO:
            return "opus"
        if message_type is LarkMessageType.MEDIA:
            return "mp4"
        return {
            ".pdf": "pdf",
            ".doc": "doc",
            ".docx": "doc",
            ".xls": "xls",
            ".xlsx": "xls",
            ".ppt": "ppt",
            ".pptx": "ppt",
        }.get(suffix.lower(), "stream")

    async def _create_sdk_message(
        self,
        client,
        receive_id: str,
        receive_id_type: str,
        message_type: str,
        content: str,
        sdk_uuid: str,
    ):
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        body_builder = (
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(message_type)
            .content(content)
        )
        if sdk_uuid:
            body_builder = body_builder.uuid(sdk_uuid)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body_builder.build())
            .build()
        )
        response = await client.im.v1.message.acreate(request)
        if not response.success():
            raise self._sdk_error("send message", response)
        return response

    async def _reply_sdk_message(
        self,
        client,
        message_id: str,
        message_type: str,
        content: str,
        sdk_uuid: str,
    ):
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

        body_builder = (
            ReplyMessageRequestBody.builder()
            .msg_type(message_type)
            .content(content)
        )
        if sdk_uuid:
            body_builder = body_builder.uuid(sdk_uuid)
        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(body_builder.build())
            .build()
        )
        response = await client.im.v1.message.areply(request)
        if not response.success():
            raise self._sdk_error("reply message", response)
        return response

    @staticmethod
    def _sdk_error(operation: str, response) -> LarkApiError:
        code = getattr(response, "code", "")
        message = getattr(response, "msg", "") or "unknown error"
        return LarkApiError(f"Lark {operation} failed: code={code} message={message}")

    async def close(self) -> None:
        """Shutdown adapter — stop all WS listeners."""
        async with self._lock:
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
        creds = self._get_credentials(binding)
        if not creds:
            logger.warning("[Lark-adapter] No credentials for add_reaction")
            return ""
        app_id, app_secret, brand = creds
        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageReactionRequest,
                CreateMessageReactionRequestBody,
                Emoji,
            )

            client = self._get_sdk_client(app_id, app_secret, brand)
            body = (
                CreateMessageReactionRequestBody.builder()
                .reaction_type(Emoji.builder().emoji_type(reaction).build())
                .build()
            )
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            response = await client.im.v1.message_reaction.acreate(request)
            if not response.success():
                raise self._sdk_error("add reaction", response)
            reaction_id = getattr(getattr(response, "data", None), "reaction_id", "")
            logger.info("[Lark-adapter] Reaction added: msg=%s type=%s id=%s", message_id, reaction, reaction_id)
            return str(reaction_id or "")
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
            from lark_oapi.api.im.v1 import DeleteMessageReactionRequest

            client = self._get_sdk_client(app_id, app_secret, brand)
            request = (
                DeleteMessageReactionRequest.builder()
                .message_id(message_id)
                .reaction_id(reaction_id)
                .build()
            )
            response = await client.im.v1.message_reaction.adelete(request)
            if not response.success():
                raise self._sdk_error("remove reaction", response)
            logger.info("[Lark-adapter] Reaction removed: msg=%s id=%s", message_id, reaction_id)
        except Exception:
            logger.warning("[Lark-adapter] remove_reaction failed", exc_info=True)


def _inbound_message(
    channel_id: str,
    message_id: str,
    text: str,
    sender_id: str,
    chat_id: str,
    attachments: list[dict[str, Any]],
) -> InboundMessage:
    return InboundMessage(
        channel_id=channel_id,
        channel_type=ImChannelType.LARK.value,
        external_message_id=message_id,
        route=ChannelRoute(sender_id=sender_id, group_id=chat_id),
        segments=(
            MessageSegment.of_text(text),
            *(MessageSegment.from_attachment(item) for item in attachments),
        ),
    )


_SEGMENT_MESSAGE_TYPE = {
    SegmentType.IMAGE: LarkMessageType.IMAGE,
    SegmentType.AUDIO: LarkMessageType.AUDIO,
    SegmentType.VIDEO: LarkMessageType.MEDIA,
    SegmentType.FILE: LarkMessageType.FILE,
}


def _segment_to_lark_message(segment: MessageSegment) -> LarkOutboundMessage:
    if segment.segment_type is SegmentType.TEXT:
        return LarkOutboundMessage(
            message_type=LarkMessageType.TEXT, content=segment.text,
        )
    if segment.segment_type is SegmentType.CARD:
        return LarkOutboundMessage(
            message_type=LarkMessageType.INTERACTIVE, content=dict(segment.payload),
        )
    if not segment.path:
        raise ValueError("Outbound attachment is missing its local path")
    return LarkOutboundMessage(
        message_type=_SEGMENT_MESSAGE_TYPE[segment.segment_type],
        file_path=segment.path,
        file_name=segment.filename or Path(segment.path).name,
        duration=segment.duration_seconds,
    )
