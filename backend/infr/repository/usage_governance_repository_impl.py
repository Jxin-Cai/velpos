from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.usage.model.budget_policy import BudgetPolicy
from domain.usage.model.usage_ledger import UsageLedger
from domain.usage.repository.usage_governance_repository import UsageGovernanceRepository
from infr.repository.usage_governance_model import BudgetPolicyModel, UsageLedgerModel


class UsageGovernanceRepositoryImpl(UsageGovernanceRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_ledger(self, ledger: UsageLedger) -> None:
        self._session.add(self._ledger_to_model(ledger))
        await self._session.flush()

    async def find_ledgers_by_session_id(self, session_id: str) -> list[UsageLedger]:
        stmt = (
            select(UsageLedgerModel)
            .where(UsageLedgerModel.session_id == session_id)
            .order_by(UsageLedgerModel.created_time.desc())
        )
        result = await self._session.execute(stmt)
        return [self._ledger_to_domain(m) for m in result.scalars().all()]

    async def find_ledgers_by_project_id(
        self,
        project_id: str,
        since: datetime | None = None,
    ) -> list[UsageLedger]:
        stmt = select(UsageLedgerModel).where(UsageLedgerModel.project_id == project_id)
        if since is not None:
            stmt = stmt.where(UsageLedgerModel.created_time >= since)
        stmt = stmt.order_by(UsageLedgerModel.created_time.desc())
        result = await self._session.execute(stmt)
        return [self._ledger_to_domain(m) for m in result.scalars().all()]

    async def save_budget_policy(self, policy: BudgetPolicy) -> None:
        await self._session.merge(self._budget_to_model(policy))
        await self._session.flush()

    async def find_budget_policy_by_project_id(self, project_id: str) -> BudgetPolicy | None:
        stmt = select(BudgetPolicyModel).where(BudgetPolicyModel.project_id == project_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._budget_to_domain(model)

    @staticmethod
    def _ledger_to_model(ledger: UsageLedger) -> UsageLedgerModel:
        return UsageLedgerModel(
            id=ledger.id,
            session_id=ledger.session_id,
            project_id=ledger.project_id,
            model=ledger.model,
            input_tokens=ledger.input_tokens,
            output_tokens=ledger.output_tokens,
            cache_read_tokens=ledger.cache_read_tokens,
            cache_creation_tokens=ledger.cache_creation_tokens,
            estimated_cost_usd=ledger.estimated_cost_usd,
            created_time=ledger.created_time,
        )

    @staticmethod
    def _ledger_to_domain(model: UsageLedgerModel) -> UsageLedger:
        return UsageLedger(
            id=model.id,
            session_id=model.session_id,
            project_id=model.project_id,
            model=model.model,
            input_tokens=model.input_tokens,
            output_tokens=model.output_tokens,
            cache_read_tokens=model.cache_read_tokens,
            cache_creation_tokens=model.cache_creation_tokens,
            estimated_cost_usd=model.estimated_cost_usd,
            created_time=model.created_time,
        )

    @staticmethod
    def _budget_to_model(policy: BudgetPolicy) -> BudgetPolicyModel:
        return BudgetPolicyModel(
            id=policy.id,
            project_id=policy.project_id,
            daily_token_limit=policy.daily_token_limit,
            daily_cost_limit_usd=policy.daily_cost_limit_usd,
            on_exceed=policy.on_exceed,
            updated_time=policy.updated_time,
        )

    @staticmethod
    def _budget_to_domain(model: BudgetPolicyModel) -> BudgetPolicy:
        return BudgetPolicy(
            id=model.id,
            project_id=model.project_id,
            daily_token_limit=model.daily_token_limit,
            daily_cost_limit_usd=model.daily_cost_limit_usd,
            on_exceed=model.on_exceed,
            updated_time=model.updated_time,
        )
