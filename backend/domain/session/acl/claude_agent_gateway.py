from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class ClaudeAgentGateway(ABC):

    @abstractmethod
    async def connect(
        self,
        session_id: str,
        model: str,
        prompt: str,
        cwd: str = "",
        sdk_session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Connect to Claude and send initial query, returning a persistent message stream.

        Creates a long-lived SDK client bound to the session. The returned
        iterator yields messages via receive_messages() until the session
        is disconnected.

        Args:
            session_id: Session identifier for client lifecycle management.
            model: Claude model name.
            prompt: Initial user prompt text.
            cwd: Working directory for Claude Agent SDK.
            sdk_session_id: Resume selector. None means gateway may use its in-memory
                cache; an empty string forces a fresh Claude Code session; a real UUID
                resumes that session. A value in the form fork:<sdk-session-id> means
                the connection should fork from that source Claude Code session before
                running the prompt.

        Yields:
            dict with message_type, content, and optionally input_tokens/output_tokens
            and sdk_session_id.
        """
        ...

    @abstractmethod
    async def send_query(
        self,
        session_id: str,
        prompt: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a follow-up query on an existing connection.

        Reuses the long-lived SDK client for this session.

        Args:
            session_id: Session identifier.
            prompt: User prompt text.

        Yields:
            dict with message_type, content, and optionally input_tokens/output_tokens.
        """
        ...

    @abstractmethod
    async def interrupt(self, session_id: str) -> None:
        """Send interrupt signal to an active Claude query.

        Args:
            session_id: Session identifier.
        """
        ...

    @abstractmethod
    async def disconnect(self, session_id: str) -> None:
        """Disconnect and cleanup the SDK client for a session.

        Args:
            session_id: Session identifier.
        """
        ...

    @abstractmethod
    async def set_model(self, session_id: str, model: str) -> None:
        """Change the model for an active session.

        Args:
            session_id: Session identifier.
            model: New model name.
        """
        ...

    @abstractmethod
    async def set_permission_mode(self, session_id: str, mode: str) -> None:
        """Change the permission mode for an active session.

        Args:
            session_id: Session identifier.
            mode: New permission mode.
        """
        ...

    @abstractmethod
    def is_connected(self, session_id: str) -> bool:
        """Check if a session has an active SDK client.

        Args:
            session_id: Session identifier.
        """
        ...

    @abstractmethod
    async def open_connection(
        self,
        session_id: str,
        model: str,
        cwd: str = "",
        sdk_session_id: str | None = None,
    ) -> None:
        """Open a persistent SDK connection without sending a query.

        Creates a long-lived SDK client bound to the session.
        Subsequent prompts can be sent via send_query().

        Args:
            session_id: Session identifier for client lifecycle management.
            model: Claude model name.
            cwd: Working directory for Claude Agent SDK.
            sdk_session_id: Resume selector. None means gateway may use its in-memory
                cache; an empty string forces a fresh Claude Code session; a real UUID
                resumes that session. A value in the form fork:<sdk-session-id> means
                the connection should fork from that source Claude Code session before
                running the prompt.
        """
        ...

    def get_permission_mode(self, session_id: str) -> str:
        """Return the effective permission mode for a session.

        Returns the session-specific override if set, otherwise the global default.

        Args:
            session_id: Session identifier.
        """
        return "bypassPermissions"

    def get_connected_model(self, session_id: str) -> str | None:
        """Return the model used for the current connection, or None if not connected.

        Args:
            session_id: Session identifier.
        """
        return None

    @abstractmethod
    def delete_session_files(self, session_id: str, project_dir: str) -> None:
        """Delete Claude Code JSONL session files for a session.

        Args:
            session_id: Session identifier.
            project_dir: Project directory path.
        """
        ...

    def cleanup_session(self, session_id: str) -> None:
        """Remove all tracked state for a session after full deletion.

        Args:
            session_id: Session identifier.
        """
        pass

    @abstractmethod
    async def compact(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Compact session context via Claude Agent SDK.

        Calls the SDK compact functionality to reduce session token usage.
        Requires the session_id to have an active SDK client connection.

        Args:
            session_id: Session identifier.

        Yields:
            dict with message_type, content, usage fields, and optionally sdk_session_id.

        Raises:
            RuntimeError: If no SDK client is connected for the session.
        """
        ...

    @abstractmethod
    async def get_models(self) -> list[dict[str, Any]]:
        """Get available models from Claude Code.

        Returns a list of model dicts with at least 'value' and 'displayName'.
        """
        ...

    async def get_context_usage(self, session_id: str) -> dict[str, Any] | None:
        """Return live Claude Code context usage for an active session if supported."""
        return None

    async def resolve_user_response(self, session_id: str, response_data: dict[str, Any]) -> bool:
        """Resolve a pending user response (choice answer or permission decision).

        Returns True if a pending response was resolved, False if none was pending.
        """
        return False

    def mark_active(self, session_id: str) -> None:
        """Mark a session as actively running a query.

        Active sessions will not be disconnected by idle cleanup.
        """
        pass

    def mark_idle(self, session_id: str) -> None:
        """Mark a session as no longer actively running a query."""
        pass

    def is_active(self, session_id: str) -> bool:
        """Check if a session is actively running a query."""
        return False

    def schedule_idle_disconnect(self, session_id: str, delay: float | None = None) -> None:
        """Schedule a delayed disconnect for an idle session.

        If no activity occurs before the delay, the SDK client is disconnected.
        """
        pass

    async def disconnect_all(self) -> None:
        """Disconnect all active SDK clients (used during server shutdown)."""
        pass
