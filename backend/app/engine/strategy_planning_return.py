"""Deterministic planning-return assumptions for the home strategy cards.

These are fixed reference baskets. They are not ETF selections,
do not use a user's holdings, and must not be interpreted as forecasts.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from .educational_portfolio import (
    CMA_ASSUMPTIONS_PERCENT,
    CMA_POLICY_ID,
    CMA_SOURCE_AS_OF,
    POLICY_VERSION as PORTFOLIO_RISK_POLICY_VERSION,
    STRESS_POLICY,
)
from .models import SourceChip

PERCENT_QUANTUM = Decimal("0.0001")
STRATEGY_PLANNING_RETURN_POLICY_VERSION = "2026-07-28.1"


class StrategyStressScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_code: str
    estimated_loss_percent: Decimal = Field(ge=0)


class StrategyStressRiskEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worst_scenario_code: str
    worst_estimated_loss_percent: Decimal = Field(ge=0)
    scenarios: list[StrategyStressScenarioResult]
    policy_version: str
    source: SourceChip
    representative_basket_only: bool
    is_forecast: bool


class StrategyPlanningReturnComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cma_bucket: str
    target_percent: Decimal = Field(gt=0, le=100)
    cma_percent: Decimal = Field(ge=0)


class StrategyPlanningReturnEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    cma_weighted_return_percent: Decimal
    uncertainty_discount_percent: Decimal = Field(ge=0)
    net_planning_return_percent: Decimal
    components: list[StrategyPlanningReturnComponent]
    stress_risk: StrategyStressRiskEvaluation
    cma_policy_id: str
    policy_version: str
    sources: list[SourceChip]
    annual_review_required: bool
    is_forecast: bool
    warnings: list[str]


class _StrategyPlanningReturnPreset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    weights: dict[str, Decimal]
    uncertainty_discount_percent: Decimal
    warnings: tuple[str, ...] = ()


_PRESETS = (
    _StrategyPlanningReturnPreset(
        strategy_id="market_beta",
        weights={"global_equity": Decimal("100")},
        uncertainty_discount_percent=Decimal("0.25"),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="factor",
        weights={"global_equity": Decimal("100")},
        uncertainty_discount_percent=Decimal("0.40"),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="thematic",
        weights={"global_equity": Decimal("100")},
        uncertainty_discount_percent=Decimal("1.00"),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="top_down",
        weights={"global_60_40": Decimal("100")},
        uncertainty_discount_percent=Decimal("0.75"),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="bottom_up",
        weights={"global_equity": Decimal("100")},
        uncertainty_discount_percent=Decimal("0.75"),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="barbell",
        weights={
            "global_equity": Decimal("50"),
            "us_10y_treasury": Decimal("30"),
            "cash": Decimal("20"),
        },
        uncertainty_discount_percent=Decimal("0.75"),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="volatility_managed",
        weights={
            "us_large_cap_equity": Decimal("40"),
            "us_investment_grade_credit": Decimal("40"),
            "cash": Decimal("20"),
        },
        uncertainty_discount_percent=Decimal("0.75"),
        warnings=("low_volatility_equity_is_represented_by_us_large_cap_equity",),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="market_neutral",
        weights={
            "us_investment_grade_credit": Decimal("50"),
            "cash": Decimal("50"),
        },
        uncertainty_discount_percent=Decimal("0.75"),
        warnings=("market_neutral_alpha_is_not_assumed",),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="event_driven",
        weights={"global_equity": Decimal("50"), "cash": Decimal("50")},
        uncertainty_discount_percent=Decimal("0.75"),
        warnings=("event_driven_alpha_is_not_assumed",),
    ),
    _StrategyPlanningReturnPreset(
        strategy_id="trend_global_macro",
        weights={"global_60_40": Decimal("100")},
        uncertainty_discount_percent=Decimal("0.75"),
    ),
)


# The strategy cards use CMA reference buckets, while the approved stress policy
# uses portfolio sleeves. Keep the translation explicit so the UI never infers it.
_CMA_STRESS_SLEEVE_WEIGHTS = {
    "global_equity": {"core_equity": Decimal("100")},
    "us_large_cap_equity": {"core_equity": Decimal("100")},
    "us_10y_treasury": {"fixed_income": Decimal("100")},
    "us_investment_grade_credit": {"fixed_income": Decimal("100")},
    "cash": {"cash": Decimal("100")},
    "global_60_40": {
        "core_equity": Decimal("60"),
        "fixed_income": Decimal("40"),
    },
}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _source_chips() -> list[SourceChip]:
    return [
        SourceChip(
            label="J.P. Morgan 2026 Long-Term Capital Market Assumptions",
            reference=(
                "https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/"
                "portfolio-insights/ltcma/noindex/ltcma-full-report.pdf"
            ),
            as_of=CMA_SOURCE_AS_OF,
        ),
        SourceChip(
            label="홈 전략 카드 대표구성 정책",
            reference="backend/app/engine/strategy_planning_return.py",
            as_of=date(2026, 7, 24),
        ),
    ]


def _stress_source_chip() -> SourceChip:
    return SourceChip(
        label="연금 코파일럿 포트폴리오 스트레스 정책",
        reference="docs/30_스펙/포트폴리오_위험정책_계약.md",
        as_of=date(2026, 7, 22),
    )


def _calculate_stress_risk(
    weights: dict[str, Decimal],
) -> StrategyStressRiskEvaluation:
    scenarios: list[StrategyStressScenarioResult] = []
    for scenario_code, sleeve_shocks in STRESS_POLICY.items():
        estimated_return = Decimal("0")
        for cma_bucket, bucket_weight in weights.items():
            sleeve_weights = _CMA_STRESS_SLEEVE_WEIGHTS[cma_bucket]
            if sum(sleeve_weights.values(), Decimal("0")) != Decimal("100"):
                raise ValueError(f"{cma_bucket} stress sleeve weights must sum to 100")
            estimated_return += sum(
                (
                    bucket_weight
                    * sleeve_weight
                    * sleeve_shocks[sleeve]
                    / Decimal("10000")
                    for sleeve, sleeve_weight in sleeve_weights.items()
                ),
                Decimal("0"),
            )
        scenarios.append(
            StrategyStressScenarioResult(
                scenario_code=scenario_code,
                estimated_loss_percent=_quantize(-estimated_return),
            )
        )

    worst = max(scenarios, key=lambda scenario: scenario.estimated_loss_percent)
    return StrategyStressRiskEvaluation(
        worst_scenario_code=worst.scenario_code,
        worst_estimated_loss_percent=worst.estimated_loss_percent,
        scenarios=scenarios,
        policy_version=PORTFOLIO_RISK_POLICY_VERSION,
        source=_stress_source_chip(),
        representative_basket_only=True,
        is_forecast=False,
    )


def calculate_strategy_planning_returns() -> list[StrategyPlanningReturnEvaluation]:
    """Calculate all home-card values from fixed, documented CMA baskets."""

    outcomes: list[StrategyPlanningReturnEvaluation] = []
    for preset in _PRESETS:
        if sum(preset.weights.values(), Decimal("0")) != Decimal("100"):
            raise ValueError(f"{preset.strategy_id} weights must sum to 100")
        components = [
            StrategyPlanningReturnComponent(
                cma_bucket=bucket,
                target_percent=weight,
                cma_percent=CMA_ASSUMPTIONS_PERCENT[bucket],
            )
            for bucket, weight in preset.weights.items()
        ]
        weighted_return = sum(
            (
                component.target_percent * component.cma_percent / Decimal("100")
                for component in components
            ),
            Decimal("0"),
        )
        outcomes.append(
            StrategyPlanningReturnEvaluation(
                strategy_id=preset.strategy_id,
                cma_weighted_return_percent=_quantize(weighted_return),
                uncertainty_discount_percent=_quantize(
                    preset.uncertainty_discount_percent
                ),
                net_planning_return_percent=_quantize(
                    weighted_return - preset.uncertainty_discount_percent
                ),
                components=components,
                stress_risk=_calculate_stress_risk(preset.weights),
                cma_policy_id=CMA_POLICY_ID,
                policy_version=STRATEGY_PLANNING_RETURN_POLICY_VERSION,
                sources=_source_chips(),
                annual_review_required=True,
                is_forecast=False,
                warnings=[
                    "fixed_reference_basket",
                    "not_a_forecast_or_product_recommendation",
                    *preset.warnings,
                ],
            )
        )
    return outcomes
