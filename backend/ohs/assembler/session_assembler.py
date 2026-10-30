from __future__ import annotations

from typing import Any

from application.session.session_presenter import SessionPresenter
from domain.session.model.message import Message
from domain.session.model.session import Session


class SessionAssembler:
    DEFAULT_MESSAGE_PAGE_SIZE = SessionPresenter.DEFAULT_MESSAGE_PAGE_SIZE

    @staticmethod
    def _recovery_to_dict(session: Session) -> dict[str, Any]:
        return SessionPresenter.recovery_to_dict(session)

    @staticmethod
    def _public_sdk_session_id(sdk_session_id: str) -> str:
        return SessionPresenter.public_sdk_session_id(sdk_session_id)

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
            "trace_id": session.trace_id or "",
            "recovery": SessionAssembler._recovery_to_dict(session),
        }

    @staticmethod
    def message_page(
        messages: list[Message],
        *,
        before: int | None = None,
        limit: int = DEFAULT_MESSAGE_PAGE_SIZE,
    ) -> dict[str, Any]:
        return SessionPresenter.message_page(messages, before=before, limit=limit)

    @staticmethod
    def user_message_markers(messages: list[Message]) -> list[dict[str, Any]]:
        return SessionPresenter.user_message_markers(messages)
