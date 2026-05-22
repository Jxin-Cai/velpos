from __future__ import annotations

import re
from typing import Any

from domain.session.model.session import Session


class SessionPresenter:

    @staticmethod
    def public_sdk_session_id(sdk_session_id: str) -> str:
        return "" if sdk_session_id.startswith("fork:") else sdk_session_id

    @staticmethod
    def recovery_to_dict(session: Session) -> dict[str, Any]:
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
                "attachment_count": len(queued_command.get("attachments", [])),
            }

        return {
            "pending_request": pending_summary,
            "queued_command": queued_summary,
            "cancel_requested": session.cancel_requested,
        }

    @staticmethod
    def session_to_dict(session: Session) -> dict[str, Any]:
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
            "sdk_session_id": SessionPresenter.public_sdk_session_id(session.sdk_session_id),
            "updated_time": session.updated_time.isoformat() if session.updated_time else None,
            "git_branch": "",
            "recovery": SessionPresenter.recovery_to_dict(session),
        }

    @staticmethod
    def artifact_candidates_from_value(value: Any) -> list[str]:
        candidates: list[str] = []
        if isinstance(value, str):
            candidates.extend(
                match.group(0).rstrip('.,:;)]}"\'')
                for match in re.finditer(r"(?:/|~/?|\./|\.\./)[^\s`'\"<>]+", value)
            )
        elif isinstance(value, dict):
            for key, nested in value.items():
                if key in {"file_path", "path", "paths", "filename", "output_file"}:
                    candidates.extend(SessionPresenter.artifact_candidates_from_value(nested))
                elif isinstance(nested, (dict, list)):
                    candidates.extend(SessionPresenter.artifact_candidates_from_value(nested))
        elif isinstance(value, list):
            for item in value:
                candidates.extend(SessionPresenter.artifact_candidates_from_value(item))
        return candidates

    @staticmethod
    def artifact_label(path: str) -> str:
        clean = path.rstrip("/")
        return clean.split("/")[-1] or clean
