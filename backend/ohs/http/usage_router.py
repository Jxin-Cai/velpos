from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from application.usage.usage_governance_application_service import UsageGovernanceApplicationService
from ohs.dependencies import get_usage_governance_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api", tags=["Usage"])

ServiceDep = Annotated[
    UsageGovernanceApplicationService,
    Depends(get_usage_governance_application_service),
]


class BudgetPolicyRequest(BaseModel):
    daily_token_limit: int = Field(default=0, ge=0)
    daily_cost_limit_usd: float = Field(default=0.0, ge=0)
    on_exceed: str = Field(default="warn")


@router.get("/usage/sessions/{session_id}", summary="Get session usage")
async def get_session_usage(
    session_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    return ApiResponse.success(await service.get_session_usage(session_id))


@router.get("/usage/projects/{project_id}", summary="Get project usage")
async def get_project_usage(
    project_id: str,
    service: ServiceDep,
    today_only: bool = Query(default=False),
) -> ApiResponse[dict]:
    return ApiResponse.success(await service.get_project_usage(project_id, today_only=today_only))


@router.get("/budgets/projects/{project_id}", summary="Get project budget policy")
async def get_project_budget(
    project_id: str,
    service: ServiceDep,
) -> ApiResponse[dict]:
    policy = await service.get_budget_policy(project_id)
    return ApiResponse.success({"budget": service.budget_to_dict(policy)})


@router.put("/budgets/projects/{project_id}", summary="Save project budget policy")
async def save_project_budget(
    project_id: str,
    request: BudgetPolicyRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    policy = await service.save_budget_policy(
        project_id=project_id,
        daily_token_limit=request.daily_token_limit,
        daily_cost_limit_usd=request.daily_cost_limit_usd,
        on_exceed=request.on_exceed,
    )
    return ApiResponse.success({"budget": service.budget_to_dict(policy)})
