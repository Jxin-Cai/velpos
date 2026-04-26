from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from typing import Annotated

from application.command_policy.command_policy_application_service import CommandPolicyApplicationService
from ohs.dependencies import get_command_policy_application_service
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/commands/policies", tags=["Command Policy"])

ServiceDep = Annotated[
    CommandPolicyApplicationService,
    Depends(get_command_policy_application_service),
]


class CommandPolicyRequest(BaseModel):
    project_id: str = Field(default="")
    project_dir: str = Field(default="")
    command_name: str = Field(min_length=1, max_length=128)
    command_type: str = Field(default="unknown", max_length=32)
    enabled: bool = True
    visible: bool = True
    default_args: dict[str, Any] = Field(default_factory=dict)


@router.get("", summary="List project command policies")
async def list_command_policies(
    service: ServiceDep,
    project_id: str = Query(default=""),
    project_dir: str = Query(default=""),
) -> ApiResponse[dict]:
    policies = await service.list_policies(project_id=project_id, project_dir=project_dir)
    return ApiResponse.success({
        "policies": [service.policy_to_dict(policy) for policy in policies],
    })


@router.put("", summary="Create or update project command policy")
async def save_command_policy(
    request: CommandPolicyRequest,
    service: ServiceDep,
) -> ApiResponse[dict]:
    policy = await service.save_policy(
        project_id=request.project_id,
        project_dir=request.project_dir,
        command_name=request.command_name,
        command_type=request.command_type,
        enabled=request.enabled,
        visible=request.visible,
        default_args=request.default_args,
    )
    return ApiResponse.success({"policy": service.policy_to_dict(policy)})
