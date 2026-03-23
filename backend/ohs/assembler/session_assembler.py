from __future__ import annotations

from typing import Any

from domain.session.model.message import Message
from domain.session.model.session import Session
from domain.session.model.usage import Usage


class SessionAssembler:
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
            "sdk_session_id": session.sdk_session_id,
            "updated_time": session.updated_time.isoformat() if session.updated_time else None,
            "git_branch": git_branch,
        }

    @staticmethod
    def message_to_dict(message: Message) -> dict[str, Any]:
        return {"type": message.message_type.value, "content": message.content}

    @staticmethod
    def usage_to_dict(usage: Usage) -> dict[str, int]:
        return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
