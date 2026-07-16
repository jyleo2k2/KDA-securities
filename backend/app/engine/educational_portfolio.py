from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import AccountType, SourceChip

ENGINE_NAME = "educational_pension_portfolio"
ENGINE_VERSION = "2026-07-16.1"
POLICY_VERSION = "2026-07-16"
PERCENT_QUANTUM = Decimal("0.0001")
DRIFT_THRESHOLD_PERCENT = Decimal("5")
RETIREMENT_RISK_CAP_PERCENT = Decimal("70")


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
        if self.current_holdings and sum(
            (item.amount_krw for item in self.current_holdings), Decimal("0")
        ) <= 0:
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
    current_total_krw: Decimal
    new_contribution_krw: Decimal
    projected_total_krw: Decimal
    unclassified_holding_amount_krw: Decimal
    contribution_first: bool
    sell_instruction_produced: bool
    sleeves: list[RebalancingSleeveGuidance]
    warnings: list[str]


class EducationalPortfolioEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    evaluated_input: EducationalPortfolioInput
    strategy_label: str
    horizon_to_age_55_years: int
    raw_risk_target_percent: Decimal
    final_general_risk_target_percent: Decimal
    account_risk_cap_percent: Decimal | None
    account_cap_binding: bool
    loss_tolerance_binding: bool
    stress_loss_proxy_percent: Decimal
    target_sleeves: list[SleeveTarget]
    candidates: list[EducationalEtfCandidate]
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
    retirement_cash_addition = max(
        Decimal("0"), Decimal(age - 45) * Decimal("0.5")
    )
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
    age_adjustment = Decimal(35 - request.age) * Decimal("0.75")
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
        value <= target if higher_is_better else value >= target
        for value in values
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
        key: [
            value[key]
            for value in inputs.values()
            if value[key] is not None
        ]
        for key in ("fee", "liquidity", "size", "nav", "tracking")
    }
    scored = []
    for product in products:
        values = inputs[product["isu_code"]]
        fee = _percentile(values["fee"], columns["fee"], higher_is_better=False)
        liquidity = _percentile(
            values["liquidity"], columns["liquidity"], higher_is_better=True
        )
        size = _percentile(
            values["size"], columns["size"], higher_is_better=True
        )
        nav = _percentile(values["nav"], columns["nav"], higher_is_better=False)
        tracking = _percentile(
            values["tracking"], columns["tracking"], higher_is_better=False
        )
        history = min(
            Decimal("100"),
            (values["history"] or Decimal("0")) / Decimal("756")
            * Decimal("100"),
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
    first_returns = _daily_returns(first)
    second_returns = _daily_returns(second)
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


def _candidate_counts(
    sleeves: dict[str, Decimal], max_etfs: int
) -> dict[str, int]:
    active_sleeves = [
        sleeve for sleeve, weight in sleeves.items() if weight > Decimal("0.01")
    ]
    counts = {sleeve: 1 for sleeve in active_sleeves}
    remaining = max_etfs - len(active_sleeves)
    if remaining > 0 and "core_equity" in counts:
        counts["core_equity"] += 1
        remaining -= 1
    if (
        remaining > 0
        and "tactical" in counts
        and sleeves["tactical"] >= Decimal("10")
    ):
        counts["tactical"] += 1
    return counts


def select_educational_candidates(
    *,
    products: list[dict[str, Any]],
    histories: dict[str, dict[date, Decimal]],
    sleeves: dict[str, Decimal],
    request: EducationalPortfolioInput,
) -> list[EducationalEtfCandidate]:
    counts = _candidate_counts(sleeves, request.max_etfs)
    selected: list[tuple[dict[str, Any], CandidateQuality]] = []
    output: list[EducationalEtfCandidate] = []
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
                and eligibility.get("allocation_bucket")
                != "full_allocation_eligible"
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
                        correlation := calculate_return_correlation(
                            histories.get(product["isu_code"], {}),
                            histories.get(selected_product["isu_code"], {}),
                        )
                    )
                    is not None
                ]
                maximum = max(correlations) if correlations else None
                penalty = (
                    max(Decimal("0"), maximum - Decimal("0.75"))
                    * Decimal("60")
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
        sleeve: max(
            Decimal("0"), target - current_by_sleeve.get(sleeve, Decimal("0"))
        )
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
        status=(
            "partial_unclassified_holdings" if unclassified else "calculated"
        ),
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
) -> EducationalPortfolioEvaluation:
    sleeves, policy = calculate_target_allocation(request)
    candidates = select_educational_candidates(
        products=products,
        histories=histories,
        sleeves=sleeves,
        request=request,
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
        horizon_to_age_55_years=55 - request.age,
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
        rebalancing=calculate_rebalancing_guidance(
            request=request,
            products={product["isu_code"]: product for product in products},
            sleeves=sleeves,
        ),
        sources=[
            SourceChip(
                label="계좌별 ETF 총수익률·비용 마스터",
                reference="data/cache/returns",
                as_of=source_as_of,
            ),
            SourceChip(
                label="퇴직연금감독규정 위험자산 규칙 마스터",
                reference="data/cache/law_open",
                as_of=source_as_of,
            ),
        ],
        warnings=[
            "educational_example_not_personalized_investment_advice",
            "no_order_or_automatic_rebalancing",
            "historical_returns_excluded_from_candidate_ranking",
            "correlation_is_price_return_proxy_not_holdings_overlap",
            "holdings_overlap_unavailable_until_pdf_data_is_complete",
            "planning_return_not_calculated_without_approved_cma_inputs",
        ],
    )
