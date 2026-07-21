"""Shared error response contract for API routers."""

from enum import StrEnum

from fastapi import HTTPException
from pydantic import BaseModel


class ApiErrorCode(StrEnum):
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    DATABASE_NOT_CONFIGURED = "DATABASE_NOT_CONFIGURED"
    INVALID_DATE_RANGE = "INVALID_DATE_RANGE"


class ApiErrorResponse(BaseModel):
    code: ApiErrorCode
    message: str


def api_error(
    code: ApiErrorCode,
    message: str,
    status_code: int,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ApiErrorResponse(code=code, message=message).model_dump(mode="json"),
    )
