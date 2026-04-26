from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from typing import Annotated

from application.message.attachment_application_service import AttachmentApplicationService
from application.session.command.run_query_command import RunQueryCommand
from application.session.session_application_service import SessionApplicationService
from domain.shared.async_utils import safe_create_task
from infr.client.connection_manager import ConnectionManager
from infr.client.claude_agent_gateway import ClaudeAgentGateway as ClaudeAgentGatewayImpl
from ohs.assembler.session_assembler import SessionAssembler
from ohs.dependencies import get_session_application_service, get_connection_manager, get_claude_agent_gateway, get_attachment_application_service

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
AttachmentServiceDep = Annotated[
    AttachmentApplicationService,
    Depends(get_attachment_application_service),
]


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
        manager.disconnect_global(websocket)


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    service: ServiceDep,
    manager: ConnectionManagerDep,
    gateway: GatewayDep,
    attachment_service: AttachmentServiceDep,
) -> None:
    from domain.shared.business_exception import BusinessException

    # Accept WebSocket first to avoid 403 on handshake rejection.
    # Errors are delivered as WebSocket events so the client gets proper close codes.
    await manager.connect(websocket, session_id)
    logger.info("websocket_connected", extra={"session_id": session_id})

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

        all_messages = [SessionAssembler.message_to_dict(msg) for msg in session.messages]
        result_count = sum(1 for msg in session.messages if msg.message_type.value == "result")
        logger.info(
            "ws connected: session=%s, messages=%d, result_messages=%d",
            session_id, len(all_messages), result_count,
        )

        git_branch = await service.get_current_git_branch(session.project_dir)
        session_summary = SessionAssembler.to_summary(session, git_branch=git_branch)

        # Include effective permission mode so frontend can sync
        session_summary["permission_mode"] = gateway.get_permission_mode(session_id)
        session_summary["waiting_for_slot"] = service.is_waiting_for_slot(session_id)

        await websocket.send_json({
            "event": "connected",
            "session": session_summary,
            "messages": all_messages,
        })

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
            async def _prewarm_loaded_session() -> None:
                try:
                    await gateway.open_connection(
                        session_id=session_id,
                        model=session.model,
                        cwd=session.project_dir,
                        sdk_session_id=session.sdk_session_id,
                    )
                    logger.info("[session=%s] SDK 连接预热完成", session_id)
                except Exception as e:
                    logger.warning("[session=%s] SDK 连接预热失败: %s", session_id, e)

            safe_create_task(_prewarm_loaded_session())

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "send_prompt":
                prompt = data.get("prompt", "")
                images = data.get("images", [])
                incoming_attachments = list(data.get("attachments") or [])
                for img in images:
                    incoming_attachments.append({
                        "name": img.get("name") or f"image-{uuid.uuid4().hex[:8]}.png",
                        "mime_type": img.get("media_type", "image/png"),
                        "data": img.get("data", ""),
                    })
                current_session = await service.get_session(session_id)

                # Protect listener sessions from manual input
                if current_session.name.startswith("[SYSTEM] Lark Agent Listener"):
                    await websocket.send_json({
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
                            attachment = await attachment_service.save_base64_attachment(
                                project_id=current_session.project_id,
                                session_id=session_id,
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
                        session_id=session_id,
                        prompt=prompt or "Please review the attached files.",
                        image_paths=image_paths,
                        attachments=saved_attachments,
                    )

                    if not current_session.is_running:
                        task = asyncio.create_task(service.submit_query(command))
                        task.add_done_callback(
                            lambda t: t.exception() and logger.error(
                                "run_claude_query task crashed: %s", t.exception()
                            ) if not t.cancelled() and t.exception() else None
                        )
                    else:
                        # Queue for after current query completes (latest-wins)
                        await service.queue_message(session_id, command)
                        await websocket.send_json({
                            "event": "message_queued",
                            "prompt": prompt,
                        })

            elif action == "cancel":
                try:
                    # Run cancel in background — cancel_query handles rewind + broadcast
                    safe_create_task(service.cancel_query(session_id))
                    # Immediately signal cancellation is in progress
                    await websocket.send_json({
                        "event": "info",
                        "message": "Cancelling...",
                    })
                except Exception as e:
                    await websocket.send_json({
                        "event": "error",
                        "message": str(e),
                    })

            elif action == "get_status":
                current_session = await service.get_session(session_id)
                summary = SessionAssembler.to_summary(
                    current_session,
                    git_branch=await service.get_current_git_branch(current_session.project_dir),
                )
                summary["waiting_for_slot"] = service.is_waiting_for_slot(session_id)
                await websocket.send_json({
                    "event": "status",
                    "session": summary,
                })

            elif action == "set_model":
                model = data.get("model", "")
                if model:
                    try:
                        await service.set_model(session_id, model)
                        current_session = await service.get_session(session_id)
                        summary = SessionAssembler.to_summary(
                            current_session,
                            git_branch=await service.get_current_git_branch(current_session.project_dir),
                        )
                        summary["waiting_for_slot"] = service.is_waiting_for_slot(session_id)
                        await websocket.send_json({
                            "event": "status",
                            "session": summary,
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "event": "error",
                            "message": str(e),
                        })

            elif action == "set_permission_mode":
                mode = data.get("mode", "")
                if mode:
                    try:
                        await service.set_permission_mode(session_id, mode)
                        await websocket.send_json({
                            "event": "info",
                            "message": f"Permission mode changed to {mode}",
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "event": "error",
                            "message": str(e),
                        })

            elif action == "user_response":
                # Handle user choice answers (AskUserQuestion) or permission decisions (Allow/Deny)
                response_data = data.get("data", {})
                resolved = await service.resolve_user_response(session_id, response_data)
                if not resolved:
                    await websocket.send_json({
                        "event": "info",
                        "message": "No pending request to respond to",
                    })

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", extra={"session_id": session_id})
    except Exception:
        logger.exception("websocket_error", extra={"session_id": session_id})
    finally:
        manager.disconnect(websocket, session_id)
        # Schedule idle cleanup when last WS client disconnects
        if not manager.has_connections(session_id):
            gateway.schedule_idle_disconnect(session_id)
