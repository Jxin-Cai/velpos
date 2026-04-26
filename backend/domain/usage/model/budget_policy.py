from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BudgetPolicy:
    id: str
    project_id: str
    daily_token_limit: int = 0
    daily_cost_limit_usd: float = 0.0
    on_exceed: str = "warn"
    updated_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        project_id: str,
        daily_token_limit: int = 0,
        daily_cost_limit_usd: float = 0.0,
        on_exceed: str = "warn",
    ) -> BudgetPolicy:
        return cls(
            id=uuid.uuid4().hex[:8],
            project_id=project_id,
            daily_token_limit=max(daily_token_limit, 0),
            daily_cost_limit_usd=max(daily_cost_limit_usd, 0.0),
            on_exceed=on_exceed or "warn",
            updated_time=datetime.now(),
        )

    def update(
        self,
        daily_token_limit: int,
        daily_cost_limit_usd: float,
        on_exceed: str,
    ) -> None:
        self.daily_token_limit = max(daily_token_limit, 0)
        self.daily_cost_limit_usd = max(daily_cost_limit_usd, 0.0)
        self.on_exceed = on_exceed or "warn"
        self.updated_time = datetime.now()
