"""Deterministic windows and quality gates for official ETF distribution refreshes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

KIND_CORRECTION_LOOKBACK_DAYS = 45
KIS_SCHEDULE_LOOKAHEAD_DAYS = 120
MAX_CONFIRMED_EVENT_DROP_RATIO = 0.30
KIND_HISTORY_START = date(2020, 1, 1)


class DistributionRefreshQuarantined(ValueError):
    """Raised before loading when refreshed official history drops too far."""


@dataclass(frozen=True, slots=True)
class DistributionRefreshWindow:
    kind_from: date
    kind_to: date
    kis_from: date
    kis_to: date


def build_refresh_window(
    *, latest_ready_as_of: date | None, today: date
) -> DistributionRefreshWindow:
    kind_from = (
        KIND_HISTORY_START
        if latest_ready_as_of is None
        else max(
            KIND_HISTORY_START,
            latest_ready_as_of - timedelta(days=KIND_CORRECTION_LOOKBACK_DAYS),
        )
    )
    return DistributionRefreshWindow(
        kind_from=kind_from,
        kind_to=today,
        kis_from=today,
        kis_to=today + timedelta(days=KIS_SCHEDULE_LOOKAHEAD_DAYS),
    )


def merge_distribution_events(
    *,
    previous_events: list[dict[str, Any]],
    refreshed_events: list[dict[str, Any]],
    kind_from: date,
) -> list[dict[str, Any]]:
    """Keep old confirmed history outside the correction window; replace schedules."""

    old_confirmed = [event for event in previous_events if _is_confirmed(event)]
    new_confirmed = [event for event in refreshed_events if _is_confirmed(event)]
    _ensure_confirmed_history_not_eroded(
        previous_events=old_confirmed,
        refreshed_events=new_confirmed,
        kind_from=kind_from,
    )
    preserved = [
        event
        for event in old_confirmed
        if date.fromisoformat(str(event["effective_date"])) < kind_from
    ]
    schedules = [
        event for event in refreshed_events if not _is_confirmed(event)
    ]
    return _deduplicate_events([*preserved, *new_confirmed, *schedules])


def _is_confirmed(event: dict[str, Any]) -> bool:
    return event.get("status") != "excluded_from_historical_total_return"


def _ensure_confirmed_history_not_eroded(
    *,
    previous_events: list[dict[str, Any]],
    refreshed_events: list[dict[str, Any]],
    kind_from: date,
) -> None:
    previous_count = sum(
        date.fromisoformat(str(event["effective_date"])) >= kind_from
        for event in previous_events
    )
    refreshed_count = sum(
        date.fromisoformat(str(event["effective_date"])) >= kind_from
        for event in refreshed_events
    )
    if previous_count and refreshed_count < previous_count * (
        1 - MAX_CONFIRMED_EVENT_DROP_RATIO
    ):
        raise DistributionRefreshQuarantined(
            "confirmed KIND event count declined by more than 30% in correction window"
        )


def _deduplicate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {
        json.dumps(
            event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ): event
        for event in events
    }
    return [unique[key] for key in sorted(unique)]
