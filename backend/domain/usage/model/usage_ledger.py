from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class UsageLedger:
    id: str
    session_id: str
    project_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float = 0.0
    created_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        session_id: str,
        project_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> UsageLedger:
        estimated_cost = cls.estimate_cost_usd(input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
        return cls(
            id=uuid.uuid4().hex[:8],
            session_id=session_id,
            project_id=project_id,
            model=model,
            input_tokens=max(input_tokens, 0),
            output_tokens=max(output_tokens, 0),
            cache_read_tokens=max(cache_read_tokens, 0),
            cache_creation_tokens=max(cache_creation_tokens, 0),
            estimated_cost_usd=estimated_cost,
            created_time=datetime.now(),
        )

    @staticmethod
    def estimate_cost_usd(
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> float:
        input_cost = max(input_tokens - cache_read_tokens - cache_creation_tokens, 0) / 1_000_000 * 3.0
        output_cost = max(output_tokens, 0) / 1_000_000 * 15.0
        cache_read_cost = max(cache_read_tokens, 0) / 1_000_000 * 0.30
        cache_creation_cost = max(cache_creation_tokens, 0) / 1_000_000 * 3.75
        return round(input_cost + output_cost + cache_read_cost + cache_creation_cost, 6)
