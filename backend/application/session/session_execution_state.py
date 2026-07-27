from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from domain.shared.async_utils import KeyedLockPool


@dataclass
class SessionExecutionState:
    """Process-level execution coordination state for session queries."""

    session_lock_pool: KeyedLockPool = field(default_factory=lambda: KeyedLockPool(max_size=500))
    cancelled_sessions: set[str] = field(default_factory=set)
    queued_messages: dict[str, Any] = field(default_factory=dict)
    active_contexts: dict[str, Any] = field(default_factory=dict)
    waiting_for_slot: set[str] = field(default_factory=set)
    slot_wait_started_at: dict[str, float] = field(default_factory=dict)
    queue_guard: asyncio.Lock = field(default_factory=asyncio.Lock)
    query_semaphore: asyncio.Semaphore | None = field(default=None)
    query_semaphore_guard: asyncio.Lock = field(default_factory=asyncio.Lock)
