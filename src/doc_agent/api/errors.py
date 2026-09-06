from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details)
    ).model_dump()


def http_error(status_code: int, code: str, message: str, details: Any = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_payload(code, message, details)["error"],
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body = {"error": detail}
    else:
        body = error_payload("http_error", str(detail))
    return JSONResponse(status_code=exc.status_code, content=body)


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "validation_error",
            "Request validation failed",
            details=exc.errors(),
        ),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_payload("internal_error", str(exc) or exc.__class__.__name__),
    )
