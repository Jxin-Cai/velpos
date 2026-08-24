"""IM 投递监控 — 队列状态查询与死信重投.

与 :class:`~ohs.im_delivery_coordinator.ImDeliveryCoordinator` 分工:
协调器负责队列 worker 的推进, 本类负责让队列状态对用户可见、
让最终失败可被一键重投。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.im_binding.model.im_delivery import (
    INBOX_UNSETTLED_STATUSES,
    OUTBOX_UNSETTLED_STATUSES,
    ImDeliveryKind,
    ImInboxEvent,
    ImOutboxMessage,
)
from infr.config.database import async_session_factory
from infr.repository.im_delivery_repository_impl import (
    ImInboxRepositoryImpl,
    ImOutboxRepositoryImpl,
)

_CONTENT_PREVIEW_LENGTH = 120


class ImDeliveryMonitor:
    """会话级 IM 投递健康视图与死信重投入口."""

    def __init__(
        self,
        wake_inbox: Callable[[], None],
        wake_outbox: Callable[[], None],
    ) -> None:
        self._wake_inbox = wake_inbox
        self._wake_outbox = wake_outbox

    async def overview(
        self, session_id: str, *, recent_limit: int = 10,
    ) -> dict[str, Any]:
        """返回会话两条队列的状态计数与未结清条目明细."""
        async with async_session_factory() as db:
            inbox_repo = ImInboxRepositoryImpl(db)
            outbox_repo = ImOutboxRepositoryImpl(db)
            inbox_counts = await inbox_repo.count_by_status(session_id)
            outbox_counts = await outbox_repo.count_by_status(session_id)
            inbox_recent = await inbox_repo.find_recent_by_session(
                session_id, recent_limit, statuses=INBOX_UNSETTLED_STATUSES,
            )
            outbox_recent = await outbox_repo.find_recent_by_session(
                session_id, recent_limit, statuses=OUTBOX_UNSETTLED_STATUSES,
            )
        return {
            "session_id": session_id,
            "inbox": {
                "counts": {
                    status.value: count for status, count in inbox_counts.items()
                },
                "unsettled": [self._inbox_item(event) for event in inbox_recent],
            },
            "outbox": {
                "counts": {
                    status.value: count for status, count in outbox_counts.items()
                },
                "unsettled": [
                    self._outbox_item(message) for message in outbox_recent
                ],
            },
        }

    async def retry(
        self, session_id: str, kind: ImDeliveryKind, delivery_id: int,
    ) -> bool:
        """把会话内一条最终失败的投递重新放回队列.

        返回是否真的发生了重投 — 条目不存在、不属于该会话或不处于
        可重投状态时返回 False, 幂等且不报错（并发重投是正常场景）。
        """
        async with async_session_factory() as db:
            if kind is ImDeliveryKind.INBOX:
                requeued = await ImInboxRepositoryImpl(db).requeue(
                    delivery_id, session_id,
                )
            else:
                requeued = await ImOutboxRepositoryImpl(db).requeue(
                    delivery_id, session_id,
                )
            await db.commit()
        if requeued is None:
            return False
        if kind is ImDeliveryKind.INBOX:
            self._wake_inbox()
        else:
            self._wake_outbox()
        return True

    @staticmethod
    def _inbox_item(event: ImInboxEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "kind": ImDeliveryKind.INBOX.value,
            "status": event.status.value,
            "content_preview": event.content[:_CONTENT_PREVIEW_LENGTH],
            "attempt_count": event.attempt_count,
            "next_attempt_at": _isoformat(event.next_attempt_at),
            "error_message": event.error_message,
            "created_at": _isoformat(event.created_at),
            "updated_at": _isoformat(event.updated_at),
        }

    @staticmethod
    def _outbox_item(message: ImOutboxMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "kind": ImDeliveryKind.OUTBOX.value,
            "status": message.status.value,
            "content_preview": message.content[:_CONTENT_PREVIEW_LENGTH],
            "attempt_count": message.attempt_count,
            "next_attempt_at": _isoformat(message.next_attempt_at),
            "error_message": message.error_message,
            "created_at": _isoformat(message.created_at),
            "updated_at": _isoformat(message.updated_at),
        }


def _isoformat(value: Any) -> str:
    return value.isoformat() if value is not None else ""
