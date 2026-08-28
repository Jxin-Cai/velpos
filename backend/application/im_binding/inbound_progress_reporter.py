from __future__ import annotations

import asyncio
import enum
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime

from application.im_binding.im_channel_facade import ImChannelFacade
from domain.im_binding.model.channel_capability import ChannelCapability
from domain.im_binding.model.channel_route import ChannelRoute
from domain.im_binding.model.im_binding import ImBinding

logger = logging.getLogger(__name__)

#: 渠道无原生进度提示时, 延迟多久发送"任务已开始"文本.
PROGRESS_ACK_DELAY_SECONDS = 8.0

#: 发送进度文本的回调: ``(content, dedup_suffix) -> None``.
SendText = Callable[[str, str], Awaitable[None]]


class TaskOutcome(str, enum.Enum):
    COMPLETED = "已完成"
    FAILED = "未完成"
    RETRYING = "执行异常，正在重试"
    WAITING = "等待中"


class InboundProgressReporter:
    """入站任务的进度反馈 — 用渠道具备的能力告诉用户"我在干活".

    三种反馈手段按能力择优使用, 互不排斥:

    - ``REACTION``: 给来源消息打表情, 完成后撤掉（飞书）
    - ``TYPING_INDICATOR``: 展示正在输入（微信）
    - ``PROGRESS_ACK``: 以上都没有时, 超时后发一条文本告知任务已开始

    只有走 ``PROGRESS_ACK`` 的渠道才需要任务编号来关联"开始"和"结束"两条
    消息, 因此 :meth:`decorate` 也由能力决定是否加编号, 而不是由渠道类型。
    """

    def __init__(
        self,
        facade: ImChannelFacade,
        binding: ImBinding,
        route: ChannelRoute,
        source_message_id: str,
        task_code: str,
        send_text: SendText,
    ) -> None:
        self._facade = facade
        self._binding = binding
        self._route = route
        self._source_message_id = source_message_id
        self._task_code = task_code
        self._send_text = send_text

        self._reaction_id = ""
        self._typing_ticket = ""
        self._ack_task: asyncio.Task[None] | None = None
        self._started_at = time.monotonic()

    @property
    def uses_task_framing(self) -> bool:
        return self._facade.supports(
            self._binding.channel_type, ChannelCapability.PROGRESS_ACK,
        )

    async def __aenter__(self) -> InboundProgressReporter:
        self._started_at = time.monotonic()
        self._reaction_id = await self._safely(
            self._facade.add_reaction(
                self._binding, self._source_message_id, "OnIt",
            ),
            "add_reaction",
        ) or ""
        self._typing_ticket = await self._safely(
            self._facade.start_typing(self._binding, self._route),
            "start_typing",
        ) or ""
        if self.uses_task_framing:
            self._ack_task = asyncio.create_task(
                self._send_delayed_ack(),
                name=f"im-progress-ack-{self._task_code}",
            )
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._ack_task is not None:
            self._ack_task.cancel()
            await asyncio.gather(self._ack_task, return_exceptions=True)
            self._ack_task = None
        await self._safely(
            self._facade.remove_reaction(
                self._binding, self._source_message_id, self._reaction_id,
            ),
            "remove_reaction",
        )
        await self._safely(
            self._facade.stop_typing(self._binding, self._typing_ticket),
            "stop_typing",
        )

    def outcome_line(self, outcome: TaskOutcome) -> str:
        """任务结果标记行 — 带耗时与完成时刻, 便于用户感知操作时间."""
        return (
            f"任务 {self._task_code} · {outcome.value} · "
            f"用时 {_humanize(time.monotonic() - self._started_at)} · "
            f"{datetime.now():%m-%d %H:%M}"
        )

    def decorate(self, outcome: TaskOutcome, content: str) -> str:
        """给结果文本加上任务编号与耗时, 仅对使用文本进度的渠道生效."""
        if not self.uses_task_framing:
            return content
        return f"{self.outcome_line(outcome)}\n\n{content.strip()}"

    async def report_waiting(self, reason: str) -> None:
        """任务无法立即执行时告知用户, 避免渠道侧看起来像没反应."""
        if not self.uses_task_framing:
            return
        await self._send_text(
            f"任务 {self._task_code} · {TaskOutcome.WAITING.value}\n\n{reason}",
            "busy",
        )

    async def _send_delayed_ack(self) -> None:
        await asyncio.sleep(PROGRESS_ACK_DELAY_SECONDS)
        await self._send_text(
            f"任务 {self._task_code} · 已开始\n\n正在执行你的请求，完成后会发送结果。",
            "started",
        )

    async def _safely(self, awaitable: Awaitable[object], action: str) -> object:
        """进度反馈是锦上添花, 失败不应影响主流程."""
        try:
            return await awaitable
        except Exception:
            logger.debug(
                "[IM-progress] %s failed: channel=%s",
                action,
                self._binding.channel_type.value,
                exc_info=True,
            )
            return None


def _humanize(elapsed_seconds: float) -> str:
    total = max(0, round(elapsed_seconds))
    if total < 60:
        return f"{total} 秒"
    minutes, seconds = divmod(total, 60)
    return f"{minutes} 分 {seconds} 秒"
