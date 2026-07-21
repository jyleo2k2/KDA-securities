"""Public presentation profiles for the six synthetic demo customers."""

import json
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..engine.models import ScenarioAccountInput
from ..engine.scenario import evaluate_mock_scenario
from .demo_customer_records import BenchmarkCustomerRecord, get_benchmark_customer
from .scenarios import LocalScenarioRepository

ROOT = Path(__file__).resolve().parents[3]
HERO_MANIFEST = ROOT / "data" / "mock" / "demo_scenario_users.json"
INVESTOR_PROFILE_MANIFEST = ROOT / "data" / "mock" / "demo_investor_profiles.json"
PUBLIC_PORTFOLIO_METRICS_MANIFEST = (
    ROOT / "data" / "mock" / "demo_public_portfolio_metrics.json"
)
PERCENT_QUANTUM = Decimal("0.01")

STRESS_SCENARIO_CODE = "equity_drawdown"
STRESS_SHOCK_PERCENT = {
    "cash": Decimal("0"),
    "deposit": Decimal("0"),
    "bond": Decimal("-8"),
    "domestic_equity": Decimal("-35"),
    "global_equity": Decimal("-35"),
    "alternative": Decimal("-25"),
    "eligible_tdf": Decimal("-35"),
    "default_option": Decimal("-20"),
}


class DemoHeroRiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dominant_asset_class: str
    dominant_asset_percent: Decimal
    general_risky_asset_percent: Decimal
    stress_scenario_code: str
    estimated_stress_loss_percent: Decimal
    is_forecast: bool = False
    requires_rebalancing_review: bool
    policy_label: str = "연금 코파일럿 자산군 스트레스 정책"


class DemoHeroPastPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: str
    label: str
    trailing_12m_return_pct: Decimal
    period_start: str
    period_end: str
    calculation_basis: str
    source_label: str
    data_kind: str
    is_forecast: bool = False
    official_ranking_metric: bool = False


class DemoHeroLikeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: str
    label: str
    count: int
    as_of_date: str
    data_kind: str
    is_synthetic: bool = True
    performance_based: bool = False


class DemoInvestorProfileAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_code: str
    selected_option: str
    score: int
    basis: str


class DemoInvestorProfileAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_code: str
    assessment_id: str
    rule_version: str
    source_documents: list[str]
    data_boundary: str
    notice: str
    investor_profile: str
    investor_profile_label: str
    total_score: int
    score_band: str
    scenario_name: str
    scenario_description: str
    answers: list[DemoInvestorProfileAnswer]
    non_scored_answers: dict[str, str | bool]
    investment_reason: str
    portfolio_opinion_review: str
    representative_etf_isu_codes: list[str]
    representative_etf_theme: str
    representative_etf_theme_review: str
    portfolio_consistency_note: str
    financial_product_shares_percent: dict[str, int]
    portfolio_allocations: dict[str, dict[str, int]]


class DemoHeroPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str
    representative_age: int
    customer_context: str
    is_demo_login_candidate: bool
    scenario_code: str
    scenario_name: str
    scenario_description: str
    age_band: str
    investor_profile: str
    investor_profile_label: str
    investor_profile_score: int
    investment_reason: str
    portfolio_opinion_review: str
    representative_etf_isu_codes: list[str]
    representative_etf_theme: str
    representative_etf_theme_review: str
    investor_profile_assessment: DemoInvestorProfileAssessment
    risk_profile: str
    investment_horizon_years: int
    total_amount_krw: Decimal
    accounts: list[ScenarioAccountInput]
    asset_allocations: list
    duplicated_asset_classes: list[str]
    risk_summary: DemoHeroRiskSummary
    past_performance: DemoHeroPastPerformance
    like_summary: DemoHeroLikeSummary
    benchmark_customer: BenchmarkCustomerRecord
    data_boundary: str = "mock"


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _risk_summary(scenario, evaluation) -> DemoHeroRiskSummary:
    dominant = max(
        evaluation.asset_allocations,
        key=lambda item: item.allocation_percent,
    )
    total = evaluation.total_amount_krw
    general_risky = sum(
        (
            holding.amount_krw
            for account in scenario.accounts
            for holding in account.holdings
            if holding.risk_treatment.value == "general_risky"
        ),
        Decimal("0"),
    )
    stress_loss = -sum(
        (
            allocation.allocation_percent
            * STRESS_SHOCK_PERCENT.get(allocation.asset_class_code, Decimal("0"))
            / Decimal("100")
            for allocation in evaluation.asset_allocations
        ),
        Decimal("0"),
    )
    return DemoHeroRiskSummary(
        dominant_asset_class=dominant.asset_class_code,
        dominant_asset_percent=dominant.allocation_percent,
        general_risky_asset_percent=_percent(general_risky / total * Decimal("100")),
        stress_scenario_code=STRESS_SCENARIO_CODE,
        estimated_stress_loss_percent=_percent(stress_loss),
        requires_rebalancing_review=(
            dominant.allocation_percent >= Decimal("50")
            or bool(evaluation.duplicated_asset_classes)
        ),
    )


@lru_cache(maxsize=1)
def build_demo_heroes() -> tuple[DemoHeroPortfolio, ...]:
    manifest = json.loads(HERO_MANIFEST.read_text(encoding="utf-8"))["users"]
    users = {item["scenario_code"]: item for item in manifest}
    profile_payload = json.loads(
        INVESTOR_PROFILE_MANIFEST.read_text(encoding="utf-8")
    )
    profile_common = {
        "rule_version": profile_payload["rule_version"],
        "source_documents": profile_payload["source_documents"],
        "data_boundary": profile_payload["data_boundary"],
        "notice": profile_payload["notice"],
    }
    profile_records = {
        item["scenario_code"]: item for item in profile_payload["profiles"]
    }
    metric_payload = json.loads(
        PUBLIC_PORTFOLIO_METRICS_MANIFEST.read_text(encoding="utf-8")
    )
    metric_records = {
        item["scenario_code"]: item for item in metric_payload["profiles"]
    }
    if set(profile_records) != set(users) or set(metric_records) != set(users):
        raise ValueError("demo profiles and metrics must match the hero manifest")
    repository = LocalScenarioRepository()
    heroes: list[DemoHeroPortfolio] = []
    for summary in repository.list():
        scenario = repository.get(summary.code)
        if scenario is None:
            continue
        user = users[scenario.scenario_code]
        profile_record = profile_records[scenario.scenario_code]
        assessment = DemoInvestorProfileAssessment.model_validate(
            {**profile_common, **profile_record}
        )
        benchmark_customer = get_benchmark_customer(user["benchmark_user_id"])
        metric_record = metric_records[scenario.scenario_code]
        if metric_record["benchmark_user_id"] != benchmark_customer.user_id:
            raise ValueError("demo public metric benchmark user differs")
        past_performance = DemoHeroPastPerformance.model_validate(
            {
                **metric_payload["return_metric"],
                "trailing_12m_return_pct": metric_record[
                    "portfolio_trailing_12m_return_pct"
                ],
                "period_start": metric_record["return_period_start"],
                "period_end": metric_record["return_period_end"],
            }
        )
        like_summary = DemoHeroLikeSummary.model_validate(
            {
                **metric_payload["like_metric"],
                "count": metric_record["like_count"],
            }
        )
        evaluation = evaluate_mock_scenario(scenario)
        benchmark_total = sum(
            (account.balance_krw for account in benchmark_customer.accounts),
            Decimal("0"),
        )
        if evaluation.total_amount_krw != benchmark_total:
            raise ValueError(
                "demo scenario total differs from benchmark customer: "
                f"{scenario.scenario_code}"
            )
        heroes.append(
            DemoHeroPortfolio(
                nickname=user["nickname"],
                representative_age=user["representative_age"],
                customer_context=user["customer_context"],
                is_demo_login_candidate=user["is_demo_login_candidate"],
                scenario_code=scenario.scenario_code,
                scenario_name=assessment.scenario_name,
                scenario_description=assessment.scenario_description,
                age_band=scenario.age_band,
                investor_profile=assessment.investor_profile,
                investor_profile_label=assessment.investor_profile_label,
                investor_profile_score=assessment.total_score,
                investment_reason=assessment.investment_reason,
                portfolio_opinion_review=assessment.portfolio_opinion_review,
                representative_etf_isu_codes=(
                    assessment.representative_etf_isu_codes
                ),
                representative_etf_theme=assessment.representative_etf_theme,
                representative_etf_theme_review=(
                    assessment.representative_etf_theme_review
                ),
                investor_profile_assessment=assessment,
                risk_profile=scenario.risk_profile,
                investment_horizon_years=scenario.investment_horizon_years,
                total_amount_krw=evaluation.total_amount_krw,
                accounts=scenario.accounts,
                asset_allocations=evaluation.asset_allocations,
                duplicated_asset_classes=evaluation.duplicated_asset_classes,
                risk_summary=_risk_summary(scenario, evaluation),
                past_performance=past_performance,
                like_summary=like_summary,
                benchmark_customer=benchmark_customer,
            )
        )
    return tuple(heroes)
