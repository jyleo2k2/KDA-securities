"""Style-level planning returns from CMA, shrunk history, and macro scenarios."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from .models import SourceChip

ENGINE_NAME = "etf_style_planning_return"
ENGINE_VERSION = "2026-07-20.1"
POLICY_VERSION = "style-planning-return-2026-07-20.1"
PERCENT_QUANTUM = Decimal("0.0001")
HISTORICAL_ADJUSTMENT_CAP = Decimal("1.0000")
MACRO_ADJUSTMENT_CAP = Decimal("0.5000")
RANGE_WIDTH_CAP = Decimal("2.0000")
HISTORICAL_WEIGHTS = {
    "5y": Decimal("0.20"),
    "3y": Decimal("0.12"),
    "1y": Decimal("0.05"),
}


class MacroRevisionSignals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    region: str
    growth_revision_percent_point: Decimal
    inflation_revision_percent_point: Decimal
    policy_rate_revision_percent_point: Decimal
    uncertainty_level: str
    missing_signal_ids: list[str] = Field(default_factory=list)


class MacroSensitivities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    growth: Decimal
    inflation: Decimal
    policy_rate: Decimal


class StylePlanningReturnInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    etf_code: str = Field(min_length=1)
    style_key: str = Field(min_length=1)
    cma_assumption_code: str = Field(min_length=1)
    cma_percent: Decimal
    historical_annualized_return_percent: Decimal
    historical_period: str
    historical_peer_count: int = Field(ge=1)
    macro_signals: MacroRevisionSignals
    macro_sensitivities: MacroSensitivities
    uncertainty_discount_percent: Decimal = Field(ge=0)
    annual_cost_drag_percent: Decimal = Field(ge=0)
    sources: list[SourceChip] = Field(min_length=3)


class StylePlanningReturnEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    evaluated_input: StylePlanningReturnInput
    historical_weight: Decimal
    historical_gap_percent_point: Decimal
    historical_adjustment_percent_point: Decimal
    macro_raw_adjustment_percent_point: Decimal
    macro_adjustment_percent_point: Decimal
    gross_planning_return_percent: Decimal
    net_planning_return_percent: Decimal
    conservative_planning_return_percent: Decimal
    optimistic_planning_return_percent: Decimal
    range_width_percent_point: Decimal
    is_forecast: bool
    warnings: list[str]


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, limit: Decimal) -> Decimal:
    return max(-limit, min(limit, value))


def style_macro_sensitivities(
    *, asset_class: str, strategy: str
) -> MacroSensitivities:
    """Return bounded policy sensitivities for a classified ETF style."""

    if asset_class == "equity":
        if strategy == "sector_or_theme":
            values = ("0.35", "-0.15", "-0.20")
        elif strategy in {"dividend", "factor", "covered_call"}:
            values = ("0.20", "-0.05", "-0.05")
        else:
            values = ("0.25", "-0.10", "-0.10")
    elif asset_class == "fixed_income":
        values = ("-0.10", "-0.15", "0.25")
    elif asset_class == "cash_equivalent":
        values = ("0", "0", "0.25")
    elif asset_class == "real_estate":
        values = ("0.15", "0.10", "-0.20")
    elif asset_class == "commodity":
        values = (
            ("0", "0.25", "-0.20")
            if strategy == "gold"
            else ("0.20", "0.20", "0")
        )
    elif asset_class == "multi_asset":
        values = ("0.15", "-0.05", "-0.05")
    else:
        values = ("0.10", "0", "0")
    return MacroSensitivities(
        growth=Decimal(values[0]),
        inflation=Decimal(values[1]),
        policy_rate=Decimal(values[2]),
    )


def calculate_style_planning_return(
    assumption: StylePlanningReturnInput,
) -> StylePlanningReturnEvaluation:
    """Calculate an educational range; never label it a realized-return forecast."""

    try:
        historical_weight = HISTORICAL_WEIGHTS[assumption.historical_period]
    except KeyError as exc:
        raise ValueError("historical period must be one of 1y, 3y, or 5y") from exc

    historical_gap = (
        assumption.historical_annualized_return_percent - assumption.cma_percent
    )
    historical_adjustment = _clamp(
        historical_gap * historical_weight,
        HISTORICAL_ADJUSTMENT_CAP,
    )
    signals = assumption.macro_signals
    sensitivities = assumption.macro_sensitivities
    macro_raw = (
        signals.growth_revision_percent_point * sensitivities.growth
        + signals.inflation_revision_percent_point * sensitivities.inflation
        + signals.policy_rate_revision_percent_point * sensitivities.policy_rate
    )
    macro_adjustment = _clamp(macro_raw, MACRO_ADJUSTMENT_CAP)
    gross = (
        assumption.cma_percent
        + historical_adjustment
        + macro_adjustment
        - assumption.uncertainty_discount_percent
    )
    net = gross - assumption.annual_cost_drag_percent
    uncertainty_extra = (
        Decimal("0.25")
        if assumption.macro_signals.uncertainty_level == "high"
        else Decimal("0")
    )
    range_width = min(
        RANGE_WIDTH_CAP,
        max(
            Decimal("0.75"),
            assumption.uncertainty_discount_percent
            + abs(historical_adjustment) / Decimal("2")
            + abs(macro_adjustment) / Decimal("2")
            + uncertainty_extra,
        ),
    )
    warnings = [
        "planning_assumption_not_realized_return_prediction",
        "historical_style_return_is_shrunk_and_capped",
        "macro_forecast_revision_is_bounded_scenario_input",
        "scenario_range_has_no_probability_attached",
    ]
    if assumption.macro_signals.missing_signal_ids:
        warnings.append("missing_macro_signals_neutralized_to_zero")
    if assumption.historical_peer_count < 5:
        warnings.append("historical_peer_count_below_preferred_minimum")

    return StylePlanningReturnEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        usage_label="annualized_style_planning_assumption_not_forecast",
        evaluated_input=assumption,
        historical_weight=_percent(historical_weight),
        historical_gap_percent_point=_percent(historical_gap),
        historical_adjustment_percent_point=_percent(historical_adjustment),
        macro_raw_adjustment_percent_point=_percent(macro_raw),
        macro_adjustment_percent_point=_percent(macro_adjustment),
        gross_planning_return_percent=_percent(gross),
        net_planning_return_percent=_percent(net),
        conservative_planning_return_percent=_percent(net - range_width),
        optimistic_planning_return_percent=_percent(net + range_width),
        range_width_percent_point=_percent(range_width),
        is_forecast=False,
        warnings=warnings,
    )
