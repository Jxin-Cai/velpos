from __future__ import annotations

from datetime import datetime, time
from typing import Any

from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException
from domain.usage.model.budget_policy import BudgetPolicy
from domain.usage.model.usage_ledger import UsageLedger
from domain.usage.repository.usage_governance_repository import UsageGovernanceRepository


class UsageGovernanceApplicationService:

    def __init__(
        self,
        repository: UsageGovernanceRepository,
        project_repository: ProjectRepository | None = None,
    ) -> None:
        self._repository = repository
        self._project_repository = project_repository

    async def record_usage(
        self,
        session_id: str,
        project_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> UsageLedger:
        ledger = UsageLedger.create(
            session_id=session_id,
            project_id=project_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )
        await self._repository.save_ledger(ledger)
        return ledger

    async def get_session_usage(self, session_id: str) -> dict[str, Any]:
        ledgers = await self._repository.find_ledgers_by_session_id(session_id)
        return self._usage_summary(ledgers, {"session_id": session_id})

    async def get_project_usage(self, project_id: str, today_only: bool = False) -> dict[str, Any]:
        await self._ensure_project(project_id)
        since = datetime.combine(datetime.now().date(), time.min) if today_only else None
        ledgers = await self._repository.find_ledgers_by_project_id(project_id, since=since)
        policy = await self._repository.find_budget_policy_by_project_id(project_id)
        summary = self._usage_summary(ledgers, {"project_id": project_id})
        summary["budget"] = self.budget_to_dict(policy) if policy else None
        summary["budget_status"] = self._budget_status(summary, policy)
        return summary

    async def get_budget_policy(self, project_id: str) -> BudgetPolicy | None:
        await self._ensure_project(project_id)
        return await self._repository.find_budget_policy_by_project_id(project_id)

    async def save_budget_policy(
        self,
        project_id: str,
        daily_token_limit: int,
        daily_cost_limit_usd: float,
        on_exceed: str,
    ) -> BudgetPolicy:
        await self._ensure_project(project_id)
        policy = await self._repository.find_budget_policy_by_project_id(project_id)
        if policy is None:
            policy = BudgetPolicy.create(project_id, daily_token_limit, daily_cost_limit_usd, on_exceed)
        else:
            policy.update(daily_token_limit, daily_cost_limit_usd, on_exceed)
        await self._repository.save_budget_policy(policy)
        return policy

    async def _ensure_project(self, project_id: str) -> None:
        if not project_id:
            raise BusinessException("Project id is required")
        if self._project_repository is None:
            return
        project = await self._project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found")

    @staticmethod
    def _usage_summary(ledgers: list[UsageLedger], extra: dict[str, Any]) -> dict[str, Any]:
        total_input = sum(item.input_tokens for item in ledgers)
        total_output = sum(item.output_tokens for item in ledgers)
        total_cache_read = sum(item.cache_read_tokens for item in ledgers)
        total_cache_creation = sum(item.cache_creation_tokens for item in ledgers)
        total_cost = round(sum(item.estimated_cost_usd for item in ledgers), 6)
        return {
            **extra,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_creation_tokens": total_cache_creation,
            "estimated_cost_usd": total_cost,
            "entries": [UsageGovernanceApplicationService.ledger_to_dict(item) for item in ledgers],
        }

    @staticmethod
    def _budget_status(summary: dict[str, Any], policy: BudgetPolicy | None) -> dict[str, Any]:
        if policy is None:
            return {"state": "none", "token_ratio": 0, "cost_ratio": 0}
        token_ratio = summary["total_tokens"] / policy.daily_token_limit if policy.daily_token_limit > 0 else 0
        cost_ratio = summary["estimated_cost_usd"] / policy.daily_cost_limit_usd if policy.daily_cost_limit_usd > 0 else 0
        exceeded = (policy.daily_token_limit > 0 and token_ratio >= 1) or (policy.daily_cost_limit_usd > 0 and cost_ratio >= 1)
        warning = token_ratio >= 0.8 or cost_ratio >= 0.8
        return {
            "state": "exceeded" if exceeded else "warning" if warning else "ok",
            "token_ratio": round(token_ratio, 4),
            "cost_ratio": round(cost_ratio, 4),
            "on_exceed": policy.on_exceed,
        }

    @staticmethod
    def ledger_to_dict(ledger: UsageLedger) -> dict[str, Any]:
        return {
            "id": ledger.id,
            "session_id": ledger.session_id,
            "project_id": ledger.project_id,
            "model": ledger.model,
            "input_tokens": ledger.input_tokens,
            "output_tokens": ledger.output_tokens,
            "cache_read_tokens": ledger.cache_read_tokens,
            "cache_creation_tokens": ledger.cache_creation_tokens,
            "estimated_cost_usd": ledger.estimated_cost_usd,
            "created_time": ledger.created_time.isoformat(),
        }

    @staticmethod
    def budget_to_dict(policy: BudgetPolicy | None) -> dict[str, Any] | None:
        if policy is None:
            return None
        return {
            "id": policy.id,
            "project_id": policy.project_id,
            "daily_token_limit": policy.daily_token_limit,
            "daily_cost_limit_usd": policy.daily_cost_limit_usd,
            "on_exceed": policy.on_exceed,
            "updated_time": policy.updated_time.isoformat(),
        }
