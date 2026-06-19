"""Global exception handlers and custom application error."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError


class AppError(Exception):
    """Raise this anywhere in the app to produce a clean HTTP error response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def jwt_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, JWTError)
    return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})


async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
