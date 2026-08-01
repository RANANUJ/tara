"""FastAPI adapters for Tara's safe, correlated application error envelope."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from tara_api.domain.errors import (
    ApplicationError,
    AuthenticationRequiredError,
    ErrorCode,
    InternalError,
    ResourceNotFoundError,
    ValidationError,
)

logger = logging.getLogger("tara_api")

HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_FAILED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.AUTHENTICATION_REQUIRED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.AUTHENTICATION_FAILED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.PERMISSION_DENIED: status.HTTP_403_FORBIDDEN,
    ErrorCode.RESOURCE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.RESOURCE_EXPIRED: status.HTTP_410_GONE,
    ErrorCode.DEPENDENCY_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.OPERATION_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ErrorCode.INVALID_STATE: status.HTTP_409_CONFLICT,
    ErrorCode.UNSUPPORTED_OPERATION: status.HTTP_501_NOT_IMPLEMENTED,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


def error_response(request: Request, error: ApplicationError) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": error.code.value,
            "message": error.public_message,
            "correlation_id": correlation_id(request),
            "retryable": error.retryable,
        }
    }
    if error.details:
        body["error"]["details"] = error.details
    return JSONResponse(status_code=HTTP_STATUS[error.code], content=body)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, error: ApplicationError) -> JSONResponse:
        return error_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        details = {
            ".".join(str(part) for part in item["loc"] if part != "body"): "Invalid value."
            for item in error.errors()
            if item.get("loc")
        }
        return error_response(request, ValidationError(details))

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
        mapped = ResourceNotFoundError() if error.status_code == status.HTTP_404_NOT_FOUND else AuthenticationRequiredError() if error.status_code == status.HTTP_401_UNAUTHORIZED else InternalError()
        return error_response(request, mapped)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        logger.exception("unexpected_request_error", extra={"event_data": {"correlation_id": correlation_id(request), "error_code": ErrorCode.INTERNAL_ERROR.value}})
        return error_response(request, InternalError())
