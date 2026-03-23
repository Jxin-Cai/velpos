from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from application.channel_profile.channel_profile_application_service import (
    ChannelProfileApplicationService,
)
from application.channel_profile.command.create_channel_profile_command import (
    CreateChannelProfileCommand,
)
from application.channel_profile.command.update_channel_profile_command import (
    UpdateChannelProfileCommand,
)
from ohs.dependencies import get_channel_profile_application_service
from ohs.http.api_response import ApiResponse
from ohs.http.dto.channel_profile_dto import (
    ChannelProfileListResponse,
    ChannelProfileResponse,
    CreateChannelProfileRequest,
    UpdateChannelProfileRequest,
)

router = APIRouter(prefix="/api/channel-profiles", tags=["ChannelProfile"])

ServiceDep = Annotated[
    ChannelProfileApplicationService,
    Depends(get_channel_profile_application_service),
]


@router.get("", summary="List channel profiles")
async def list_profiles(
    service: ServiceDep,
) -> ApiResponse[ChannelProfileListResponse]:
    profiles = await service.list_profiles()
    response = ChannelProfileListResponse.from_domain_list(profiles)
    return ApiResponse.success(response)


@router.post("", summary="Create channel profile")
async def create_profile(
    request: CreateChannelProfileRequest,
    service: ServiceDep,
) -> ApiResponse[ChannelProfileResponse]:
    command = CreateChannelProfileCommand(
        name=request.name,
        host=request.host,
        api_key=request.api_key,
        auth_env_name=request.auth_env_name,
        channel_model_config=request.channel_model_config,
    )
    profile = await service.create_profile(command)
    response = ChannelProfileResponse.from_domain(profile)
    return ApiResponse.success(response)


@router.put("/{profile_id}", summary="Update channel profile")
async def update_profile(
    profile_id: str,
    request: UpdateChannelProfileRequest,
    service: ServiceDep,
) -> ApiResponse[ChannelProfileResponse]:
    command = UpdateChannelProfileCommand(
        name=request.name,
        host=request.host,
        api_key=request.api_key,
        auth_env_name=request.auth_env_name,
        channel_model_config=request.channel_model_config,
    )
    profile = await service.update_profile(profile_id, command)
    response = ChannelProfileResponse.from_domain(profile)
    return ApiResponse.success(response)


@router.delete("/{profile_id}", summary="Delete channel profile")
async def delete_profile(
    profile_id: str,
    service: ServiceDep,
) -> ApiResponse[None]:
    await service.delete_profile(profile_id)
    return ApiResponse.success()


@router.post("/{profile_id}/activate", summary="Activate channel profile")
async def activate_profile(
    profile_id: str,
    service: ServiceDep,
) -> ApiResponse[ChannelProfileResponse]:
    profile = await service.activate_profile(profile_id)
    response = ChannelProfileResponse.from_domain(profile)
    return ApiResponse.success(response)
