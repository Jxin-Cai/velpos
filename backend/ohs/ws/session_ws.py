from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from typing import Annotated, Awaitable, Callable

from application.message.attachment_application_service import AttachmentApplicationService
from application.session.command.run_query_command import RunQueryCommand
from application.session.session_application_service import SessionApplicationService
from application.terminal.terminal_application_service import TerminalApplicationService
from domain.shared.async_utils import safe_create_task
from domain.shared.business_exception import BusinessException
from infr.client.connection_manager import ConnectionManager
from infr.client.claude_agent_gateway import ClaudeAgentGateway as ClaudeAgentGatewayImpl
from ohs.assembler.session_assembler import SessionAssembler
from application.team_board.team_board_service import TeamBoardApplicationService
from ohs.dependencies import get_session_application_service, get_connection_manager, get_claude_agent_gateway, get_attachment_application_service, get_terminal_application_service, get_create_session_service_factory, get_team_board_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


ServiceDep = Annotated[
    SessionApplicationService,
    Depends(get_session_application_service),
]
ConnectionManagerDep = Annotated[
    ConnectionManager,
    Depends(get_connection_manager),
]
GatewayDep = Annotated[
    ClaudeAgentGatewayImpl,
    Depends(get_claude_agent_gateway),
]
SessionServiceFactoryDep = Annotated[
    Callable[[], Awaitable[SessionApplicationService]],
    Depends(get_create_session_service_factory),
]
AttachmentServiceDep = Annotated[
    AttachmentApplicationService,
    Depends(get_attachment_application_service),
]
TerminalServiceDep = Annotated[
    TerminalApplicationService,
    Depends(get_terminal_application_service),
]
TeamServiceDep = Annotated[
    TeamBoardApplicationService,
    Depends(get_team_board_service),
]


@dataclasses.dataclass
class _WsContext:
    """Holds shared dependencies for WebSocket action handlers."""

    websocket: WebSocket
    session_id: str
    service: SessionApplicationService
    manager: ConnectionManager
    gateway: ClaudeAgentGatewayImpl
    session_service_factory: Callable[[], Awaitable[SessionApplicationService]]
    attachment_service: AttachmentApplicationService
    team_service: TeamBoardApplicationService
    build_session_summary: Callable[..., Awaitable[dict]]
    submit_query_background: Callable[[RunQueryCommand], Awaitable[None]]


async def _handle_send_prompt(ctx: _WsContext, data: dict) -> None:
    prompt = data.get("prompt", "")
    images = data.get("images", [])
    incoming_attachments = list(data.get("attachments") or [])
    for img in images:
        incoming_attachments.append({
            "name": img.get("name") or f"image-{uuid.uuid4().hex[:8]}.png",
            "mime_type": img.get("media_type", "image/png"),
            "data": img.get("data", ""),
        })
    current_session = await ctx.service.get_session(ctx.session_id)

    # Protect listener sessions from manual input
    if current_session.name.startswith("[SYSTEM] Lark Agent Listener"):
        await ctx.websocket.send_json({
            "event": "error",
            "message": "Cannot send prompts to listener session",
        })
    elif prompt or incoming_attachments:
        saved_attachments = []
        image_paths = []
        for item in incoming_attachments:
            try:
                raw_data = item.get("data", "")
                if "," in raw_data and raw_data.startswith("data:"):
                    raw_data = raw_data.split(",", 1)[1]
                mime_type = item.get("mime_type") or item.get("media_type") or "application/octet-stream"
                attachment = await ctx.attachment_service.save_base64_attachment(
                    project_id=current_session.project_id,
                    session_id=ctx.session_id,
                    project_dir=current_session.project_dir,
                    filename=item.get("name") or item.get("filename") or "attachment.bin",
                    mime_type=mime_type,
                    data_base64=raw_data,
                )
                ref = attachment.to_message_ref()
                saved_attachments.append(ref)
                if mime_type.startswith("image/"):
                    image_paths.append(ref["path"])
            except Exception as attachment_err:
                logger.warning("Failed to save attachment: %s", attachment_err)

        command = RunQueryCommand(
            session_id=ctx.session_id,
            prompt=prompt or "Please review the attached files.",
            client_message_id=str(data.get("message_id", ""))[:64],
            image_paths=image_paths,
            attachments=saved_attachments,
        )

        if not current_session.is_running:
            safe_create_task(
                ctx.submit_query_background(command),
                name=f"run_claude_query_{ctx.session_id}",
            )
        elif not ctx.service.is_agent_connected(ctx.session_id):
            await ctx.service.ensure_session_idle(ctx.session_id)
            await ctx.websocket.send_json({
                "event": "prompt_started",
                "message_id": command.client_message_id,
                "prompt": prompt,
                "image_count": len(image_paths),
                "attachments": [
                    {
                        "filename": item.get("filename", "attachment"),
                        "mime_type": item.get("mime_type", "application/octet-stream"),
                        "size_bytes": item.get("size_bytes", 0),
                    }
                    for item in saved_attachments
                ],
            })
            safe_create_task(
                ctx.submit_query_background(command),
                name=f"run_claude_query_{ctx.session_id}",
            )
        else:
            # Queue for after current query completes (latest-wins)
            await ctx.service.queue_message(ctx.session_id, command)
            await ctx.websocket.send_json({
                "event": "message_queued",
                "message_id": command.client_message_id,
                "prompt": prompt,
                "image_count": len(image_paths),
                "attachment_count": len(saved_attachments),
            })


async def _handle_clear_queue(ctx: _WsContext, data: dict) -> None:
    await ctx.service.clear_queued_message(ctx.session_id)
    await ctx.websocket.send_json({"event": "queue_cleared"})


async def _handle_steer_queue(ctx: _WsContext, data: dict) -> None:
    try:
        result = await ctx.service.steer_queued_message(ctx.session_id)
        await ctx.websocket.send_json({"event": "message_steered", **result})
    except BusinessException as exc:
        await ctx.websocket.send_json({"event": "steer_failed", "message": str(exc)})
    except Exception:
        logger.exception("[session=%s] steer queued message failed", ctx.session_id)
        await ctx.websocket.send_json({
            "event": "steer_failed",
            "message": "Unable to steer the queued message; it remains queued",
        })


async def _handle_cancel(ctx: _WsContext, data: dict) -> None:
    try:
        async def _cancel_background() -> None:
            bg_svc = await ctx.session_service_factory()
            try:
                await bg_svc.cancel_query(ctx.session_id)
            finally:
                await bg_svc.close()

        safe_create_task(_cancel_background())
        await ctx.websocket.send_json({
            "event": "info",
            "message": "Cancelling...",
        })
    except Exception as e:
        await ctx.websocket.send_json({
            "event": "error",
            "message": str(e),
        })


async def _handle_rewind_to(ctx: _WsContext, data: dict) -> None:
    message_id = data.get("message_id")
    message_index = data.get("message_index")
    if not message_id and message_index is None:
        await ctx.websocket.send_json({
            "event": "error",
            "message": "message_id or message_index is required",
        })
    else:
        async def _rewind_background(target_message_id=message_id, target_message_index=message_index) -> None:
            bg_service = await ctx.session_service_factory()
            try:
                if target_message_id:
                    await bg_service.rewind_to_message_id(ctx.session_id, str(target_message_id))
                else:
                    await bg_service.rewind_to_message(ctx.session_id, int(target_message_index))
            except Exception as e:
                try:
                    await ctx.websocket.send_json({
                        "event": "error",
                        "message": str(e),
                    })
                except Exception:
                    pass
            finally:
                await bg_service.close()

        safe_create_task(_rewind_background())
        await ctx.websocket.send_json({
            "event": "info",
            "message": "Rewinding...",
        })


async def _handle_get_status(ctx: _WsContext, data: dict) -> None:
    current_session = await ctx.service.get_session(ctx.session_id)
    summary = await ctx.build_session_summary(ctx.service, current_session)
    await ctx.websocket.send_json({
        "event": "status",
        "session": summary,
    })


async def _handle_set_model(ctx: _WsContext, data: dict) -> None:
    model = data.get("model", "")
    if model:
        try:
            await ctx.service.set_model(ctx.session_id, model)
            current_session = await ctx.service.get_session(ctx.session_id)
            summary = await ctx.build_session_summary(
                ctx.service, current_session, include_agent_state=True,
            )
            await ctx.websocket.send_json({
                "event": "status",
                "session": summary,
            })
        except Exception as e:
            await ctx.websocket.send_json({
                "event": "error",
                "message": str(e),
            })


async def _handle_set_permission_mode(ctx: _WsContext, data: dict) -> None:
    mode = data.get("mode", "")
    if mode:
        try:
            await ctx.service.set_permission_mode(ctx.session_id, mode)
        except WebSocketDisconnect:
            raise
        except Exception as e:
            await ctx.websocket.send_json({
                "event": "error",
                "message": str(e),
            })
            return
        await ctx.websocket.send_json({
            "event": "info",
            "message": f"Permission mode changed to {mode}",
        })


async def _handle_user_response(ctx: _WsContext, data: dict) -> None:
    # Handle user choice answers (AskUserQuestion) or permission decisions (Allow/Deny)
    response_data = data.get("data", {})
    resolved = await ctx.service.resolve_user_response(ctx.session_id, response_data)
    if not resolved:
        await ctx.websocket.send_json({
            "event": "info",
            "message": "No pending request to respond to",
        })


_ACTION_HANDLERS: dict[str, Callable[[_WsContext, dict], Awaitable[None]]] = {
    "send_prompt": _handle_send_prompt,
    "clear_queue": _handle_clear_queue,
    "steer_queue": _handle_steer_queue,
    "cancel": _handle_cancel,
    "rewind_to": _handle_rewind_to,
    "get_status": _handle_get_status,
    "set_model": _handle_set_model,
    "set_permission_mode": _handle_set_permission_mode,
    "user_response": _handle_user_response,
}


@router.websocket("/ws/terminal")
async def terminal_websocket_endpoint(
    websocket: WebSocket,
    terminal_service: TerminalServiceDep,
) -> None:
    await websocket.accept()
    init = await websocket.receive_json()
    cwd = init.get("cwd") if isinstance(init, dict) else None
    cols = int(init.get("cols") or 120) if isinstance(init, dict) else 120
    rows = int(init.get("rows") or 30) if isinstance(init, dict) else 30
    terminal = await terminal_service.create_pty(cwd=cwd, cols=cols, rows=rows)
    terminal_id = terminal["terminal_id"]
    await websocket.send_json({"event": "ready", **terminal})

    async def relay_output() -> None:
        while True:
            chunk = await terminal_service.read_pty(terminal_id)
            if not chunk:
                await websocket.send_json({"event": "closed"})
                break
            await websocket.send_json({"event": "output", "data": chunk})

    output_task = asyncio.create_task(relay_output())
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "input":
                await terminal_service.write_pty(terminal_id, data.get("data") or "")
            elif action == "resize":
                await terminal_service.resize_pty(
                    terminal_id,
                    int(data.get("cols") or 120),
                    int(data.get("rows") or 30),
                )
            elif action == "close":
                break
    except WebSocketDisconnect:
        pass
    finally:
        output_task.cancel()
        with contextlib.suppress(Exception):
            await output_task
        await terminal_service.close_pty(terminal_id)


@router.websocket("/ws/events")
async def global_events_endpoint(
    websocket: WebSocket,
    manager: ConnectionManagerDep,
) -> None:
    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_global(websocket)


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    service: ServiceDep,
    manager: ConnectionManagerDep,
    gateway: GatewayDep,
    session_service_factory: SessionServiceFactoryDep,
    attachment_service: AttachmentServiceDep,
    team_service: TeamServiceDep,
) -> None:
    # Accept WebSocket first to avoid 403 on handshake rejection.
    # Errors are delivered as WebSocket events so the client gets proper close codes.
    await manager.connect(websocket, session_id)
    logger.info("websocket_connected", extra={"session_id": session_id})

    async def _build_session_summary(
        svc: SessionApplicationService,
        sess,
        *,
        include_permission: bool = True,
        include_agent_state: bool = False,
    ) -> dict:
        summary = SessionAssembler.to_summary(
            sess,
            git_branch=await svc.get_current_git_branch(sess.project_dir),
        )
        if include_permission:
            summary["permission_mode"] = gateway.get_permission_mode(session_id)
        summary["waiting_for_slot"] = await svc.is_waiting_for_slot(session_id)
        if include_agent_state:
            summary["agent_state"] = svc.get_agent_state(session_id)
        return summary

    try:
        try:
            session = await service.get_session(session_id)
        except BusinessException:
            await websocket.send_json({"event": "error", "message": "Session not found"})
            await websocket.close(code=4004, reason="Session not found")
            return
        except Exception:
            logger.exception("ws: failed to load session %s", session_id)
            await websocket.send_json({"event": "error", "message": "Failed to load session"})
            await websocket.close(code=4004, reason="Session load failed")
            return

        # Correct stale "running" status when SDK client is not connected
        # (e.g., after server restart)
        if session.is_running and not service.is_agent_connected(session_id):
            await service.ensure_session_idle(session_id)
            session = await service.get_session(session_id)
            logger.info("corrected stale running status for session=%s", session_id)

        # Note: We do NOT promote idle→running when is_connected is True.
        # is_connected only means a persistent SDK client exists, not that
        # a query is actively streaming. The actual running state is set by
        # run_claude_query's start_query() call.

        message_page = SessionAssembler.message_page(session.messages)
        recent_messages = message_page["messages"]
        result_count = sum(1 for msg in session.messages if msg.message_type.value == "result")
        logger.info(
            "ws connected: session=%s, messages=%d/%d, result_messages=%d",
            session_id, len(recent_messages), len(session.messages), result_count,
        )

        git_branch = await service.get_current_git_branch(session.project_dir)
        session_summary = SessionAssembler.to_summary(session, git_branch=git_branch)

        # Include effective permission mode so frontend can sync
        session_summary["permission_mode"] = gateway.get_permission_mode(session_id)
        session_summary["waiting_for_slot"] = await service.is_waiting_for_slot(session_id)
        session_summary["agent_state"] = service.get_agent_state(session_id)

        await websocket.send_json({
            "event": "connected",
            "session": session_summary,
            "messages": recent_messages,
            "message_window": message_page["message_window"],
            "user_message_markers": SessionAssembler.user_message_markers(session.messages),
        })

        async def _with_background_service(
            handler: Callable[[SessionApplicationService], Awaitable[None]],
        ) -> None:
            bg_service = await session_service_factory()
            try:
                await handler(bg_service)
            finally:
                await bg_service.close()

        async def _refresh_context_after_connect() -> None:
            try:
                async def _refresh(bg_service: SessionApplicationService) -> None:
                    refreshed = await bg_service.refresh_context_usage(session_id)
                    refreshed_summary = await _build_session_summary(
                        bg_service, refreshed, include_agent_state=True,
                    )
                    await manager.broadcast(session_id, {
                        "event": "status",
                        "session": refreshed_summary,
                    })

                await _with_background_service(_refresh)
            except Exception as e:
                logger.info("[session=%s] context refresh after connect skipped: %s", session_id, e)

        safe_create_task(_refresh_context_after_connect())

        # Replay pending permission/choice request if query is waiting for user input
        pending_ctx = await gateway.get_pending_request_context(session_id)
        if pending_ctx:
            tool_name = pending_ctx.get("tool_name", "")
            if tool_name == "AskUserQuestion":
                await websocket.send_json({
                    "event": "user_choice_request",
                    "tool_name": tool_name,
                    "questions": pending_ctx.get("questions", []),
                })
            else:
                await websocket.send_json({
                    "event": "permission_request",
                    "tool_name": tool_name,
                    "tool_input": pending_ctx.get("tool_input", ""),
                })

        # Pre-warm SDK connection in background so first query is faster
        if session.sdk_session_id and not service.is_agent_connected(session_id):
            async def _prewarm_background() -> None:
                bg_svc = await session_service_factory()
                try:
                    await bg_svc.prewarm_connection(session_id)
                finally:
                    await bg_svc.close()

            safe_create_task(_prewarm_background())

        async def _submit_query_background(command: RunQueryCommand) -> None:
            bg_service = await session_service_factory()
            try:
                await bg_service.submit_query(command)
            finally:
                await bg_service.close()

        ctx = _WsContext(
            websocket=websocket,
            session_id=session_id,
            service=service,
            manager=manager,
            gateway=gateway,
            session_service_factory=session_service_factory,
            attachment_service=attachment_service,
            team_service=team_service,
            build_session_summary=_build_session_summary,
            submit_query_background=_submit_query_background,
        )

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            handler = _ACTION_HANDLERS.get(action)
            if handler:
                await handler(ctx, data)

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", extra={"session_id": session_id})
    except Exception:
        logger.exception("websocket_error", extra={"session_id": session_id})
    finally:
        await manager.disconnect(websocket, session_id)
        with contextlib.suppress(Exception):
            await service.rollback()
        # Schedule idle cleanup when last WS client disconnects
        if not await manager.has_connections(session_id):
            gateway.schedule_idle_disconnect(session_id)
