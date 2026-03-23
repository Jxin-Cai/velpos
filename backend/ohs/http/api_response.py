from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=0, description="Business status code, 0 means success")
    message: str = Field(default="ok", description="Response message")
    data: T | None = Field(default=None, description="Response data")

    @classmethod
    def success(cls, data: T | None = None) -> ApiResponse[T]:
        return cls(code=0, message="ok", data=data)

    @classmethod
    def fail(cls, code: int, message: str) -> ApiResponse[None]:
        return cls(code=code, message=message, data=None)
