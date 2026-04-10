from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from domain.session.model.message import Message
from domain.session.model.session_status import SessionStatus
from domain.session.model.usage import Usage


@dataclass
class Session:
    _session_id: str
    _model: str
    _status: SessionStatus
    _messages: list[Message] = field(default_factory=list)
    _usage: Usage = field(default_factory=Usage.zero)
    _continue_conversation: bool = False
    _project_id: str = ""
    _project_dir: str = ""
    _name: str = ""
    _sdk_session_id: str = ""
    _last_input_tokens: int = 0
    _updated_time: datetime | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def model(self) -> str:
        return self._model

    @property
    def status(self) -> SessionStatus:
        return self._status

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    @property
    def usage(self) -> Usage:
        return self._usage

    @property
    def continue_conversation(self) -> bool:
        return self._continue_conversation

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def project_dir(self) -> str:
        """返回会话绑定的项目目录全路径。"""
        return self._project_dir

    @property
    def name(self) -> str:
        return self._name

    @property
    def sdk_session_id(self) -> str:
        return self._sdk_session_id

    @property
    def last_input_tokens(self) -> int:
        return self._last_input_tokens

    @property
    def updated_time(self) -> datetime | None:
        return self._updated_time

    @property
    def is_running(self) -> bool:
        return self._status == SessionStatus.RUNNING

    @property
    def is_compacting(self) -> bool:
        return self._status == SessionStatus.COMPACTING

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @classmethod
    def create(
        cls,
        model: str = "",
        project_id: str = "",
        project_dir: str = "",
    ) -> Session:
        """Create a new Session.

        Generates an 8-character UUID prefix as session_id.
        Initial status is IDLE, messages list is empty, usage is zero,
        continue_conversation is False.
        project_id ties this session to a Project aggregate.
        project_dir is optional; empty string means no specific directory binding.
        """
        session_id = uuid.uuid4().hex[:8]
        if not model:
            model = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
        return cls(
            _session_id=session_id,
            _model=model,
            _status=SessionStatus.IDLE,
            _messages=[],
            _usage=Usage.zero(),
            _continue_conversation=False,
            _project_id=project_id,
            _project_dir=project_dir,
            _name="",
            _sdk_session_id="",
            _last_input_tokens=0,
            _updated_time=datetime.now(),
        )

    @classmethod
    def reconstitute(
        cls,
        session_id: str,
        model: str,
        status: SessionStatus,
        messages: list[Message],
        usage: Usage,
        continue_conversation: bool,
        project_id: str = "",
        project_dir: str = "",
        name: str = "",
        sdk_session_id: str = "",
        last_input_tokens: int = 0,
        updated_time: datetime | None = None,
    ) -> Session:
        """Reconstitute a Session from persisted data.

        Does not perform business validation; directly restores aggregate state
        from the provided values. Called by Repository implementations when
        loading from the database.
        """
        return cls(
            _session_id=session_id,
            _model=model,
            _status=status,
            _messages=list(messages),
            _usage=usage,
            _continue_conversation=continue_conversation,
            _project_id=project_id,
            _project_dir=project_dir,
            _name=name,
            _sdk_session_id=sdk_session_id,
            _last_input_tokens=last_input_tokens,
            _updated_time=updated_time,
        )

    def start_query(self) -> None:
        """Transition status to RUNNING.

        Allowed from IDLE or ERROR state (ERROR enables retry).
        Raises ValueError if already RUNNING or COMPACTING.
        """
        if self._status in (SessionStatus.RUNNING, SessionStatus.COMPACTING):
            raise ValueError("Session is already running")
        self._status = SessionStatus.RUNNING

    def complete_query(self) -> None:
        """Transition status from RUNNING to IDLE.

        Sets continue_conversation to True.
        Raises ValueError if not currently RUNNING.
        """
        if self._status != SessionStatus.RUNNING:
            raise ValueError("Session is not running")
        self._status = SessionStatus.IDLE
        self._continue_conversation = True
        self._updated_time = datetime.now()

    def cancel_query(self) -> str:
        """Cancel a running query and rewind to before the last user message.

        Transitions status from RUNNING to IDLE.
        Removes the last user message and any subsequent assistant/tool/system messages.
        Returns the prompt text from the removed user message (for restoring to input).
        Raises ValueError if not currently RUNNING.
        """
        if self._status != SessionStatus.RUNNING:
            raise ValueError("Session is not running")
        self._status = SessionStatus.IDLE
        self._continue_conversation = True
        self._updated_time = datetime.now()

        # Find and remove the last user message and everything after it
        prompt = ""
        last_user_idx = -1
        for i in range(len(self._messages) - 1, -1, -1):
            from domain.session.model.message_type import MessageType
            if self._messages[i].message_type == MessageType.USER:
                last_user_idx = i
                prompt = self._messages[i].content.get("text", "")
                break

        if last_user_idx >= 0:
            self._messages = self._messages[:last_user_idx]

        return prompt

    def fail_query(self, error_message: str) -> None:
        """Transition status from RUNNING to ERROR.

        Records the error message.
        Raises ValueError if not currently RUNNING.
        """
        if self._status != SessionStatus.RUNNING:
            raise ValueError("Session is not running")
        self._status = SessionStatus.ERROR

    def add_message(self, message: Message) -> None:
        """Append a message to the message list.

        message must not be None.
        """
        if message is None:
            raise ValueError("message must not be None")
        self._messages.append(message)

    def update_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Replace usage with the latest query's token counts.

        Each query's input_tokens already represents the full context window
        consumption (all prior messages included), so we overwrite rather than
        accumulate.  output_tokens is the model's response for this query.
        """
        if input_tokens < 0:
            raise ValueError("input_tokens must be >= 0")
        if output_tokens < 0:
            raise ValueError("output_tokens must be >= 0")
        self._usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)

    def update_sdk_session_id(self, sdk_session_id: str) -> None:
        """Update the SDK session ID for resume support."""
        self._sdk_session_id = sdk_session_id

    def update_last_input_tokens(self, input_tokens: int) -> None:
        """Update the last query's input_tokens (reflects current context window size)."""
        self._last_input_tokens = input_tokens

    def clear_context(self) -> None:
        """清空会话上下文，完全重置到初始状态。

        重置内容：
        - _messages 置为空列表
        - _usage 重置为 Usage.zero()
        - _continue_conversation 重置为 False
        - _status 设为 SessionStatus.IDLE

        不变内容：
        - _session_id 不变
        - _model 不变
        - _project_dir 不变

        前置条件：当前状态不能为 RUNNING 或 COMPACTING。
        违反时抛出 ValueError("Cannot clear context while session is running")。
        当前状态为 ERROR 时允许清空（视为从错误状态恢复）。
        当前状态为 IDLE 时允许清空（幂等操作）。
        """
        if self._status in (SessionStatus.RUNNING, SessionStatus.COMPACTING):
            raise ValueError("Cannot clear context while session is running")
        self._messages = []
        self._usage = Usage.zero()
        self._continue_conversation = False
        self._sdk_session_id = ""
        self._last_input_tokens = 0
        self._status = SessionStatus.IDLE

    def rename(self, name: str) -> None:
        """Rename this session."""
        self._name = name

    def change_model(self, model: str) -> None:
        """Change the model for this session."""
        self._model = model

    def initialize_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Set absolute usage values for resume scenarios.

        Replaces direct field assignment from the application layer.
        Only allowed when current usage is zero (first-time initialization).

        Args:
            input_tokens: Absolute input token count (>= 0).
            output_tokens: Absolute output token count (>= 0).

        Raises:
            ValueError: If current usage is non-zero.
            ValueError: If input_tokens or output_tokens < 0.
        """
        if self._usage.input_tokens != 0 or self._usage.output_tokens != 0:
            raise ValueError("Cannot initialize usage: current usage is non-zero")
        if input_tokens < 0:
            raise ValueError("input_tokens must be >= 0")
        if output_tokens < 0:
            raise ValueError("output_tokens must be >= 0")
        self._usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)

    def start_compact(self) -> None:
        """Transition status from IDLE to COMPACTING.

        Only allowed from IDLE state.
        Raises ValueError if session is not idle.
        """
        if self._status != SessionStatus.IDLE:
            raise ValueError("Cannot compact: session is not idle")
        self._status = SessionStatus.COMPACTING

    def complete_compact(self, messages: list[Message], usage: Usage) -> None:
        """Complete the compact operation.

        Transitions status from COMPACTING to IDLE.
        Replaces _messages with the provided messages.
        Replaces _usage with the provided usage.
        Sets _continue_conversation to True.
        Updates _updated_time to the current time.

        Only allowed from COMPACTING state.
        Raises ValueError if session is not compacting.
        Raises ValueError if messages is None.
        Raises ValueError if usage is None.
        """
        if self._status != SessionStatus.COMPACTING:
            raise ValueError("Session is not compacting")
        if messages is None:
            raise ValueError("messages must not be None")
        if usage is None:
            raise ValueError("usage must not be None")
        self._messages = list(messages)
        self._usage = usage
        self._continue_conversation = True
        self._status = SessionStatus.IDLE
        self._updated_time = datetime.now()

    def fail_compact(self) -> None:
        """Fail the compact operation, restoring status from COMPACTING to IDLE.

        Messages and usage remain unchanged.
        Only allowed from COMPACTING state.
        Raises ValueError if session is not compacting.
        """
        if self._status != SessionStatus.COMPACTING:
            raise ValueError("Session is not compacting")
        self._status = SessionStatus.IDLE
