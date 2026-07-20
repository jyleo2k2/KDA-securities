"""Realized ETF outcomes following historical macro-regime matches."""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import BaseModel, ConfigDict

from .macro_regime import MacroRegimeMatch
from .models import SourceChip

ENGINE_NAME = "historical_macro_regime_etf_outcomes"
ENGINE_VERSION = "2026-07-20.1"
POLICY_VERSION = "macro-analog-etf-outcomes-2026-07-20.1"
OUTCOME_HORIZON_MONTHS = (3, 6, 12)
_MAX_BOUNDARY_LAG_DAYS = 7
_QUANTUM = Decimal("0.0001")


class RegimeHorizonOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_months: int
    start_date: date
    end_date: date
    total_return_percent: Decimal
    maximum_drawdown_percent: Decimal


class RegimeOutcomeGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_months: int
    reason: str


class EtfPostRegimeOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isu_code: str
    isu_name: str
    history_source: str | None
    source: SourceChip | None
    history_start: date | None
    history_end: date | None
    horizons: list[RegimeHorizonOutcome]
    gaps: list[RegimeOutcomeGap]


class MacroRegimeOutcomeGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    regime_period: date
    distance: Decimal
    etfs: list[EtfPostRegimeOutcome]


class MacroRegimeEtfOutcomeEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    policy_version: str
    outcome_start_rule: str
    boundary_lag_days: int
    groups: list[MacroRegimeOutcomeGroup]
    is_forecast: bool
    planning_return_input: bool
    allocation_weight_input: bool
    rebalancing_trigger_input: bool
    limitations: list[str]


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


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
    if source is None:
        return False
    return source == "kis_adjusted_close_plus_kind_cash_distribution" or (
        "total_return" in source
    )


def _etf_outcome(
    *,
    match: MacroRegimeMatch,
    isu_code: str,
    isu_name: str,
    history: dict[date, Decimal] | None,
    history_source: str | None,
    source_chip: SourceChip | None,
) -> EtfPostRegimeOutcome:
    dates = sorted(history or {})
    gaps: list[RegimeOutcomeGap] = []
    if not dates:
        gaps = [
            RegimeOutcomeGap(
                horizon_months=months,
                reason="total_return_history_unavailable",
            )
            for months in OUTCOME_HORIZON_MONTHS
        ]
    elif not _is_verified_total_return_source(history_source):
        gaps = [
            RegimeOutcomeGap(
                horizon_months=months,
                reason="verified_total_return_basis_unavailable",
            )
            for months in OUTCOME_HORIZON_MONTHS
        ]
    elif source_chip is None:
        gaps = [
            RegimeOutcomeGap(
                horizon_months=months,
                reason="source_chip_unavailable",
            )
            for months in OUTCOME_HORIZON_MONTHS
        ]

    horizons: list[RegimeHorizonOutcome] = []
    if not gaps:
        assert history is not None
        start_target = _add_months(match.period, 1)
        start = _first_observation_on_or_after(dates, start_target)
        for months in OUTCOME_HORIZON_MONTHS:
            if start is None:
                gaps.append(
                    RegimeOutcomeGap(
                        horizon_months=months,
                        reason="start_observation_unavailable",
                    )
                )
                continue
            start_index, start_date = start
            end_target = _add_months(start_target, months)
            end = _first_observation_on_or_after(dates, end_target)
            if end is None:
                gaps.append(
                    RegimeOutcomeGap(
                        horizon_months=months,
                        reason="end_observation_unavailable",
                    )
                )
                continue
            end_index, end_date = end
            if end_index <= start_index:
                gaps.append(
                    RegimeOutcomeGap(
                        horizon_months=months,
                        reason="outcome_window_incomplete",
                    )
                )
                continue
            window = [
                history[observed_on]
                for observed_on in dates[start_index : end_index + 1]
            ]
            with localcontext() as context:
                context.prec = 28
                total_return = (window[-1] / window[0] - Decimal("1")) * Decimal("100")
            horizons.append(
                RegimeHorizonOutcome(
                    horizon_months=months,
                    start_date=start_date,
                    end_date=end_date,
                    total_return_percent=_quantize(total_return),
                    maximum_drawdown_percent=_maximum_drawdown(window),
                )
            )

    return EtfPostRegimeOutcome(
        isu_code=isu_code,
        isu_name=isu_name,
        history_source=history_source,
        source=source_chip,
        history_start=dates[0] if dates else None,
        history_end=dates[-1] if dates else None,
        horizons=horizons,
        gaps=gaps,
    )


def calculate_post_regime_etf_outcomes(
    *,
    matches: list[MacroRegimeMatch],
    isu_codes: list[str],
    names_by_code: dict[str, str],
    histories: dict[str, dict[date, Decimal]],
    history_sources: dict[str, str],
    source_chips: dict[str, SourceChip],
) -> MacroRegimeEtfOutcomeEvaluation:
    """Calculate realized outcomes only; never infer missing observations."""

    codes = list(dict.fromkeys(isu_codes))
    if not codes:
        raise ValueError("at least one ETF code is required")
    groups = [
        MacroRegimeOutcomeGroup(
            regime_period=match.period,
            distance=match.distance,
            etfs=[
                _etf_outcome(
                    match=match,
                    isu_code=code,
                    isu_name=names_by_code.get(code, code),
                    history=histories.get(code),
                    history_source=history_sources.get(code),
                    source_chip=source_chips.get(code),
                )
                for code in codes
            ],
        )
        for match in matches
    ]
    return MacroRegimeEtfOutcomeEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        outcome_start_rule="first_trading_day_of_month_after_regime",
        boundary_lag_days=_MAX_BOUNDARY_LAG_DAYS,
        groups=groups,
        is_forecast=False,
        planning_return_input=False,
        allocation_weight_input=False,
        rebalancing_trigger_input=False,
        limitations=[
            "historical_similarity_does_not_imply_future_return",
            "only_verified_total_return_histories_are_calculated",
            "missing_boundaries_are_not_interpolated",
            "older_regimes_may_precede_etf_listing_or_data_coverage",
        ],
    )
