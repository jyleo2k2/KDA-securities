"""Shared date-range helpers for ingestion collectors."""

from datetime import date, timedelta


def weekdays(start: date, end: date) -> list[date]:
    if start > end:
        raise ValueError("from-date must not be after to-date")
    return [
        current
        for offset in range((end - start).days + 1)
        if (current := start + timedelta(days=offset)).weekday() < 5
    ]
