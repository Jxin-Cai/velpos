from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from application.im_binding.im_channel_application_service import ImChannelApplicationService
from domain.im_binding.model.im_delivery import ImDeliveryKind
from domain.user.model.user import User
from ohs.auth_dependency import get_current_user
from ohs.dependencies import (
    get_im_channel_application_service,
    get_im_delivery_monitor,
)
from ohs.http.api_response import ApiResponse
from ohs.http.dto.im_dto import (
    BindImRequest,
    BindImResponse,
    ChannelInfo,
    ChannelInstanceInfo,
    CompleteBindingRequest,
    CreateChannelRequest,
    ImDeliveryOverviewResponse,
    ImStatusResponse,
    InitChannelRequest,
    InitChannelResponse,
    RenameChannelRequest,
    RetryDeliveryResponse,
)
from ohs.im_delivery_monitor import ImDeliveryMonitor

router = APIRouter(prefix="/api/im", tags=["IM"])

ChannelServiceDep = Annotated[ImChannelApplicationService, Depends(get_im_channel_application_service)]
DeliveryMonitorDep = Annotated[ImDeliveryMonitor, Depends(get_im_delivery_monitor)]


# ── Channel discovery ──

@router.get("/channels", summary="List available IM channels with instances")
async def list_channels(
    channel_service: ChannelServiceDep,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[ChannelInfo]]:
    channels = await channel_service.list_available_channels(user_id=current_user.id)
    result = []
    for c in channels:
        instances_raw = c.get("instances", [])
        instances = [ChannelInstanceInfo(**inst) for inst in instances_raw]
        channel_data = {k: v for k, v in c.items() if k != "instances"}
        result.append(ChannelInfo(**channel_data, instances=instances))
    return ApiResponse.success(result)


# ── Channel instance management ──

@router.post("/channels", summary="Create channel instance")
async def create_channel(
    request: CreateChannelRequest,
    channel_service: ChannelServiceDep,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    result = await channel_service.create_channel_instance(
        channel_type=request.channel_type,
        name=request.name,
        user_id=current_user.id,
    )
    return ApiResponse.success(result)


@router.delete("/channels/{channel_id}", summary="Delete channel instance")
async def delete_channel(
    channel_id: str,
    channel_service: ChannelServiceDep,
) -> ApiResponse[None]:
    await channel_service.delete_channel_instance(channel_id)
    return ApiResponse.success()


@router.patch("/channels/{channel_id}", summary="Rename channel instance")
async def rename_channel(
    channel_id: str,
    request: RenameChannelRequest,
    channel_service: ChannelServiceDep,
) -> ApiResponse[dict[str, Any]]:
    result = await channel_service.rename_channel_instance(channel_id, request.name)
    return ApiResponse.success(result)


# ── Channel initialization ──

@router.get("/channels/{channel_id}/init", summary="Get channel init status")
async def get_channel_init(
    channel_id: str,
    channel_service: ChannelServiceDep,
) -> ApiResponse[InitChannelResponse]:
    result = await channel_service.get_channel_init_status(channel_id)
    return ApiResponse.success(InitChannelResponse(**result))


@router.post("/channels/{channel_id}/init", summary="Initialize channel instance")
async def init_channel(
    channel_id: str,
    request: InitChannelRequest,
    channel_service: ChannelServiceDep,
) -> ApiResponse[InitChannelResponse]:
    result = await channel_service.initialize_channel(channel_id, request.params)
    return ApiResponse.success(InitChannelResponse(**result))


@router.delete("/channels/{channel_id}/init", summary="Reset channel instance")
async def reset_channel(
    channel_id: str,
    channel_service: ChannelServiceDep,
) -> ApiResponse[None]:
    await channel_service.reset_channel(channel_id)
    return ApiResponse.success()


# ── Unified binding endpoints ──

@router.post("/bindings", summary="Bind IM for session")
async def bind_im(
    request: BindImRequest,
    channel_service: ChannelServiceDep,
) -> ApiResponse[dict[str, Any]]:
    result = await channel_service.bind(
        session_id=request.session_id,
        channel_id=request.channel_id,
        params=request.params,
    )
    if result.get("action") == "init_required":
        return ApiResponse.success(result)
    return ApiResponse.success(BindImResponse.from_dict(result).model_dump())


@router.post("/bindings/complete", summary="Complete IM binding")
async def complete_binding(
    request: CompleteBindingRequest,
    channel_service: ChannelServiceDep,
) -> ApiResponse[BindImResponse]:
    params = request.params.copy()
    if request.friend_user_id:
        params["friend_user_id"] = request.friend_user_id
    result = await channel_service.complete_binding(
        session_id=request.session_id,
        channel_id=request.channel_id,
        params=params,
    )
    return ApiResponse.success(BindImResponse.from_dict(result))


@router.get("/bindings/{session_id}", summary="Get IM binding status")
async def get_binding_status(
    session_id: str,
    channel_service: ChannelServiceDep,
) -> ApiResponse[ImStatusResponse | None]:
    binding = await channel_service.get_binding(session_id)
    if binding is None:
        return ApiResponse.success(None)
    return ApiResponse.success(ImStatusResponse.from_domain(binding))


@router.delete("/bindings/{session_id}", summary="Unbind IM")
async def unbind_im(
    session_id: str,
    channel_service: ChannelServiceDep,
) -> ApiResponse[None]:
    await channel_service.unbind(session_id)
    return ApiResponse.success()


@router.post("/bindings/{session_id}/sync-context", summary="Sync session context to IM")
async def sync_context(
    session_id: str,
    channel_service: ChannelServiceDep,
) -> ApiResponse[dict[str, Any]]:
    result = await channel_service.sync_session_context(session_id)
    return ApiResponse.success(result)


# ── Delivery observability ──

@router.get(
    "/bindings/{session_id}/deliveries",
    summary="Get IM delivery queue status for session",
)
async def get_delivery_overview(
    session_id: str,
    delivery_monitor: DeliveryMonitorDep,
) -> ApiResponse[ImDeliveryOverviewResponse]:
    overview = await delivery_monitor.overview(session_id)
    return ApiResponse.success(ImDeliveryOverviewResponse(**overview))


@router.post(
    "/bindings/{session_id}/deliveries/{kind}/{delivery_id}/retry",
    summary="Requeue a permanently failed IM delivery",
)
async def retry_delivery(
    session_id: str,
    kind: ImDeliveryKind,
    delivery_id: int,
    delivery_monitor: DeliveryMonitorDep,
) -> ApiResponse[RetryDeliveryResponse]:
    requeued = await delivery_monitor.retry(session_id, kind, delivery_id)
    return ApiResponse.success(RetryDeliveryResponse(requeued=requeued))
