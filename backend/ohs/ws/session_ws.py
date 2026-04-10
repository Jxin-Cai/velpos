from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from typing import Annotated

from application.session.command.run_query_command import RunQueryCommand
from application.session.session_application_service import SessionApplicationService
from infr.client.connection_manager import ConnectionManager
from infr.client.claude_agent_gateway import ClaudeAgentGateway as ClaudeAgentGatewayImpl
from ohs.assembler.session_assembler import SessionAssembler
from ohs.dependencies import get_session_application_service, get_connection_manager, get_claude_agent_gateway, get_project_application_service
from application.project.project_application_service import ProjectApplicationService

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
ProjectServiceDep = Annotated[
    ProjectApplicationService,
    Depends(get_project_application_service),
]


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    service: ServiceDep,
    manager: ConnectionManagerDep,
    gateway: GatewayDep,
    project_service: ProjectServiceDep,
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

        session_summary = SessionAssembler.to_summary(session)

        # Auto-load git branch for the session's project
        if session.project_id:
            try:
                branch_info = await project_service.list_git_branches(session.project_id)
                session_summary["git_branch"] = branch_info.get("current", "")
            except Exception:
                pass

        # Include effective permission mode so frontend can sync
        session_summary["permission_mode"] = gateway.get_permission_mode(session_id)

        await websocket.send_json({
            "event": "connected",
            "session": session_summary,
            "messages": all_messages,
        })

        # Pre-warm SDK connection in background so first query is faster
        if session.sdk_session_id and not service.is_agent_connected(session_id):
            asyncio.create_task(service.prewarm_connection(session_id))

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "send_prompt":
                prompt = data.get("prompt", "")
                images = data.get("images", [])
                current_session = await service.get_session(session_id)

                # Protect listener sessions from manual input
                if current_session.name.startswith("[SYSTEM] Lark Agent Listener"):
                    await websocket.send_json({
                        "event": "error",
                        "message": "Cannot send prompts to listener session",
                    })
                elif prompt:
                    # Save images to temp files if present (before running check)
                    image_paths = []
                    for img in images:
                        try:
                            img_data = base64.b64decode(img.get("data", ""))
                            media_type = img.get("media_type", "image/png")
                            ext = ".png" if "png" in media_type else ".jpg" if "jpeg" in media_type or "jpg" in media_type else ".webp" if "webp" in media_type else ".png"
                            # Save to project dir's .claude/images/ for better access
                            img_dir = os.path.join(current_session.project_dir, ".claude", "images") if current_session.project_dir else tempfile.gettempdir()
                            os.makedirs(img_dir, exist_ok=True)
                            img_filename = f"vp-img-{uuid.uuid4().hex[:8]}{ext}"
                            img_path = os.path.join(img_dir, img_filename)
                            with open(img_path, "wb") as f:
                                f.write(img_data)
                            image_paths.append(img_path)
                        except Exception as img_err:
                            logger.warning("Failed to save image: %s", img_err)

                    command = RunQueryCommand(
                        session_id=session_id,
                        prompt=prompt,
                        image_paths=image_paths,
                    )

                    if not current_session.is_running:
                        task = asyncio.create_task(service.run_claude_query(command))
                        task.add_done_callback(
                            lambda t: t.exception() and logger.error(
                                "run_claude_query task crashed: %s", t.exception()
                            ) if not t.cancelled() and t.exception() else None
                        )
                    else:
                        # Queue for after current query completes (latest-wins)
                        service.queue_message(session_id, command)
                        await websocket.send_json({
                            "event": "message_queued",
                            "prompt": prompt,
                        })

            elif action == "cancel":
                try:
                    # Run cancel in background — cancel_query handles rewind + broadcast
                    asyncio.create_task(service.cancel_query(session_id))
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
                summary = SessionAssembler.to_summary(current_session)
                if current_session.project_id:
                    try:
                        branch_info = await project_service.list_git_branches(current_session.project_id)
                        summary["git_branch"] = branch_info.get("current", "")
                    except Exception:
                        pass
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
                        summary = SessionAssembler.to_summary(current_session)
                        # Preserve git_branch — it comes from the project repo, not the session
                        if current_session.project_id:
                            try:
                                branch_info = await project_service.list_git_branches(current_session.project_id)
                                summary["git_branch"] = branch_info.get("current", "")
                            except Exception:
                                pass
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
