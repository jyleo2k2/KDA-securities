"""Deterministic historical macro-regime similarity analysis."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import BaseModel, ConfigDict, model_validator

ENGINE_NAME = "historical_macro_regime_similarity"
ENGINE_VERSION = "2026-07-20.1"
POLICY_VERSION = "macro-analog-regime-2026-07-20.1"
MACRO_REGIME_METRIC_IDS = (
    "kr_base_rate",
    "kr_cpi_yoy",
    "us_federal_funds_rate",
    "us_cpi_yoy",
    "us_treasury_10y",
    "us_breakeven_inflation_10y",
)
_QUANTUM = Decimal("0.0001")


class MonthlyMacroRegimeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    period: date
    values: dict[str, Decimal]

    @model_validator(mode="after")
    def validate_complete_month(self) -> MonthlyMacroRegimeObservation:
        if self.period.day != 1:
            raise ValueError("macro regime period must be the first day of a month")
        if set(self.values) != set(MACRO_REGIME_METRIC_IDS):
            raise ValueError("macro regime observation must contain all policy metrics")
        if any(not value.is_finite() for value in self.values.values()):
            raise ValueError("macro regime values must be finite")
        return self


class MacroRegimeMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    period: date
    distance: Decimal
    values: dict[str, Decimal]
    expanding_z_scores: dict[str, Decimal]


class MacroAnalogRegimeEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    policy_version: str
    current_period: date
    current_values: dict[str, Decimal]
    current_expanding_z_scores: dict[str, Decimal]
    metric_ids: list[str]
    frequency: str
    standardization: str
    distance_metric: str
    top_n: int
    minimum_history_months: int
    minimum_separation_months: int
    excluded_recent_months: int
    matches: list[MacroRegimeMatch]
    is_forecast: bool
    planning_return_input: bool
    allocation_weight_input: bool
    rebalancing_trigger_input: bool
    historical_outcomes_included: bool
    limitations: list[str]


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _month_distance(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _expanding_z_scores(
    rows: list[MonthlyMacroRegimeObservation],
) -> list[dict[str, Decimal]]:
    sums = {metric_id: Decimal("0") for metric_id in MACRO_REGIME_METRIC_IDS}
    squared_sums = {
        metric_id: Decimal("0") for metric_id in MACRO_REGIME_METRIC_IDS
    }
    results: list[dict[str, Decimal]] = []
    with localcontext() as context:
        context.prec = 28
        for count, row in enumerate(rows, start=1):
            scores: dict[str, Decimal] = {}
            divisor = Decimal(count)
            for metric_id in MACRO_REGIME_METRIC_IDS:
                value = row.values[metric_id]
                sums[metric_id] += value
                squared_sums[metric_id] += value * value
                mean = sums[metric_id] / divisor
                variance = squared_sums[metric_id] / divisor - mean * mean
                variance = max(variance, Decimal("0"))
                scores[metric_id] = (
                    Decimal("0")
                    if variance == 0
                    else (value - mean) / variance.sqrt()
                )
            results.append(scores)
    return results


def calculate_macro_analog_regimes(
    observations: list[MonthlyMacroRegimeObservation],
    *,
    top_n: int = 5,
    minimum_history_months: int = 36,
    minimum_separation_months: int = 12,
    excluded_recent_months: int = 12,
) -> MacroAnalogRegimeEvaluation:
    """Match the latest complete month to prior regimes without look-ahead."""

    if not 1 <= top_n <= 10:
        raise ValueError("top_n must be between 1 and 10")
    rows = sorted(observations, key=lambda row: row.period)
    if len({row.period for row in rows}) != len(rows):
        raise ValueError("macro regime periods must be unique")
    if len(rows) < minimum_history_months + excluded_recent_months + 1:
        raise ValueError("macro regime history is insufficient")

    z_scores = _expanding_z_scores(rows)
    current = rows[-1]
    current_scores = z_scores[-1]
    candidates: list[MacroRegimeMatch] = []
    with localcontext() as context:
        context.prec = 28
        metric_count = Decimal(len(MACRO_REGIME_METRIC_IDS))
        for index in range(minimum_history_months - 1, len(rows) - 1):
            row = rows[index]
            if _month_distance(current.period, row.period) < excluded_recent_months:
                continue
            squared_distance = sum(
                (
                    current_scores[metric_id] - z_scores[index][metric_id]
                )
                ** 2
                for metric_id in MACRO_REGIME_METRIC_IDS
            ) / metric_count
            candidates.append(
                MacroRegimeMatch(
                    period=row.period,
                    distance=_quantize(squared_distance.sqrt()),
                    values=row.values,
                    expanding_z_scores={
                        metric_id: _quantize(z_scores[index][metric_id])
                        for metric_id in MACRO_REGIME_METRIC_IDS
                    },
                )
            )

    selected: list[MacroRegimeMatch] = []
    for candidate in sorted(candidates, key=lambda item: (item.distance, item.period)):
        if all(
            abs(_month_distance(candidate.period, item.period))
            >= minimum_separation_months
            for item in selected
        ):
            selected.append(candidate)
        if len(selected) == top_n:
            break

    return MacroAnalogRegimeEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        current_period=current.period,
        current_values=current.values,
        current_expanding_z_scores={
            metric_id: _quantize(current_scores[metric_id])
            for metric_id in MACRO_REGIME_METRIC_IDS
        },
        metric_ids=list(MACRO_REGIME_METRIC_IDS),
        frequency="monthly",
        standardization="expanding_window_z_score",
        distance_metric="equal_weight_root_mean_square_distance",
        top_n=top_n,
        minimum_history_months=minimum_history_months,
        minimum_separation_months=minimum_separation_months,
        excluded_recent_months=excluded_recent_months,
        matches=selected,
        is_forecast=False,
        planning_return_input=False,
        allocation_weight_input=False,
        rebalancing_trigger_input=False,
        historical_outcomes_included=False,
        limitations=[
            "historical_similarity_does_not_imply_future_return",
            "historical_outcomes_are_not_part_of_this_contract",
            "macro_similarity_does_not_cover_all_market_risk_factors",
        ],
    )
