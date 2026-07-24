"""Descriptive realized ETF outcomes following verified historical news events.

This module calculates past total-return windows only.  Its output is explicitly
excluded from planning returns, allocation weights, and rebalancing triggers.
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import BaseModel, ConfigDict, Field

from .models import SourceChip

ENGINE_NAME = "historical_news_event_etf_outcomes"
ENGINE_VERSION = "2026-07-24.1"
POLICY_VERSION = "news-event-outcomes-2026-07-24.1"
OUTCOME_HORIZON_MONTHS = (1, 3, 6)
_MAX_BOUNDARY_LAG_DAYS = 14
_QUANTUM = Decimal("0.0001")


class HistoricalNewsEvent(BaseModel):
    """One manually verified past event and its descriptive ETF comparison set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    occurred_on: date
    theme_id: str = Field(pattern=r"^[a-z0-9_]+$")
    peer_isu_codes: tuple[str, ...] = Field(min_length=1)
    source: SourceChip


class NewsEventHorizonOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_months: int
    start_date: date
    end_date: date
    total_return_percent: Decimal
    maximum_drawdown_percent: Decimal
    peer_median_total_return_percent: Decimal
    peer_sample_count: int = Field(ge=1)


class NewsEventOutcomeGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_months: int
    reason: str


class NewsEventEtfOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    occurred_on: date
    theme_id: str
    event_source: SourceChip
    isu_code: str
    isu_name: str
    history_source: str | None
    history_source_chip: SourceChip | None
    horizons: list[NewsEventHorizonOutcome]
    gaps: list[NewsEventOutcomeGap]


class NewsEventHorizonSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_months: int
    event_sample_count: int = Field(ge=0)
    etf_outcome_sample_count: int = Field(ge=0)
    median_total_return_percent: Decimal | None
    median_maximum_drawdown_percent: Decimal | None


class NewsEventOutcomeEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    policy_version: str
    outcome_start_rule: str
    boundary_lag_days: int
    outcomes: list[NewsEventEtfOutcome]
    summaries: list[NewsEventHorizonSummary]
    is_forecast: bool
    planning_return_input: bool
    allocation_weight_input: bool
    rebalancing_trigger_input: bool
    limitations: list[str]


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    day = min(value.day, 28)
    return date(month_index // 12, month_index % 12 + 1, day)


def _first_observation_on_or_after(
    dates: list[date], target: date
) -> tuple[int, date] | None:
    index = bisect_left(dates, target)
    if index >= len(dates):
        return None
    observed_on = dates[index]
    if observed_on - target > timedelta(days=_MAX_BOUNDARY_LAG_DAYS):
        return None
    return index, observed_on


def _maximum_drawdown(values: list[Decimal]) -> Decimal:
    peak = values[0]
    maximum = Decimal("0")
    for value in values:
        peak = max(peak, value)
        maximum = max(maximum, (peak - value) / peak)
    return _quantize(maximum * Decimal("100"))


def _is_verified_total_return_source(source: str | None) -> bool:
    return source == "kis_adjusted_close_plus_kind_cash_distribution" or (
        source is not None and "total_return" in source
    )


def _window_outcome(
    *,
    event: HistoricalNewsEvent,
    months: int,
    history: dict[date, Decimal] | None,
    history_source: str | None,
    source_chip: SourceChip | None,
) -> tuple[dict[str, object] | None, str | None]:
    dates = sorted(history or {})
    if not dates:
        return None, "total_return_history_unavailable"
    if not _is_verified_total_return_source(history_source):
        return None, "verified_total_return_basis_unavailable"
    if source_chip is None:
        return None, "source_chip_unavailable"
    start = _first_observation_on_or_after(dates, event.occurred_on)
    if start is None:
        return (
            None,
            "outcome_precedes_history_coverage"
            if event.occurred_on < dates[0]
            else "start_observation_unavailable",
        )
    end_target = _add_months(event.occurred_on, months)
    end = _first_observation_on_or_after(dates, end_target)
    if end is None:
        return (
            None,
            "outcome_exceeds_history_coverage"
            if end_target > dates[-1]
            else "end_observation_unavailable",
        )
    start_index, start_date = start
    end_index, end_date = end
    if end_index <= start_index:
        return None, "outcome_window_incomplete"
    values = [
        history[observed_on] for observed_on in dates[start_index : end_index + 1]
    ]
    with localcontext() as context:
        context.prec = 28
        total_return = (values[-1] / values[0] - Decimal("1")) * Decimal("100")
    return (
        {
            "end_date": end_date,
            "maximum_drawdown_percent": _maximum_drawdown(values),
            "start_date": start_date,
            "total_return_percent": _quantize(total_return),
        },
        None,
    )


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return _quantize((ordered[middle - 1] + ordered[middle]) / Decimal("2"))


def calculate_news_event_outcomes(
    *,
    events: list[HistoricalNewsEvent],
    names_by_code: dict[str, str],
    histories: dict[str, dict[date, Decimal]],
    history_sources: dict[str, str],
    source_chips: dict[str, SourceChip],
) -> NewsEventOutcomeEvaluation:
    """Calculate descriptive post-event outcomes; missing observations stay gaps."""

    outcomes: list[NewsEventEtfOutcome] = []
    all_horizons: dict[int, list[NewsEventEtfOutcome]] = {
        months: [] for months in OUTCOME_HORIZON_MONTHS
    }
    for event in events:
        by_code: dict[str, dict[int, dict[str, object]]] = {}
        gaps_by_code: dict[str, list[NewsEventOutcomeGap]] = {}
        for code in dict.fromkeys(event.peer_isu_codes):
            horizon_rows: dict[int, dict[str, object]] = {}
            gaps: list[NewsEventOutcomeGap] = []
            for months in OUTCOME_HORIZON_MONTHS:
                row, gap = _window_outcome(
                    event=event,
                    months=months,
                    history=histories.get(code),
                    history_source=history_sources.get(code),
                    source_chip=source_chips.get(code),
                )
                if row is not None:
                    horizon_rows[months] = row
                else:
                    gaps.append(
                        NewsEventOutcomeGap(
                            horizon_months=months, reason=gap or "unknown"
                        )
                    )
            by_code[code] = horizon_rows
            gaps_by_code[code] = gaps

        peer_rows = {
            months: [rows[months] for rows in by_code.values() if months in rows]
            for months in OUTCOME_HORIZON_MONTHS
        }
        for code in dict.fromkeys(event.peer_isu_codes):
            horizons = []
            for months, row in by_code[code].items():
                peers = peer_rows[months]
                horizons.append(
                    NewsEventHorizonOutcome(
                        horizon_months=months,
                        peer_median_total_return_percent=_median(
                            [
                                Decimal(str(peer["total_return_percent"]))
                                for peer in peers
                            ]
                        ),
                        peer_sample_count=len(peers),
                        **row,
                    )
                )
            outcome = NewsEventEtfOutcome(
                event_id=event.event_id,
                occurred_on=event.occurred_on,
                theme_id=event.theme_id,
                event_source=event.source,
                isu_code=code,
                isu_name=names_by_code.get(code, code),
                history_source=history_sources.get(code),
                history_source_chip=source_chips.get(code),
                horizons=sorted(horizons, key=lambda item: item.horizon_months),
                gaps=gaps_by_code[code],
            )
            outcomes.append(outcome)
            for horizon in outcome.horizons:
                all_horizons[horizon.horizon_months].append(outcome)

    summaries = []
    for months in OUTCOME_HORIZON_MONTHS:
        rows = [
            horizon
            for outcome in all_horizons[months]
            for horizon in outcome.horizons
            if horizon.horizon_months == months
        ]
        summaries.append(
            NewsEventHorizonSummary(
                horizon_months=months,
                event_sample_count=len(
                    {outcome.event_id for outcome in all_horizons[months]}
                ),
                etf_outcome_sample_count=len(rows),
                median_total_return_percent=(
                    _median([row.total_return_percent for row in rows])
                    if rows
                    else None
                ),
                median_maximum_drawdown_percent=(
                    _median([row.maximum_drawdown_percent for row in rows])
                    if rows
                    else None
                ),
            )
        )
    return NewsEventOutcomeEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        outcome_start_rule="first_trading_day_on_or_after_event_date",
        boundary_lag_days=_MAX_BOUNDARY_LAG_DAYS,
        outcomes=outcomes,
        summaries=summaries,
        is_forecast=False,
        planning_return_input=False,
        allocation_weight_input=False,
        rebalancing_trigger_input=False,
        limitations=[
            "historical_news_events_are_descriptive_not_predictive",
            "only_verified_total_return_histories_are_calculated",
            "missing_boundaries_are_not_interpolated",
            "results_must_not_change_allocation_or_orders",
        ],
    )
