"""Structural long-term planning ensemble with explicit evidence gates."""

from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import SourceChip

ENGINE_NAME = "structural_long_term_return_ensemble"
ENGINE_VERSION = "2026-07-20.1"
POLICY_VERSION = "structural-return-ensemble-2026-07-20.1"
PERCENT_QUANTUM = Decimal("0.0001")
MINIMUM_CMA_PROVIDERS = 2
MINIMUM_STATISTICAL_HOLDOUT_VINTAGES = 3


class EquityBuildingBlocks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dividend_yield_percent: Decimal
    nominal_revenue_growth_percent: Decimal
    margin_change_percent_point: Decimal
    net_dilution_percent_point: Decimal
    valuation_change_annualized_percent_point: Decimal


class FixedIncomeBuildingBlocks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    coupon_income_percent: Decimal
    duration_impact_percent_point: Decimal
    curve_roll_down_percent_point: Decimal
    default_and_loss_percent_point: Decimal = Field(ge=0)


class RealAssetBuildingBlocks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    net_operating_yield_percent: Decimal
    maintenance_capex_percent_point: Decimal = Field(ge=0)
    net_cash_flow_growth_percent: Decimal
    exit_yield_adjustment_percent_point: Decimal
    leverage_adjustment_percent_point: Decimal
    fee_drag_percent_point: Decimal = Field(ge=0)


class CommodityBuildingBlocks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cash_return_percent: Decimal
    spot_premium_percent_point: Decimal
    roll_yield_percent_point: Decimal


class CmaEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    expected_return_percent: Decimal
    source: SourceChip


class StructuralEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_return_percent: Decimal
    method: str = Field(min_length=1)
    source: SourceChip


class StatisticalEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_return_percent: Decimal
    holdout_vintage_count: int = Field(ge=0)
    beats_cma_mae: bool
    beats_cma_rmse: bool
    independent_long_horizon_passed: bool
    source: SourceChip


class EquilibriumPrior(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_return_percent: Decimal
    view_confidence: Decimal = Field(ge=0, le=1)
    source: SourceChip


class StructuralEnsembleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_code: str = Field(min_length=1)
    horizon_years: int = Field(ge=10, le=15)
    cma_estimates: list[CmaEstimate] = Field(min_length=1)
    structural_estimate: StructuralEstimate | None = None
    statistical_estimate: StatisticalEstimate | None = None
    equilibrium_prior: EquilibriumPrior | None = None
    annual_cost_drag_percent: Decimal = Field(ge=0, le=10)
    tracking_drag_percent: Decimal = Field(default=Decimal("0"), ge=0, le=5)
    currency_hedge_drag_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=5
    )
    ensemble_external_validation_passed: bool = False

    @model_validator(mode="after")
    def require_distinct_cma_providers(self) -> StructuralEnsembleInput:
        providers = [item.provider for item in self.cma_estimates]
        if len(providers) != len(set(providers)):
            raise ValueError("CMA providers must be distinct")
        return self


class StructuralEnsembleEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    evaluated_input: StructuralEnsembleInput
    cma_consensus_percent: Decimal
    robust_view_percent: Decimal
    equilibrium_shrunk_percent: Decimal
    net_planning_return_percent: Decimal
    statistical_estimate_used: bool
    component_category_count: int
    readiness_status: str
    adoption_authorized: bool
    is_forecast: bool
    warnings: list[str]


class ResampledScenarioDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_count: int
    horizon_years: int
    block_size_years: int
    p10_annualized_percent: Decimal
    p50_annualized_percent: Decimal
    p90_annualized_percent: Decimal
    is_forecast: bool
    warning: str


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_equity_building_block(value: EquityBuildingBlocks) -> Decimal:
    return _percent(
        value.dividend_yield_percent
        + value.nominal_revenue_growth_percent
        + value.margin_change_percent_point
        - value.net_dilution_percent_point
        + value.valuation_change_annualized_percent_point
    )


def calculate_fixed_income_building_block(
    value: FixedIncomeBuildingBlocks,
) -> Decimal:
    return _percent(
        value.coupon_income_percent
        + value.duration_impact_percent_point
        + value.curve_roll_down_percent_point
        - value.default_and_loss_percent_point
    )


def calculate_real_asset_building_block(value: RealAssetBuildingBlocks) -> Decimal:
    return _percent(
        value.net_operating_yield_percent
        - value.maintenance_capex_percent_point
        + value.net_cash_flow_growth_percent
        + value.exit_yield_adjustment_percent_point
        + value.leverage_adjustment_percent_point
        - value.fee_drag_percent_point
    )


def calculate_commodity_building_block(value: CommodityBuildingBlocks) -> Decimal:
    return _percent(
        value.cash_return_percent
        + value.spot_premium_percent_point
        + value.roll_yield_percent_point
    )


def _statistical_gate(value: StatisticalEstimate | None) -> bool:
    return bool(
        value
        and value.holdout_vintage_count >= MINIMUM_STATISTICAL_HOLDOUT_VINTAGES
        and value.beats_cma_mae
        and value.beats_cma_rmse
        and value.independent_long_horizon_passed
    )


def calculate_structural_ensemble(
    assumption: StructuralEnsembleInput,
) -> StructuralEnsembleEvaluation:
    """Calculate a candidate planning assumption, never a return promise."""

    cma_consensus = Decimal(median(
        item.expected_return_percent for item in assumption.cma_estimates
    ))
    category_values = [cma_consensus]
    if assumption.structural_estimate is not None:
        category_values.append(assumption.structural_estimate.expected_return_percent)
    statistical_used = _statistical_gate(assumption.statistical_estimate)
    if statistical_used and assumption.statistical_estimate is not None:
        category_values.append(assumption.statistical_estimate.expected_return_percent)
    robust_view = Decimal(median(category_values))

    shrunk = robust_view
    if assumption.equilibrium_prior is not None:
        prior = assumption.equilibrium_prior
        shrunk = prior.expected_return_percent + prior.view_confidence * (
            robust_view - prior.expected_return_percent
        )
    net = (
        shrunk
        - assumption.annual_cost_drag_percent
        - assumption.tracking_drag_percent
        - assumption.currency_hedge_drag_percent
    )

    warnings = [
        "planning_assumption_not_return_forecast",
        "annual_review_required",
    ]
    if len(assumption.cma_estimates) < MINIMUM_CMA_PROVIDERS:
        warnings.append("single_cma_provider_no_consensus")
    if assumption.structural_estimate is None:
        warnings.append("structural_building_block_missing")
    if assumption.equilibrium_prior is None:
        warnings.append("equilibrium_prior_missing_no_black_litterman_shrinkage")
    if assumption.statistical_estimate is None:
        warnings.append("statistical_challenger_missing")
    elif not statistical_used:
        warnings.append("statistical_challenger_rejected_by_validation_gate")

    full_inputs = (
        len(assumption.cma_estimates) >= MINIMUM_CMA_PROVIDERS
        and assumption.structural_estimate is not None
        and assumption.equilibrium_prior is not None
        and statistical_used
    )
    readiness_status = "full_inputs_validated" if full_inputs else "partial_inputs"
    adoption_authorized = bool(
        full_inputs and assumption.ensemble_external_validation_passed
    )
    if not adoption_authorized:
        warnings.append("candidate_not_authorized_for_production_adoption")

    return StructuralEnsembleEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        usage_label="structural_ensemble_planning_candidate",
        evaluated_input=assumption,
        cma_consensus_percent=_percent(cma_consensus),
        robust_view_percent=_percent(robust_view),
        equilibrium_shrunk_percent=_percent(shrunk),
        net_planning_return_percent=_percent(net),
        statistical_estimate_used=statistical_used,
        component_category_count=len(category_values),
        readiness_status=readiness_status,
        adoption_authorized=adoption_authorized,
        is_forecast=False,
        warnings=warnings,
    )


def _quantile(values: list[float], probability: float) -> Decimal:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    result = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    return _percent(Decimal(str(result)))


def simulate_resampled_scenarios(
    *,
    center_percent: Decimal,
    historical_annual_residuals_percent: list[Decimal],
    horizon_years: int,
    scenario_count: int = 10_000,
    seed: int = 20260720,
    block_size_years: int = 3,
) -> ResampledScenarioDistribution:
    """Circular-block resample residuals to retain tails and short dependence."""

    if not 10 <= horizon_years <= 15:
        raise ValueError("horizon_years must be between 10 and 15")
    if len(historical_annual_residuals_percent) < 10:
        raise ValueError("at least 10 annual residuals are required")
    if scenario_count < 100:
        raise ValueError("scenario_count must be at least 100")
    if not 1 <= block_size_years <= len(historical_annual_residuals_percent):
        raise ValueError("block_size_years is outside the residual history")

    randomizer = random.Random(seed)
    residuals = [float(value) for value in historical_annual_residuals_percent]
    center = float(center_percent)
    annualized = []
    for _ in range(scenario_count):
        path_residuals = []
        while len(path_residuals) < horizon_years:
            start = randomizer.randrange(len(residuals))
            path_residuals.extend(
                residuals[(start + offset) % len(residuals)]
                for offset in range(block_size_years)
            )
        wealth = 1.0
        for residual in path_residuals[:horizon_years]:
            annual_return = center + residual
            wealth *= 1 + max(annual_return, -99.9) / 100
        annualized.append((wealth ** (1 / horizon_years) - 1) * 100)

    return ResampledScenarioDistribution(
        scenario_count=scenario_count,
        horizon_years=horizon_years,
        block_size_years=block_size_years,
        p10_annualized_percent=_quantile(annualized, 0.10),
        p50_annualized_percent=_quantile(annualized, 0.50),
        p90_annualized_percent=_quantile(annualized, 0.90),
        is_forecast=False,
        warning="resampled_diagnostic_scenarios_not_probability_forecast",
    )
