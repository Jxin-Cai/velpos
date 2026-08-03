from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from domain.shared.business_exception import BusinessException
from domain.user.model.user import User, UserRole
from domain.user.repository.user_repository import UserRepository
from ohs.auth_dependency import require_admin
from ohs.http.api_response import ApiResponse
from infr.config.database import get_async_session
from infr.repository.user_repository_impl import UserRepositoryImpl

router = APIRouter(
    prefix="/api/admin/users",
    tags=["Admin - Users"],
    dependencies=[Depends(require_admin)],
)


async def _get_user_repo(
    db_session: AsyncSession = Depends(get_async_session),
) -> UserRepository:
    return UserRepositoryImpl(db_session)


RepoDep = Annotated[UserRepository, Depends(_get_user_repo)]


class UpdateRoleRequest(BaseModel):
    role: str


class UpdateStatusRequest(BaseModel):
    is_active: bool


@router.get("", summary="List all users")
async def list_users(repo: RepoDep) -> ApiResponse[list]:
    users = await repo.find_all()
    return ApiResponse.success([
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role.value,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ])


@router.put("/{user_id}/role", summary="Update user role")
async def update_user_role(
    user_id: int,
    request: UpdateRoleRequest,
    repo: RepoDep,
    admin: Annotated[User, Depends(require_admin)],
) -> ApiResponse[None]:
    user = await repo.find_by_id(user_id)
    if user is None:
        raise BusinessException(f"User not found: {user_id}")

    try:
        new_role = UserRole(request.role)
    except ValueError:
        raise BusinessException(f"Invalid role: {request.role}")

    if user.id == admin.id and new_role != UserRole.ADMIN:
        raise BusinessException("Administrators cannot demote their own account")

    user.update_role(new_role)
    await repo.save(user)
    return ApiResponse.success(None)


@router.put("/{user_id}/status", summary="Update user status")
async def update_user_status(
    user_id: int,
    request: UpdateStatusRequest,
    repo: RepoDep,
    admin: Annotated[User, Depends(require_admin)],
) -> ApiResponse[None]:
    user = await repo.find_by_id(user_id)
    if user is None:
        raise BusinessException(f"User not found: {user_id}")

    if user.id == admin.id and not request.is_active:
        raise BusinessException("Administrators cannot disable their own account")

    if request.is_active:
        user.activate()
    else:
        user.deactivate()
    await repo.save(user)
    return ApiResponse.success(None)
