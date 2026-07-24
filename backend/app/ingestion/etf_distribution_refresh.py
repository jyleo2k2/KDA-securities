"""Deterministic windows and quality gates for official ETF distribution refreshes."""

from __future__ import annotations

import json
from collections import Counter
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
    """Replace only refreshable distribution evidence and retain other history."""

    old_confirmed = [event for event in previous_events if _is_confirmed_cash(event)]
    new_confirmed = [event for event in refreshed_events if _is_confirmed_cash(event)]
    _ensure_confirmed_history_not_eroded(
        previous_events=old_confirmed,
        refreshed_events=new_confirmed,
        kind_from=kind_from,
    )
    preserved = [
        event
        for event in previous_events
        if _preserve_previous_event(event, kind_from=kind_from)
    ]
    refreshed = [
        event for event in refreshed_events if _is_refreshable_distribution_event(event)
    ]
    return _deduplicate_events([*preserved, *refreshed])


def _is_confirmed_cash(event: dict[str, Any]) -> bool:
    return (
        event.get("event_type") == "cash_distribution"
        and event.get("status") == "confirmed_cash_flow"
    )


def _is_refreshable_distribution_event(event: dict[str, Any]) -> bool:
    return event.get("event_type") in {
        "cash_distribution",
        "distribution_ex_date_unmatched",
        "scheduled_cash_distribution",
    }


def _preserve_previous_event(event: dict[str, Any], *, kind_from: date) -> bool:
    if not _is_refreshable_distribution_event(event):
        return True
    if event.get("event_type") != "cash_distribution":
        return False
    return date.fromisoformat(str(event["effective_date"])) < kind_from


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
            event,
            default=_json_default,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ): event
        for event in events
    }
    return [json.loads(key) for key in sorted(unique)]


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"unsupported event value: {type(value).__name__}")


def build_refreshed_event_master(
    *,
    previous_master: dict[str, Any],
    refreshed_master: dict[str, Any],
    kind_from: date,
) -> dict[str, Any]:
    """Return a loadable master without silently dropping non-distribution history."""

    previous_events = previous_master.get("events")
    refreshed_events = refreshed_master.get("events")
    if not isinstance(previous_events, list) or not all(
        isinstance(event, dict) for event in previous_events
    ):
        raise ValueError("previous event master must contain event objects")
    if not isinstance(refreshed_events, list) or not all(
        isinstance(event, dict) for event in refreshed_events
    ):
        raise ValueError("refreshed event master must contain event objects")

    events = merge_distribution_events(
        previous_events=previous_events,
        refreshed_events=refreshed_events,
        kind_from=kind_from,
    )
    result = dict(refreshed_master)
    result["events"] = events
    result["event_count"] = len(events)
    result["event_type_counts"] = dict(
        sorted(Counter(str(event.get("event_type")) for event in events).items())
    )
    result["cash_distribution_count"] = sum(
        event.get("event_type") == "cash_distribution" for event in events
    )
    result["refresh_policy"] = {
        "kind_correction_from": kind_from.isoformat(),
        "preserve_non_distribution_history": True,
        "quarantine_confirmed_cash_drop_ratio": MAX_CONFIRMED_EVENT_DROP_RATIO,
    }
    return result
