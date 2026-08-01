"""Correlation and safe request logging middleware."""

import logging
import re
import secrets
import time

from fastapi import FastAPI, Request, Response

CORRELATION_HEADER = "X-Correlation-ID"
_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
logger = logging.getLogger("tara_api")


def select_correlation_id(value: str | None) -> str:
    return value if value and _VALID_CORRELATION_ID.fullmatch(value) else secrets.token_urlsafe(18)


def install_request_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlate_and_log(request: Request, call_next) -> Response:
        request.state.correlation_id = select_correlation_id(request.headers.get(CORRELATION_HEADER))
        started = time.monotonic()
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = request.state.correlation_id
        logger.info(
            "request_completed",
            extra={
                "event_data": {
                    "correlation_id": request.state.correlation_id,
                    "method": request.method,
                    "route": getattr(request.scope.get("route"), "path", request.url.path),
                    "status": response.status_code,
                    "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
                }
            },
        )
        return response
