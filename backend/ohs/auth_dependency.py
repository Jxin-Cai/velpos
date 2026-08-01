from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from domain.user.model.user import User, UserRole
from infr.config.app_config import app_config

DEFAULT_ADMIN_ID = 1

_DEFAULT_ADMIN = User.reconstitute(
    id=DEFAULT_ADMIN_ID,
    username="admin",
    display_name="Admin",
    role=UserRole.ADMIN,
    hashed_password="",
    created_at=datetime(2024, 1, 1),
)

_PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/config",
    "/api/health",
}


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    if path.startswith("/ws/"):
        return True
    if path.startswith("/docs") or path.startswith("/openapi"):
        return True
    return False


async def get_current_user(request: Request) -> User:
    if app_config.mode == "dev":
        return _DEFAULT_ADMIN

    user = getattr(request.state, "current_user", None)
    if user is None:
        from domain.shared.business_exception import BusinessException
        raise BusinessException("Authentication required", "AUTH_REQUIRED")
    return user


class AuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        if app_config.mode == "dev":
            request.state.current_user = _DEFAULT_ADMIN
            return await call_next(request)

        if _is_public_path(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"code": -1, "message": "Authentication required", "data": None},
            )

        token = auth_header[7:]

        from application.auth.auth_application_service import AuthApplicationService
        from infr.config.database import async_session_factory
        from infr.repository.user_repository_impl import UserRepositoryImpl

        async with async_session_factory() as db_session:
            auth_svc = AuthApplicationService(UserRepositoryImpl(db_session))
            user_id = auth_svc.verify_token(token)
            if user_id is None:
                return JSONResponse(
                    status_code=401,
                    content={"code": -1, "message": "Invalid or expired token", "data": None},
                )
            user = await auth_svc.get_user_by_id(user_id)
            if user is None:
                return JSONResponse(
                    status_code=401,
                    content={"code": -1, "message": "User not found", "data": None},
                )
            request.state.current_user = user

        return await call_next(request)
