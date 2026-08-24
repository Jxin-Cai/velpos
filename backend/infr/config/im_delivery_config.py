"""IM 投递队列策略 — 经环境变量调优, 越界值被夹取并告警."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ENV_LEASE_SECONDS = "IM_DELIVERY_LEASE_SECONDS"
_ENV_MAX_ATTEMPTS = "IM_DELIVERY_MAX_ATTEMPTS"
_ENV_MAX_BACKOFF_SECONDS = "IM_DELIVERY_MAX_BACKOFF_SECONDS"
_ENV_INBOX_WORKERS = "IM_INBOX_WORKERS"
_ENV_OUTBOX_WORKERS = "IM_OUTBOX_WORKERS"


@dataclass(frozen=True)
class ImDeliveryPolicy:
    """IM 收发队列的可靠性参数.

    - ``lease_seconds``: worker 租约时长, 超时后消息可被其他 worker 重认领
    - ``max_attempts``: 最大尝试次数, 超过即死信
    - ``max_backoff_seconds``: 指数退避的上限
    - ``inbox_workers`` / ``outbox_workers``: 并发 worker 数
    """

    lease_seconds: int = 120
    max_attempts: int = 8
    max_backoff_seconds: int = 300
    inbox_workers: int = 4
    outbox_workers: int = 4

    @classmethod
    def from_env(cls) -> ImDeliveryPolicy:
        default = cls()
        return cls(
            lease_seconds=_read_bounded_int(
                _ENV_LEASE_SECONDS, default.lease_seconds, 10, 3600,
            ),
            max_attempts=_read_bounded_int(
                _ENV_MAX_ATTEMPTS, default.max_attempts, 1, 50,
            ),
            max_backoff_seconds=_read_bounded_int(
                _ENV_MAX_BACKOFF_SECONDS, default.max_backoff_seconds, 1, 3600,
            ),
            inbox_workers=_read_bounded_int(
                _ENV_INBOX_WORKERS, default.inbox_workers, 1, 16,
            ),
            outbox_workers=_read_bounded_int(
                _ENV_OUTBOX_WORKERS, default.outbox_workers, 1, 16,
            ),
        )


def _read_bounded_int(
    env_name: str, default: int, minimum: int, maximum: int,
) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid %s=%r; using default %s", env_name, raw_value, default,
        )
        return default
    clamped = min(maximum, max(minimum, value))
    if clamped != value:
        logger.warning(
            "%s=%s outside [%s, %s]; clamped to %s",
            env_name, value, minimum, maximum, clamped,
        )
    return clamped
