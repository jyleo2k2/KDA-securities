import statistics
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import AccountType, SourceChip
from .planning_return import (
    EtfPlanningReturnInput,
    PlanningReturnSources,
    calculate_etf_planning_return,
)

ENGINE_NAME = "educational_pension_portfolio"
ENGINE_VERSION = "2026-07-16.4"
POLICY_VERSION = "2026-07-16.2"
PERCENT_QUANTUM = Decimal("0.0001")
DRIFT_THRESHOLD_PERCENT = Decimal("5")
RETIREMENT_RISK_CAP_PERCENT = Decimal("70")
TRADING_DAYS_PER_YEAR = Decimal("252")
MINIMUM_RISK_OBSERVATIONS = 60
CMA_POLICY_ID = "jpm_2026_usd_educational_v1"
CMA_SOURCE_AS_OF = date(2025, 9, 30)
CMA_HORIZON_MIN_YEARS = 10
CMA_HORIZON_MAX_YEARS = 15
CMA_ASSUMPTIONS_PERCENT = {
    "cash": Decimal("3.1"),
    "us_10y_treasury": Decimal("4.6"),
    "us_investment_grade_credit": Decimal("5.2"),
    "us_high_yield": Decimal("6.1"),
    "us_large_cap_equity": Decimal("6.7"),
    "global_equity": Decimal("7.0"),
    "emerging_markets_equity": Decimal("7.8"),
    "global_reit": Decimal("8.7"),
    "broad_commodities": Decimal("4.6"),
    "gold": Decimal("5.5"),
    "global_60_40": Decimal("6.4"),
}


class RiskProfile(StrEnum):
    STABLE = "stable"
    STABLE_SEEKING = "stable_seeking"
    RISK_NEUTRAL = "risk_neutral"
    ACTIVE = "active"
    AGGRESSIVE = "aggressive"


class CurrentHolding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isu_code: str = Field(min_length=1)
    amount_krw: Decimal = Field(ge=0, allow_inf_nan=False)


class EducationalPortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType
    age: int = Field(ge=20, le=54)
    retirement_start_age: int = Field(default=55, ge=55, le=60)
    risk_profile: RiskProfile
    loss_tolerance_percent: Decimal = Field(
        ge=Decimal("1"), le=Decimal("50"), allow_inf_nan=False
    )
    max_etfs: int = Field(default=7, ge=5, le=8)
    current_holdings: list[CurrentHolding] = Field(default_factory=list)
    new_contribution_krw: Decimal = Field(
        default=Decimal("0"), ge=0, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def require_a_portfolio_value_for_rebalancing(
        self,
    ) -> "EducationalPortfolioInput":
        if self.retirement_start_age <= self.age:
            raise ValueError("retirement_start_age must be greater than age")
        if (
            self.current_holdings
            and sum((item.amount_krw for item in self.current_holdings), Decimal("0"))
            <= 0
        ):
            raise ValueError("current holdings must have a positive total")
        return self


class SleeveTarget(BaseModel):
    sleeve: str
    target_percent: Decimal
    risk_treatment: str
    role: str


class CandidateQuality(BaseModel):
    total_score: Decimal
    fee_efficiency: Decimal
    liquidity: Decimal
    size: Decimal
    nav_quality: Decimal
    tracking_quality: Decimal
    history_depth: Decimal


class EducationalEtfCandidate(BaseModel):
    isu_code: str
    isu_name: str
    sleeve: str
    target_percent: Decimal
    quality: CandidateQuality
    region: str | None
    strategy: str | None
    max_correlation_with_selected: Decimal | None
    price_history_source: str
    account_eligibility: dict[str, Any]
    reasons: list[str]


class RebalancingSleeveGuidance(BaseModel):
    sleeve: str
    target_percent: Decimal
    current_percent: Decimal
    projected_percent_after_contribution: Decimal
    drift_before_percent_points: Decimal
    drift_after_percent_points: Decimal
    contribution_example_krw: Decimal
    status: str


class RebalancingGuidance(BaseModel):
    status: str
    drift_threshold_percent_points: Decimal
    current_total_krw: Decimal
    new_contribution_krw: Decimal
    projected_total_krw: Decimal
    unclassified_holding_amount_krw: Decimal
    contribution_first: bool
    sell_instruction_produced: bool
    sleeves: list[RebalancingSleeveGuidance]
    warnings: list[str]


class StressScenarioResult(BaseModel):
    scenario_code: str
    estimated_loss_percent: Decimal
    sleeve_shocks_percent: dict[str, Decimal]
    is_forecast: bool


class PortfolioRiskEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    status: str
    observation_count: int
    observation_start: date | None
    observation_end: date | None
    annualized_volatility_percent: Decimal | None
    annualized_downside_deviation_percent: Decimal | None
    maximum_drawdown_percent: Decimal | None
    historical_95pct_one_day_loss_percent: Decimal | None
    worst_daily_return_percent: Decimal | None
    historical_return_used_for_risk_only: bool
    is_return_forecast: bool
    stress_scenarios: list[StressScenarioResult]
    sources: list[SourceChip]
    warnings: list[str]


class PortfolioPlanningComponent(BaseModel):
    isu_code: str
    isu_name: str
    sleeve: str
    target_percent: Decimal
    cma_assumption_code: str
    cma_percent: Decimal
    uncertainty_discount_percent: Decimal
    annual_cost_drag_percent: Decimal
    gross_planning_return_percent: Decimal
    net_planning_return_percent: Decimal
    proxy_used: bool
    warnings: list[str]


class PortfolioPlanningEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    policy_version: str
    cma_policy_id: str
    cma_policy_status: str
    usage_label: str
    retirement_start_age: int
    portfolio_horizon_years: int
    cma_source_horizon_min_years: int
    cma_source_horizon_max_years: int
    annual_review_required: bool
    coverage_weight_percent: Decimal
    gross_planning_return_percent: Decimal | None
    net_planning_return_percent: Decimal | None
    conservative_planning_return_percent: Decimal | None
    base_planning_return_percent: Decimal | None
    is_forecast: bool
    historical_performance_used: bool
    risk_adjustment_included: bool
    components: list[PortfolioPlanningComponent]
    sources: list[SourceChip]
    warnings: list[str]


class EducationalPortfolioEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    evaluated_input: EducationalPortfolioInput
    strategy_label: str
    retirement_start_age: int
    planning_horizon_years: int
    horizon_to_age_55_years: int
    horizon_to_age_60_years: int
    raw_risk_target_percent: Decimal
    final_general_risk_target_percent: Decimal
    account_risk_cap_percent: Decimal | None
    account_cap_binding: bool
    loss_tolerance_binding: bool
    stress_loss_proxy_percent: Decimal
    target_sleeves: list[SleeveTarget]
    candidates: list[EducationalEtfCandidate]
    portfolio_risk: PortfolioRiskEvaluation
    planning_return: PortfolioPlanningEvaluation
    rebalancing: RebalancingGuidance
    sources: list[SourceChip]
    warnings: list[str]


PROFILE_POLICY = {
    RiskProfile.STABLE: {
        "base_risk": Decimal("20"),
        "minimum": Decimal("5"),
        "maximum": Decimal("30"),
        "tactical": Decimal("0"),
        "cash": Decimal("15"),
        "strategy": "capital_preservation_core",
    },
    RiskProfile.STABLE_SEEKING: {
        "base_risk": Decimal("35"),
        "minimum": Decimal("15"),
        "maximum": Decimal("45"),
        "tactical": Decimal("0"),
        "cash": Decimal("10"),
        "strategy": "defensive_diversified_core",
    },
    RiskProfile.RISK_NEUTRAL: {
        "base_risk": Decimal("50"),
        "minimum": Decimal("25"),
        "maximum": Decimal("60"),
        "tactical": Decimal("5"),
        "cash": Decimal("7"),
        "strategy": "balanced_core_satellite",
    },
    RiskProfile.ACTIVE: {
        "base_risk": Decimal("65"),
        "minimum": Decimal("35"),
        "maximum": Decimal("75"),
        "tactical": Decimal("10"),
        "cash": Decimal("5"),
        "strategy": "growth_core_satellite",
    },
    RiskProfile.AGGRESSIVE: {
        "base_risk": Decimal("85"),
        "minimum": Decimal("45"),
        "maximum": Decimal("90"),
        "tactical": Decimal("15"),
        "cash": Decimal("3"),
        "strategy": "barbell_growth_tactical",
    },
}


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


STRESS_POLICY = {
    "equity_drawdown": {
        "core_equity": Decimal("-35"),
        "real_assets": Decimal("-25"),
        "tactical": Decimal("-45"),
        "fixed_income": Decimal("-8"),
        "cash": Decimal("0"),
    },
    "rate_inflation_shock": {
        "core_equity": Decimal("-15"),
        "real_assets": Decimal("-12"),
        "tactical": Decimal("-20"),
        "fixed_income": Decimal("-10"),
        "cash": Decimal("0"),
    },
    "stagflation": {
        "core_equity": Decimal("-20"),
        "real_assets": Decimal("-5"),
        "tactical": Decimal("-25"),
        "fixed_income": Decimal("-8"),
        "cash": Decimal("0"),
    },
}


def _stress_results(
    candidates: list[EducationalEtfCandidate],
) -> list[StressScenarioResult]:
    return [
        StressScenarioResult(
            scenario_code=code,
            estimated_loss_percent=_percent(
                -sum(
                    (
                        candidate.target_percent
                        * shocks.get(candidate.sleeve, Decimal("0"))
                        / Decimal("100")
                        for candidate in candidates
                    ),
                    Decimal("0"),
                )
            ),
            sleeve_shocks_percent=shocks,
            is_forecast=False,
        )
        for code, shocks in STRESS_POLICY.items()
    ]


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    if probability != Decimal("0.05"):
        raise ValueError("only the 5th percentile is supported")
    return statistics.quantiles(values, n=20, method="inclusive")[0]


def calculate_portfolio_risk(
    *,
    candidates: list[EducationalEtfCandidate],
    histories: dict[str, dict[date, Decimal]],
    source_as_of: date,
) -> PortfolioRiskEvaluation:
    stress = _stress_results(candidates)
    returns_by_code = {
        candidate.isu_code: _daily_returns(histories.get(candidate.isu_code, {}))
        for candidate in candidates
    }
    common_dates = (
        set.intersection(*(set(values) for values in returns_by_code.values()))
        if returns_by_code and all(returns_by_code.values())
        else set()
    )
    ordered_dates = sorted(common_dates)
    history_dates = [
        observed_on
        for history in histories.values()
        for observed_on in history
    ]
    sources = [
        SourceChip(
            label="한투 수정주가·KIND 분배금 반영 원화 총수익률",
            reference="data/cache/kis/adjusted_prices + data/cache/events",
            as_of=max(history_dates, default=source_as_of),
        ),
        SourceChip(
            label="연금 코파일럿 포트폴리오 스트레스 정책",
            reference="backend/app/engine/educational_portfolio.py",
            as_of=date(2026, 7, 16),
        ),
    ]
    if len(ordered_dates) < MINIMUM_RISK_OBSERVATIONS:
        return PortfolioRiskEvaluation(
            engine_name="historical_portfolio_risk",
            engine_version=ENGINE_VERSION,
            policy_version=POLICY_VERSION,
            usage_label="historical_risk_measurement_not_return_forecast",
            status="insufficient_common_history",
            observation_count=len(ordered_dates),
            observation_start=ordered_dates[0] if ordered_dates else None,
            observation_end=ordered_dates[-1] if ordered_dates else None,
            annualized_volatility_percent=None,
            annualized_downside_deviation_percent=None,
            maximum_drawdown_percent=None,
            historical_95pct_one_day_loss_percent=None,
            worst_daily_return_percent=None,
            historical_return_used_for_risk_only=True,
            is_return_forecast=False,
            stress_scenarios=stress,
            sources=sources,
            warnings=["minimum_60_common_daily_returns_required"],
        )
    total_weight = sum(
        (candidate.target_percent for candidate in candidates), Decimal("0")
    )
    portfolio_returns = [
        sum(
            (
                returns_by_code[candidate.isu_code][observed_on]
                * candidate.target_percent
                / total_weight
                for candidate in candidates
            ),
            Decimal("0"),
        )
        for observed_on in ordered_dates
    ]
    mean = sum(portfolio_returns, Decimal("0")) / Decimal(len(portfolio_returns))
    variance = sum(
        ((value - mean) ** 2 for value in portfolio_returns), Decimal("0")
    ) / Decimal(len(portfolio_returns) - 1)
    volatility = variance.sqrt() * TRADING_DAYS_PER_YEAR.sqrt()
    downside = (
        sum(
            (min(value, Decimal("0")) ** 2 for value in portfolio_returns),
            Decimal("0"),
        )
        / Decimal(len(portfolio_returns))
    ).sqrt() * TRADING_DAYS_PER_YEAR.sqrt()
    wealth = Decimal("1")
    peak = Decimal("1")
    maximum_drawdown = Decimal("0")
    for daily_return in portfolio_returns:
        wealth *= Decimal("1") + daily_return
        peak = max(peak, wealth)
        maximum_drawdown = min(maximum_drawdown, wealth / peak - Decimal("1"))
    fifth_percentile = _quantile(portfolio_returns, Decimal("0.05"))
    return PortfolioRiskEvaluation(
        engine_name="historical_portfolio_risk",
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        usage_label="historical_risk_measurement_not_return_forecast",
        status="complete",
        observation_count=len(ordered_dates),
        observation_start=ordered_dates[0],
        observation_end=ordered_dates[-1],
        annualized_volatility_percent=_percent(volatility * Decimal("100")),
        annualized_downside_deviation_percent=_percent(downside * Decimal("100")),
        maximum_drawdown_percent=_percent(-maximum_drawdown * Decimal("100")),
        historical_95pct_one_day_loss_percent=_percent(
            max(Decimal("0"), -fifth_percentile * Decimal("100"))
        ),
        worst_daily_return_percent=_percent(
            min(portfolio_returns) * Decimal("100")
        ),
        historical_return_used_for_risk_only=True,
        is_return_forecast=False,
        stress_scenarios=stress,
        sources=sources,
        warnings=[
            "fixed_weight_daily_rebalanced_historical_measurement",
            "historical_risk_does_not_predict_future_loss",
            "stress_shocks_are_policy_scenarios_not_probabilities",
        ],
    )


def _cma_mapping(classification: dict[str, Any]) -> tuple[str, bool, list[str]]:
    asset_class = str(classification.get("asset_class") or "")
    strategy = str(classification.get("strategy") or "")
    region = str(classification.get("region") or "")
    warnings: list[str] = []
    proxy = False
    emerging = {
        "china",
        "emerging_markets",
        "india",
        "latin_america",
        "mexico",
        "philippines",
        "vietnam",
    }
    if asset_class == "equity":
        if region == "united_states":
            code = "us_large_cap_equity"
        elif region in emerging:
            code = "emerging_markets_equity"
        else:
            code = "global_equity"
            proxy = region not in {"global", "developed_markets"}
    elif asset_class == "fixed_income":
        if strategy == "corporate_bond":
            code = "us_investment_grade_credit"
        elif strategy == "high_yield_bond":
            code = "us_high_yield"
        elif strategy == "short_term_bond":
            code = "cash"
            proxy = True
        else:
            code = "us_10y_treasury"
            proxy = region != "united_states"
    elif asset_class == "cash_equivalent":
        code = "cash"
    elif asset_class == "real_estate":
        code = "global_reit"
    elif asset_class == "commodity":
        code = "gold" if strategy == "gold" else "broad_commodities"
    elif asset_class == "multi_asset":
        code = "global_60_40"
        proxy = True
    elif asset_class == "alternative":
        code = "cash"
        proxy = True
    else:
        raise ValueError(f"no approved CMA mapping for asset class: {asset_class}")
    if proxy:
        warnings.append("asset_class_or_region_uses_cma_proxy")
    if classification.get("currency_hedge") == "unhedged" and region != "south_korea":
        warnings.append("usd_cma_has_zero_krw_currency_adjustment")
    return code, proxy, warnings


def _uncertainty_discount(classification: dict[str, Any]) -> Decimal:
    strategy = str(classification.get("strategy") or "")
    by_strategy = {
        "money_market": Decimal("0.10"),
        "government_bond": Decimal("0.15"),
        "short_term_bond": Decimal("0.20"),
        "aggregate_bond": Decimal("0.25"),
        "corporate_bond": Decimal("0.35"),
        "high_yield_bond": Decimal("0.50"),
        "broad_market": Decimal("0.25"),
        "dividend": Decimal("0.40"),
        "factor": Decimal("0.40"),
        "target_date": Decimal("0.30"),
        "reit": Decimal("0.50"),
        "gold": Decimal("0.50"),
        "covered_call": Decimal("0.75"),
        "sector_or_theme": Decimal("1.00"),
    }
    return by_strategy.get(strategy, Decimal("0.75"))


def calculate_portfolio_planning_return(
    *,
    candidates: list[EducationalEtfCandidate],
    products: dict[str, dict[str, Any]],
    retirement_start_age: int,
    portfolio_horizon_years: int,
    source_as_of: date,
) -> PortfolioPlanningEvaluation:
    cma_source = SourceChip(
        label="J.P. Morgan 2026 Long-Term Capital Market Assumptions",
        reference=(
            "https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/"
            "portfolio-insights/ltcma/noindex/ltcma-full-report.pdf"
        ),
        as_of=CMA_SOURCE_AS_OF,
    )
    policy_source = SourceChip(
        label="연금 코파일럿 CMA 매핑·불확실성 할인 정책",
        reference="backend/app/engine/educational_portfolio.py",
        as_of=date(2026, 7, 16),
    )
    cost_source = SourceChip(
        label="계좌별 ETF 비용 마스터",
        reference="data/cache/returns",
        as_of=source_as_of,
    )
    components: list[PortfolioPlanningComponent] = []
    warnings = [
        "planning_assumption_not_realized_return_prediction",
        "cma_is_current_policy_anchor_not_full_horizon_forecast",
        "currency_adjustment_is_zero_until_approved_krw_assumption",
    ]
    for candidate in candidates:
        product = products[candidate.isu_code]
        classification = product.get("classification") or {}
        code, proxy, component_warnings = _cma_mapping(classification)
        cost_data = product.get("cost") or {}
        cost = _numeric(cost_data.get("effective_total_cost_percent"))
        if cost is None:
            cost = _numeric(cost_data.get("kis_total_expense_ratio_percent"))
            component_warnings.append(
                "effective_total_cost_missing_uses_kis_stated_expense"
            )
        if cost is None:
            cost = Decimal("0")
            component_warnings.append("verified_cost_missing_zero_placeholder")
        uncertainty = _uncertainty_discount(classification)
        result = calculate_etf_planning_return(
            EtfPlanningReturnInput(
                etf_code=candidate.isu_code,
                as_of=source_as_of,
                horizon_years=max(1, min(portfolio_horizon_years, 40)),
                asset_class_cma_percent=CMA_ASSUMPTIONS_PERCENT[code],
                industry_excess_earnings_growth_percent=Decimal("0"),
                industry_growth_confidence=Decimal("0"),
                industry_growth_persistence=Decimal("0"),
                uncertainty_discount_percent=uncertainty,
                annual_cost_drag_percent=cost,
                sources=PlanningReturnSources(
                    asset_class_cma=cma_source,
                    industry_growth=policy_source,
                    uncertainty=policy_source,
                    annual_cost=cost_source,
                ),
            )
        )
        warnings.extend(component_warnings)
        components.append(
            PortfolioPlanningComponent(
                isu_code=candidate.isu_code,
                isu_name=candidate.isu_name,
                sleeve=candidate.sleeve,
                target_percent=candidate.target_percent,
                cma_assumption_code=code,
                cma_percent=_percent(CMA_ASSUMPTIONS_PERCENT[code]),
                uncertainty_discount_percent=_percent(uncertainty),
                annual_cost_drag_percent=_percent(cost),
                gross_planning_return_percent=result.gross_planning_return_percent,
                net_planning_return_percent=result.net_planning_return_percent,
                proxy_used=proxy,
                warnings=component_warnings,
            )
        )
    coverage = sum(
        (component.target_percent for component in components), Decimal("0")
    )
    gross = (
        sum(
            (
                item.target_percent * item.gross_planning_return_percent
                for item in components
            ),
            Decimal("0"),
        )
        / coverage
        if coverage
        else None
    )
    net = (
        sum(
            (
                item.target_percent * item.net_planning_return_percent
                for item in components
            ),
            Decimal("0"),
        )
        / coverage
        if coverage
        else None
    )
    weighted_uncertainty = (
        sum(
            (
                item.target_percent * item.uncertainty_discount_percent
                for item in components
            ),
            Decimal("0"),
        )
        / coverage
        if coverage
        else None
    )
    base = (
        net + weighted_uncertainty
        if net is not None and weighted_uncertainty is not None
        else None
    )
    if not (
        CMA_HORIZON_MIN_YEARS
        <= portfolio_horizon_years
        <= CMA_HORIZON_MAX_YEARS
    ):
        warnings.append("portfolio_horizon_outside_cma_source_horizon")
    return PortfolioPlanningEvaluation(
        engine_name="portfolio_long_term_planning_return",
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        cma_policy_id=CMA_POLICY_ID,
        cma_policy_status="approved_for_educational_planning_only",
        usage_label="annualized_long_term_planning_assumption_not_forecast",
        retirement_start_age=retirement_start_age,
        portfolio_horizon_years=portfolio_horizon_years,
        cma_source_horizon_min_years=CMA_HORIZON_MIN_YEARS,
        cma_source_horizon_max_years=CMA_HORIZON_MAX_YEARS,
        annual_review_required=True,
        coverage_weight_percent=_percent(coverage),
        gross_planning_return_percent=_percent(gross) if gross is not None else None,
        net_planning_return_percent=_percent(net) if net is not None else None,
        conservative_planning_return_percent=(
            _percent(net) if net is not None else None
        ),
        base_planning_return_percent=(
            _percent(base) if base is not None else None
        ),
        is_forecast=False,
        historical_performance_used=False,
        risk_adjustment_included=False,
        components=components,
        sources=[cma_source, policy_source, cost_source],
        warnings=list(dict.fromkeys(warnings)),
    )


def _allocation_for_risk(
    risk_percent: Decimal,
    *,
    age: int,
    policy: dict[str, Decimal | str],
) -> dict[str, Decimal]:
    tactical_limit = Decimal(policy["tactical"])
    tactical = min(tactical_limit, risk_percent * Decimal("0.25"))
    real_assets = min(Decimal("7"), risk_percent * Decimal("0.10"))
    core_equity = max(Decimal("0"), risk_percent - tactical - real_assets)
    defensive = Decimal("100") - risk_percent
    retirement_cash_addition = max(Decimal("0"), Decimal(age - 45) * Decimal("0.5"))
    cash = min(
        defensive,
        Decimal(policy["cash"]) + retirement_cash_addition,
    )
    fixed_income = defensive - cash
    return {
        "core_equity": core_equity,
        "real_assets": real_assets,
        "tactical": tactical,
        "fixed_income": fixed_income,
        "cash": cash,
    }


def _stress_loss(sleeves: dict[str, Decimal]) -> Decimal:
    return (
        sleeves["core_equity"] * Decimal("0.35")
        + sleeves["real_assets"] * Decimal("0.25")
        + sleeves["tactical"] * Decimal("0.45")
        + sleeves["fixed_income"] * Decimal("0.08")
    )


def _fit_loss_tolerance(
    risk_percent: Decimal,
    *,
    age: int,
    policy: dict[str, Decimal | str],
    loss_tolerance: Decimal,
) -> tuple[Decimal, dict[str, Decimal], bool]:
    initial = _allocation_for_risk(risk_percent, age=age, policy=policy)
    if _stress_loss(initial) <= loss_tolerance:
        return risk_percent, initial, False

    low = Decimal("0")
    high = risk_percent
    for _ in range(32):
        midpoint = (low + high) / Decimal("2")
        allocation = _allocation_for_risk(midpoint, age=age, policy=policy)
        if _stress_loss(allocation) <= loss_tolerance:
            low = midpoint
        else:
            high = midpoint
    fitted = _allocation_for_risk(low, age=age, policy=policy)
    stress = _stress_loss(fitted)
    if stress > loss_tolerance and fitted["fixed_income"] > 0:
        shift = min(
            fitted["fixed_income"],
            (stress - loss_tolerance) / Decimal("0.08"),
        )
        fitted["fixed_income"] -= shift
        fitted["cash"] += shift
    return low, fitted, True


def calculate_target_allocation(
    request: EducationalPortfolioInput,
) -> tuple[dict[str, Decimal], dict[str, Any]]:
    policy = PROFILE_POLICY[request.risk_profile]
    age_adjustment = (
        Decimal(35 - request.age) * Decimal("0.75")
        + Decimal(request.retirement_start_age - 55) * Decimal("0.75")
    )
    raw_risk = Decimal(policy["base_risk"]) + age_adjustment
    raw_risk = max(
        Decimal(policy["minimum"]),
        min(Decimal(policy["maximum"]), raw_risk),
    )
    account_cap = (
        RETIREMENT_RISK_CAP_PERCENT
        if request.account_type in {AccountType.DC, AccountType.IRP}
        else Decimal("90")
    )
    capped_risk = min(raw_risk, account_cap)
    fitted_risk, sleeves, loss_binding = _fit_loss_tolerance(
        capped_risk,
        age=request.age,
        policy=policy,
        loss_tolerance=request.loss_tolerance_percent,
    )
    return sleeves, {
        "strategy_label": policy["strategy"],
        "raw_risk": raw_risk,
        "final_risk": fitted_risk,
        "account_cap": (
            RETIREMENT_RISK_CAP_PERCENT
            if request.account_type in {AccountType.DC, AccountType.IRP}
            else None
        ),
        "account_cap_binding": capped_risk < raw_risk,
        "loss_tolerance_binding": loss_binding,
        "stress_loss": _stress_loss(sleeves),
    }


def _product_sleeve(product: dict[str, Any]) -> str | None:
    classification = product["classification"]
    asset_class = classification.get("asset_class")
    strategy = classification.get("strategy")
    if asset_class == "cash_equivalent":
        return "cash"
    if asset_class == "fixed_income":
        return "fixed_income"
    if asset_class in {"commodity", "real_estate"}:
        return "real_assets"
    if asset_class == "equity":
        if strategy in {"broad_market", "dividend", "factor"}:
            return "core_equity"
        if strategy in {"sector_or_theme", "covered_call"}:
            return "tactical"
    if asset_class == "alternative":
        return "tactical"
    return None


def _numeric(value: object) -> Decimal | None:
    if value in {None, "", "-"}:
        return None
    try:
        parsed = Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None
    return parsed if parsed.is_finite() else None


def _percentile(
    target: Decimal | None,
    values: list[Decimal],
    *,
    higher_is_better: bool,
) -> Decimal:
    if target is None or not values:
        return Decimal("0")
    favorable = sum(
        value <= target if higher_is_better else value >= target for value in values
    )
    return Decimal(favorable) / Decimal(len(values)) * Decimal("100")


def _quality_inputs(product: dict[str, Any]) -> dict[str, Decimal | None]:
    metrics = product["implementation_metrics"]
    tracking = _numeric(metrics.get("kis_current_tracking_error_percent"))
    if tracking is None:
        tracking = _numeric(metrics.get("tracking_error_proxy_percent"))
    return {
        "fee": _numeric(product["cost"].get("kis_total_expense_ratio_percent")),
        "liquidity": _numeric(metrics.get("median_daily_trading_value_krw")),
        "size": _numeric(metrics.get("median_net_assets_krw")),
        "nav": _numeric(metrics.get("median_abs_premium_discount_percent")),
        "tracking": tracking,
        "history": _numeric(product.get("observation_count")),
    }


def _score_candidates(
    products: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], CandidateQuality]]:
    inputs = {product["isu_code"]: _quality_inputs(product) for product in products}
    columns = {
        key: [value[key] for value in inputs.values() if value[key] is not None]
        for key in ("fee", "liquidity", "size", "nav", "tracking")
    }
    scored = []
    for product in products:
        values = inputs[product["isu_code"]]
        fee = _percentile(values["fee"], columns["fee"], higher_is_better=False)
        liquidity = _percentile(
            values["liquidity"], columns["liquidity"], higher_is_better=True
        )
        size = _percentile(values["size"], columns["size"], higher_is_better=True)
        nav = _percentile(values["nav"], columns["nav"], higher_is_better=False)
        tracking = _percentile(
            values["tracking"], columns["tracking"], higher_is_better=False
        )
        history = min(
            Decimal("100"),
            (values["history"] or Decimal("0")) / Decimal("756") * Decimal("100"),
        )
        total = (
            fee * Decimal("0.20")
            + liquidity * Decimal("0.25")
            + size * Decimal("0.20")
            + nav * Decimal("0.15")
            + tracking * Decimal("0.15")
            + history * Decimal("0.05")
        )
        scored.append(
            (
                product,
                CandidateQuality(
                    total_score=_percent(total),
                    fee_efficiency=_percent(fee),
                    liquidity=_percent(liquidity),
                    size=_percent(size),
                    nav_quality=_percent(nav),
                    tracking_quality=_percent(tracking),
                    history_depth=_percent(history),
                ),
            )
        )
    return sorted(
        scored,
        key=lambda item: (-item[1].total_score, item[0]["isu_code"]),
    )


def _daily_returns(history: dict[date, Decimal]) -> dict[date, Decimal]:
    ordered = sorted(history.items())
    return {
        current_date: current / previous - Decimal("1")
        for (_, previous), (current_date, current) in zip(
            ordered, ordered[1:], strict=False
        )
        if previous > 0 and current > 0
    }


def calculate_return_correlation(
    first: dict[date, Decimal], second: dict[date, Decimal]
) -> Decimal | None:
    return _calculate_return_correlation_from_returns(
        _daily_returns(first),
        _daily_returns(second),
    )


def _calculate_return_correlation_from_returns(
    first_returns: dict[date, Decimal],
    second_returns: dict[date, Decimal],
) -> Decimal | None:
    common = sorted(set(first_returns).intersection(second_returns))
    if len(common) < 60:
        return None
    first_values = [first_returns[day] for day in common]
    second_values = [second_returns[day] for day in common]
    first_mean = sum(first_values, Decimal("0")) / Decimal(len(common))
    second_mean = sum(second_values, Decimal("0")) / Decimal(len(common))
    covariance = sum(
        (
            (first_value - first_mean) * (second_value - second_mean)
            for first_value, second_value in zip(
                first_values, second_values, strict=True
            )
        ),
        Decimal("0"),
    )
    first_variance = sum(
        ((value - first_mean) ** 2 for value in first_values), Decimal("0")
    )
    second_variance = sum(
        ((value - second_mean) ** 2 for value in second_values), Decimal("0")
    )
    denominator = (first_variance * second_variance).sqrt()
    if denominator == 0:
        return None
    return covariance / denominator


def _candidate_counts(sleeves: dict[str, Decimal], max_etfs: int) -> dict[str, int]:
    active_sleeves = [
        sleeve for sleeve, weight in sleeves.items() if weight > Decimal("0.01")
    ]
    counts = {sleeve: 1 for sleeve in active_sleeves}
    remaining = max_etfs - len(active_sleeves)
    if remaining > 0 and "core_equity" in counts:
        counts["core_equity"] += 1
        remaining -= 1
    if remaining > 0 and "tactical" in counts and sleeves["tactical"] >= Decimal("10"):
        counts["tactical"] += 1
    return counts


def select_educational_candidates(
    *,
    products: list[dict[str, Any]],
    histories: dict[str, dict[date, Decimal]],
    sleeves: dict[str, Decimal],
    request: EducationalPortfolioInput,
    history_sources: dict[str, str] | None = None,
) -> list[EducationalEtfCandidate]:
    history_sources = history_sources or {}
    counts = _candidate_counts(sleeves, request.max_etfs)
    selected: list[tuple[dict[str, Any], CandidateQuality]] = []
    output: list[EducationalEtfCandidate] = []
    returns_by_code: dict[str, dict[date, Decimal]] = {}
    correlations_by_pair: dict[tuple[str, str], Decimal | None] = {}

    def returns_for(isu_code: str) -> dict[date, Decimal]:
        if isu_code not in returns_by_code:
            returns_by_code[isu_code] = _daily_returns(
                histories.get(isu_code, {})
            )
        return returns_by_code[isu_code]

    def correlation_for(first_code: str, second_code: str) -> Decimal | None:
        pair = tuple(sorted((first_code, second_code)))
        if pair not in correlations_by_pair:
            correlations_by_pair[pair] = (
                _calculate_return_correlation_from_returns(
                    returns_for(first_code),
                    returns_for(second_code),
                )
            )
        return correlations_by_pair[pair]

    for sleeve in sorted(counts, key=lambda item: (-sleeves[item], item)):
        pool = []
        for product in products:
            if _product_sleeve(product) != sleeve:
                continue
            classification = product["classification"]
            if classification.get("classification_confidence") == "low":
                continue
            eligibility = product["account_eligibility"]
            if (
                request.account_type in {AccountType.DC, AccountType.IRP}
                and sleeve in {"fixed_income", "cash"}
                and eligibility.get("allocation_bucket") != "full_allocation_eligible"
            ):
                continue
            pool.append(product)
        ranked = _score_candidates(pool)
        for _ in range(counts[sleeve]):
            remaining = [item for item in ranked if item not in selected]
            if not remaining:
                break
            evaluated = []
            for product, quality in remaining[:30]:
                correlations = [
                    correlation
                    for selected_product, _ in selected
                    if (
                        correlation := correlation_for(
                            product["isu_code"],
                            selected_product["isu_code"],
                        )
                    )
                    is not None
                ]
                maximum = max(correlations) if correlations else None
                penalty = (
                    max(Decimal("0"), maximum - Decimal("0.75")) * Decimal("60")
                    if maximum is not None
                    else Decimal("0")
                )
                same_region = any(
                    selected_product["classification"].get("region")
                    == product["classification"].get("region")
                    and _product_sleeve(selected_product) == sleeve
                    for selected_product, _ in selected
                )
                region_penalty = Decimal("5") if same_region else Decimal("0")
                evaluated.append(
                    (
                        quality.total_score - penalty - region_penalty,
                        product,
                        quality,
                        maximum,
                    )
                )
            _, product, quality, maximum = max(
                evaluated, key=lambda item: (item[0], item[1]["isu_code"])
            )
            selected.append((product, quality))
            reasons = [
                "quality_score_uses_cost_liquidity_size_nav_tracking_only",
                "historical_return_not_used_for_ranking",
            ]
            history_source = history_sources.get(
                product["isu_code"], "provided_price_history"
            )
            reasons.append(f"correlation_price_source_{history_source}")
            if maximum is not None:
                reasons.append("correlation_penalty_applied_above_0_75")
            output.append(
                EducationalEtfCandidate(
                    isu_code=product["isu_code"],
                    isu_name=product["isu_name"],
                    sleeve=sleeve,
                    target_percent=Decimal("0"),
                    quality=quality,
                    region=product["classification"].get("region"),
                    strategy=product["classification"].get("strategy"),
                    max_correlation_with_selected=(
                        _percent(maximum * Decimal("100"))
                        if maximum is not None
                        else None
                    ),
                    price_history_source=history_source,
                    account_eligibility=product["account_eligibility"],
                    reasons=reasons,
                )
            )
    per_sleeve = defaultdict(int)
    for candidate in output:
        per_sleeve[candidate.sleeve] += 1
    for candidate in output:
        candidate.target_percent = _percent(
            sleeves[candidate.sleeve] / per_sleeve[candidate.sleeve]
        )
    return output


def calculate_rebalancing_guidance(
    *,
    request: EducationalPortfolioInput,
    products: dict[str, dict[str, Any]],
    sleeves: dict[str, Decimal],
) -> RebalancingGuidance:
    if not request.current_holdings:
        return RebalancingGuidance(
            status="not_requested",
            drift_threshold_percent_points=DRIFT_THRESHOLD_PERCENT,
            current_total_krw=Decimal("0"),
            new_contribution_krw=request.new_contribution_krw,
            projected_total_krw=request.new_contribution_krw,
            unclassified_holding_amount_krw=Decimal("0"),
            contribution_first=True,
            sell_instruction_produced=False,
            sleeves=[],
            warnings=["current_holdings_not_provided"],
        )

    current_by_sleeve: dict[str, Decimal] = defaultdict(Decimal)
    unclassified = Decimal("0")
    for holding in request.current_holdings:
        product = products.get(holding.isu_code)
        sleeve = _product_sleeve(product) if product is not None else None
        if sleeve is None:
            unclassified += holding.amount_krw
        else:
            current_by_sleeve[sleeve] += holding.amount_krw
    current_total = sum(
        (holding.amount_krw for holding in request.current_holdings), Decimal("0")
    )
    projected_total = current_total + request.new_contribution_krw
    targets = {
        sleeve: projected_total * percent / Decimal("100")
        for sleeve, percent in sleeves.items()
    }
    deficits = {
        sleeve: max(Decimal("0"), target - current_by_sleeve.get(sleeve, Decimal("0")))
        for sleeve, target in targets.items()
    }
    total_deficit = sum(deficits.values(), Decimal("0"))
    contribution_by_sleeve = defaultdict(Decimal)
    if total_deficit > 0 and request.new_contribution_krw > 0:
        for sleeve, deficit in deficits.items():
            contribution_by_sleeve[sleeve] = min(
                deficit,
                request.new_contribution_krw * deficit / total_deficit,
            )
    allocated = sum(contribution_by_sleeve.values(), Decimal("0"))
    if allocated < request.new_contribution_krw:
        contribution_by_sleeve["cash"] += request.new_contribution_krw - allocated

    guidance = []
    for sleeve, target_percent in sleeves.items():
        current_amount = current_by_sleeve.get(sleeve, Decimal("0"))
        projected_amount = current_amount + contribution_by_sleeve[sleeve]
        current_percent = current_amount / current_total * Decimal("100")
        projected_percent = projected_amount / projected_total * Decimal("100")
        drift_before = current_percent - target_percent
        drift_after = projected_percent - target_percent
        if drift_after.copy_abs() <= DRIFT_THRESHOLD_PERCENT:
            status = "within_drift_band"
        elif drift_after < 0:
            status = "underweight_after_contribution"
        else:
            status = "overweight_review_only"
        guidance.append(
            RebalancingSleeveGuidance(
                sleeve=sleeve,
                target_percent=_percent(target_percent),
                current_percent=_percent(current_percent),
                projected_percent_after_contribution=_percent(projected_percent),
                drift_before_percent_points=_percent(drift_before),
                drift_after_percent_points=_percent(drift_after),
                contribution_example_krw=contribution_by_sleeve[sleeve].quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                ),
                status=status,
            )
        )
    warnings = ["educational_sleeve_guidance_not_trade_instruction"]
    if unclassified:
        warnings.append("unclassified_existing_holdings_require_review")
    return RebalancingGuidance(
        status=("partial_unclassified_holdings" if unclassified else "calculated"),
        drift_threshold_percent_points=DRIFT_THRESHOLD_PERCENT,
        current_total_krw=current_total,
        new_contribution_krw=request.new_contribution_krw,
        projected_total_krw=projected_total,
        unclassified_holding_amount_krw=unclassified,
        contribution_first=True,
        sell_instruction_produced=False,
        sleeves=guidance,
        warnings=warnings,
    )


def build_educational_portfolio(
    request: EducationalPortfolioInput,
    *,
    products: list[dict[str, Any]],
    histories: dict[str, dict[date, Decimal]],
    source_as_of: date,
    history_sources: dict[str, str] | None = None,
) -> EducationalPortfolioEvaluation:
    sleeves, policy = calculate_target_allocation(request)
    candidates = select_educational_candidates(
        products=products,
        histories=histories,
        sleeves=sleeves,
        request=request,
        history_sources=history_sources,
    )
    products_by_code = {product["isu_code"]: product for product in products}
    horizon_years = request.retirement_start_age - request.age
    portfolio_risk = calculate_portfolio_risk(
        candidates=candidates,
        histories=histories,
        source_as_of=source_as_of,
    )
    planning_return = calculate_portfolio_planning_return(
        candidates=candidates,
        products=products_by_code,
        retirement_start_age=request.retirement_start_age,
        portfolio_horizon_years=horizon_years,
        source_as_of=source_as_of,
    )
    target_sleeves = [
        SleeveTarget(
            sleeve=sleeve,
            target_percent=_percent(percent),
            risk_treatment=(
                "general_risky"
                if sleeve in {"core_equity", "real_assets", "tactical"}
                else "capital_preservation_candidate_required"
            ),
            role={
                "core_equity": "long_term_growth_core",
                "real_assets": "inflation_and_diversification",
                "tactical": "capped_tactical_satellite",
                "fixed_income": "drawdown_buffer",
                "cash": "liquidity_and_rebalancing_reserve",
            }[sleeve],
        )
        for sleeve, percent in sleeves.items()
        if percent > Decimal("0.01")
    ]
    return EducationalPortfolioEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        usage_label="educational_portfolio_example_not_trade_instruction",
        evaluated_input=request,
        strategy_label=str(policy["strategy_label"]),
        retirement_start_age=request.retirement_start_age,
        planning_horizon_years=horizon_years,
        horizon_to_age_55_years=55 - request.age,
        horizon_to_age_60_years=60 - request.age,
        raw_risk_target_percent=_percent(policy["raw_risk"]),
        final_general_risk_target_percent=_percent(policy["final_risk"]),
        account_risk_cap_percent=(
            _percent(policy["account_cap"])
            if policy["account_cap"] is not None
            else None
        ),
        account_cap_binding=bool(policy["account_cap_binding"]),
        loss_tolerance_binding=bool(policy["loss_tolerance_binding"]),
        stress_loss_proxy_percent=_percent(policy["stress_loss"]),
        target_sleeves=target_sleeves,
        candidates=candidates,
        portfolio_risk=portfolio_risk,
        planning_return=planning_return,
        rebalancing=calculate_rebalancing_guidance(
            request=request,
            products=products_by_code,
            sleeves=sleeves,
        ),
        sources=[
            SourceChip(
                label="한투 수정주가 + KIND 분배금 · 과거 원화 총수익률",
                reference="data/cache/returns",
                as_of=source_as_of,
            ),
            SourceChip(
                label="퇴직연금감독규정 위험자산 규칙 마스터",
                reference="data/cache/law_open",
                as_of=source_as_of,
            ),
            SourceChip(
                label="한국투자증권 ETF 수정주가",
                reference="data/cache/kis/adjusted_prices",
                as_of=source_as_of,
            ),
            SourceChip(
                label="KRX ETF 일별매매정보 대체값",
                reference="data/raw/krx/etf_bydd_trd",
                as_of=source_as_of,
            ),
        ],
        warnings=[
            "educational_example_not_personalized_investment_advice",
            "no_order_or_automatic_rebalancing",
            "historical_returns_excluded_from_candidate_ranking",
            "historical_returns_used_for_risk_not_planning_return",
            "correlation_uses_kis_adjusted_close_kind_cash_with_krx_fallback",
            "correlation_is_return_co_movement_not_holdings_overlap",
            "holdings_overlap_unavailable_until_pdf_data_is_complete",
            "planning_return_is_cma_based_assumption_not_forecast",
            "retirement_horizon_is_selected_between_age_55_and_60",
        ],
    )
