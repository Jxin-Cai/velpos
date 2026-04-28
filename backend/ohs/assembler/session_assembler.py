from __future__ import annotations

from typing import Any

from domain.session.model.message import Message
from domain.session.model.session import Session
from domain.session.model.usage import Usage


class SessionAssembler:
    @staticmethod
    def _recovery_to_dict(session: Session) -> dict[str, Any]:
        pending_request = session.pending_request_context
        queued_command = session.queued_command

        pending_summary = None
        if pending_request:
            tool_name = pending_request.get("tool_name", "")
            if tool_name == "AskUserQuestion":
                pending_summary = {
                    "interaction_type": "user_choice",
                    "tool_name": tool_name,
                    "questions": pending_request.get("questions", []),
                }
            else:
                pending_summary = {
                    "interaction_type": "permission",
                    "tool_name": tool_name,
                    "tool_input": pending_request.get("tool_input", ""),
                }

        queued_summary = None
        if queued_command:
            queued_summary = {
                "prompt": queued_command.get("prompt", ""),
                "image_count": len(queued_command.get("image_paths", [])),
            }

        return {
            "pending_request": pending_summary,
            "queued_command": queued_summary,
            "cancel_requested": session.cancel_requested,
        }

    @staticmethod
    def _public_sdk_session_id(sdk_session_id: str) -> str:
        return "" if sdk_session_id.startswith("fork:") else sdk_session_id

    @staticmethod
    def to_summary(session: Session, git_branch: str = "") -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "model": session.model,
            "status": session.status.value,
            "message_count": session.message_count,
            "usage": {
                "input_tokens": session.usage.input_tokens,
                "output_tokens": session.usage.output_tokens,
            },
            "last_input_tokens": session.last_input_tokens,
            "project_dir": session.project_dir,
            "name": session.name,
            "sdk_session_id": SessionAssembler._public_sdk_session_id(session.sdk_session_id),
            "updated_time": session.updated_time.isoformat() if session.updated_time else None,
            "git_branch": git_branch,
            "recovery": SessionAssembler._recovery_to_dict(session),
        }

    @staticmethod
    def message_to_dict(message: Message) -> dict[str, Any]:
        return {"type": message.message_type.value, "content": message.content}

    @staticmethod
    def usage_to_dict(usage: Usage) -> dict[str, int]:
        return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
