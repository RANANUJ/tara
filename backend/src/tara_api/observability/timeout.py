"""Cancellation-safe bounded execution helper for backend operations."""

import asyncio
from collections.abc import Awaitable

from tara_api.domain.errors import OperationTimeoutError


async def run_with_timeout[Result](operation: Awaitable[Result], timeout_seconds: float) -> Result:
    """Await one operation without retries and convert expiry into a typed error."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    try:
        async with asyncio.timeout(timeout_seconds):
            return await operation
    except TimeoutError as error:
        raise OperationTimeoutError from error
