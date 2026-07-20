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


class DemoHeroPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str
    representative_age: int
    customer_context: str
    scenario_code: str
    scenario_name: str
    age_band: str
    risk_profile: str
    investment_horizon_years: int
    total_amount_krw: Decimal
    accounts: list[ScenarioAccountInput]
    asset_allocations: list
    duplicated_asset_classes: list[str]
    risk_summary: DemoHeroRiskSummary
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
    repository = LocalScenarioRepository()
    heroes: list[DemoHeroPortfolio] = []
    for summary in repository.list():
        scenario = repository.get(summary.code)
        if scenario is None:
            continue
        user = users[scenario.scenario_code]
        benchmark_customer = get_benchmark_customer(user["benchmark_user_id"])
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
                scenario_code=scenario.scenario_code,
                scenario_name=scenario.name,
                age_band=scenario.age_band,
                risk_profile=scenario.risk_profile,
                investment_horizon_years=scenario.investment_horizon_years,
                total_amount_krw=evaluation.total_amount_krw,
                accounts=scenario.accounts,
                asset_allocations=evaluation.asset_allocations,
                duplicated_asset_classes=evaluation.duplicated_asset_classes,
                risk_summary=_risk_summary(scenario, evaluation),
                benchmark_customer=benchmark_customer,
            )
        )
    return tuple(heroes)
