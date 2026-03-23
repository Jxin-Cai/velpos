from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.git.git_application_service import GitApplicationService
from ohs.dependencies import get_git_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.git_dto import (
    GenerateSshKeyRequest,
    GenerateSshKeyResponse,
    GitConfigRequest,
    GitConfigResponse,
    SshKeyInfo,
    SshKeyListResponse,
    SshPublicKeyResponse,
)

router = APIRouter(prefix="/api/git", tags=["Git"])

ServiceDep = Annotated[
    GitApplicationService,
    Depends(get_git_application_service),
]


@router.get("/config", summary="Get global git config")
async def get_git_config(
    service: ServiceDep,
) -> ApiResponse[GitConfigResponse]:
    result = await service.get_git_config()
    return ApiResponse.success(GitConfigResponse(**result))


@router.put("/config", summary="Set global git config")
async def set_git_config(
    request: GitConfigRequest,
    service: ServiceDep,
) -> ApiResponse[GitConfigResponse]:
    result = await service.set_git_config(request.user_name, request.user_email)
    return ApiResponse.success(GitConfigResponse(**result))


@router.get("/ssh/keys", summary="List SSH keys")
async def list_ssh_keys(
    service: ServiceDep,
) -> ApiResponse[SshKeyListResponse]:
    keys = await service.list_ssh_keys()
    return ApiResponse.success(SshKeyListResponse(keys=[SshKeyInfo(**k) for k in keys]))


@router.post("/ssh/keys", summary="Generate SSH key")
async def generate_ssh_key(
    request: GenerateSshKeyRequest,
    service: ServiceDep,
) -> ApiResponse[GenerateSshKeyResponse]:
    result = await service.generate_ssh_key(request.key_type, request.comment)
    return ApiResponse.success(GenerateSshKeyResponse(**result))


@router.get("/ssh/keys/{key_name}/public", summary="Get SSH public key")
async def get_ssh_public_key(
    key_name: str,
    service: ServiceDep,
) -> ApiResponse[SshPublicKeyResponse]:
    public_key = await service.get_ssh_public_key(key_name)
    return ApiResponse.success(SshPublicKeyResponse(public_key=public_key))
