from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.usage.model.budget_policy import BudgetPolicy
from domain.usage.model.usage_ledger import UsageLedger


class UsageGovernanceRepository(ABC):

    @abstractmethod
    async def save_ledger(self, ledger: UsageLedger) -> None:
        ...

    @abstractmethod
    async def find_ledgers_by_session_id(self, session_id: str) -> list[UsageLedger]:
        ...

    @abstractmethod
    async def find_ledgers_by_project_id(
        self,
        project_id: str,
        since: datetime | None = None,
    ) -> list[UsageLedger]:
        ...

    @abstractmethod
    async def save_budget_policy(self, policy: BudgetPolicy) -> None:
        ...

    @abstractmethod
    async def find_budget_policy_by_project_id(self, project_id: str) -> BudgetPolicy | None:
        ...
