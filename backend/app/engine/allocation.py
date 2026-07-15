"""Educational allocation example (아키텍처.md §2 module 6).

Returns an asset-class level example for the user's age band, risk profile and
account type. It never names products, never exceeds the user's own profile,
and keeps DC/IRP caps separate from pension-savings eligibility. The market
shock figure is an explicit stress value kept apart from return scenarios.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .assumptions import (
    ALLOCATION_MATRIX,
    ASSUMPTION_SOURCE,
    ASSUMPTION_VERSION,
    PENSION_SAVINGS_EXTENSION,
    age_band,
    display_net_return_percent,
    market_shock_percent,
)
from .models import (
    AccountType,
    AgeBand,
    AllocationWeights,
    AssumptionScenario,
    RiskProfile,
    SourceChip,
)
from .portfolio import RULE_SOURCE

ENGINE_NAME = "allocation_example"
ENGINE_VERSION = "2026-07-15.1"
EDUCATIONAL_NOTICE = (
    "특정 상품 추천이 아니라 자산군 단위의 교육용 예시다. "
    "실제 상품 선택과 주문은 이용자가 직접 결정한다."
)


class AllocationExampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_age: int = Field(ge=20, le=100)
    risk_profile: RiskProfile
    account_type: AccountType


class AllocationExampleEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    assumption_version: str
    account_type: AccountType
    risk_profile: RiskProfile
    age_band: AgeBand
    weights: AllocationWeights | None
    display_net_return_percent_by_scenario: dict[AssumptionScenario, Decimal]
    dc_irp_cap_applied: bool
    market_shock_percent: Decimal | None
    educational_notice: str
    evidence: list[SourceChip]


def build_allocation_example(
    inputs: AllocationExampleInput,
) -> AllocationExampleEvaluation:
    """Look up the approved example allocation without inventing new figures."""

    band = age_band(inputs.current_age)
    cap_applied = inputs.account_type in {AccountType.DC, AccountType.IRP}

    if band == AgeBand.AT_OR_ABOVE_55:
        # 만 55세 이상: 배분 예시·시나리오 없이 현재 상태만 다룬다.
        return AllocationExampleEvaluation(
            engine_name=ENGINE_NAME,
            engine_version=ENGINE_VERSION,
            assumption_version=ASSUMPTION_VERSION,
            account_type=inputs.account_type,
            risk_profile=inputs.risk_profile,
            age_band=band,
            weights=None,
            display_net_return_percent_by_scenario={},
            dc_irp_cap_applied=cap_applied,
            market_shock_percent=None,
            educational_notice=EDUCATIONAL_NOTICE,
            evidence=[ASSUMPTION_SOURCE, RULE_SOURCE],
        )

    weights = ALLOCATION_MATRIX[band][inputs.risk_profile]
    if inputs.account_type == AccountType.PENSION_SAVINGS:
        # 연금저축펀드는 총량 한도가 없어 승인된 확장 셀만 별도 적용한다.
        weights = PENSION_SAVINGS_EXTENSION.get(
            (band, inputs.risk_profile), weights
        )

    return AllocationExampleEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        assumption_version=ASSUMPTION_VERSION,
        account_type=inputs.account_type,
        risk_profile=inputs.risk_profile,
        age_band=band,
        weights=weights,
        display_net_return_percent_by_scenario={
            scenario: display_net_return_percent(weights, scenario)
            for scenario in AssumptionScenario
        },
        dc_irp_cap_applied=cap_applied,
        market_shock_percent=market_shock_percent(weights),
        educational_notice=EDUCATIONAL_NOTICE,
        evidence=[ASSUMPTION_SOURCE, RULE_SOURCE],
    )
