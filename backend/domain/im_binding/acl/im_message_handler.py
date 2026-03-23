from abc import ABC, abstractmethod


class ImMessageHandler(ABC):

    @abstractmethod
    async def handle_prompt(self, session_id: str, prompt: str) -> None:
        """将 IM 消息转发为 Claude Code 查询.

        session_id: 目标会话 ID.
        prompt: IM 消息文本, 等同于 Web UI 用户输入.

        实现方应调用 SessionApplicationService.run_claude_query.
        会话不存在或正在运行时, 静默返回并记录警告.
        """
        ...
