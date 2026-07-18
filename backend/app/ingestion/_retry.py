"""Shared retry-with-backoff helpers for ingestion HTTP clients."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    callback: Callable[[], T],
    *,
    exceptions: type[Exception] | tuple[type[Exception], ...],
    is_retryable: Callable[[Any], bool],
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return callback()
        except exceptions as exc:
            last_error = exc
            if not is_retryable(exc) or attempt == max_retries:
                break
            sleep(2**attempt)
    assert last_error is not None
    raise last_error


async def async_retry_with_backoff(
    callback: Callable[[], Awaitable[T]],
    *,
    exceptions: type[Exception] | tuple[type[Exception], ...],
    is_retryable: Callable[[Any], bool],
    max_retries: int = 3,
) -> T:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await callback()
        except exceptions as exc:
            last_error = exc
            if not is_retryable(exc) or attempt == max_retries:
                break
            await asyncio.sleep(2**attempt)
    assert last_error is not None
    raise last_error
