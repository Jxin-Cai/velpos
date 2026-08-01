from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from application.auth.auth_application_service import AuthApplicationService
from domain.user.model.user import User
from infr.config.app_config import app_config
from infr.config.database import get_async_session
from infr.repository.user_repository_impl import UserRepositoryImpl
from ohs.auth_dependency import get_current_user
from ohs.http.api_response import ApiResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6)
    display_name: str | None = Field(default=None, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


class AuthConfigResponse(BaseModel):
    mode: str
    auto_login: bool


def _get_auth_service(
    db_session: AsyncSession = Depends(get_async_session),
) -> AuthApplicationService:
    return AuthApplicationService(UserRepositoryImpl(db_session))


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
    )


@router.get("/config")
async def get_auth_config() -> ApiResponse[AuthConfigResponse]:
    return ApiResponse.success(
        AuthConfigResponse(
            mode=app_config.mode,
            auto_login=app_config.mode == "dev",
        )
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    auth_svc: AuthApplicationService = Depends(_get_auth_service),
) -> ApiResponse[LoginResponse]:
    user, token = await auth_svc.login(body.username, body.password)
    return ApiResponse.success(
        LoginResponse(token=token, user=_to_user_response(user))
    )


@router.post("/register")
async def register(
    body: RegisterRequest,
    auth_svc: AuthApplicationService = Depends(_get_auth_service),
) -> ApiResponse[UserResponse]:
    user = await auth_svc.register(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
    )
    return ApiResponse.success(_to_user_response(user))


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    return ApiResponse.success(_to_user_response(current_user))
