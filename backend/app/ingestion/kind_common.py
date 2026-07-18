"""Shared HTTP/search/retry primitives for KIND ETF disclosure collectors."""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ._retry import retry_with_backoff
from .kind_distribution_client import KindDisclosureError

MAX_RETRIES = 3


def windows(start_date: date, end_date: date) -> list[tuple[date, date]]:
    if start_date > end_date:
        raise ValueError("from-date must not be after to-date")
    result = []
    current = start_date
    while current <= end_date:
        window_end = min(end_date, date(current.year, 12, 31))
        result.append((current, window_end))
        current = date(current.year + 1, 1, 1)
    return result


def request_with_retry(callback: Callable[[], bytes]) -> bytes:
    return retry_with_backoff(
        callback,
        exceptions=KindDisclosureError,
        is_retryable=lambda exc: exc.status_code in {None, 429}
        or (exc.status_code is not None and exc.status_code >= 500),
        max_retries=MAX_RETRIES,
    )


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")
