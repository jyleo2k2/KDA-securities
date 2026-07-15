from decimal import Decimal

import pytest

from backend.app.engine.allocation import (
    AllocationExampleInput,
    build_allocation_example,
)
from backend.app.engine.assumptions import ALLOCATION_MATRIX
from backend.app.engine.models import (
    AccountType,
    AgeBand,
    AssumptionScenario,
    HoldingInput,
    PortfolioInput,
    RiskProfile,
    RiskTreatment,
    RuleStatus,
)
from backend.app.engine.portfolio import evaluate_risk_cap

BAND_REPRESENTATIVE_AGE = {
    AgeBand.AGE_20S: 25,
    AgeBand.AGE_30S: 35,
    AgeBand.AGE_40S: 45,
    AgeBand.AGE_50_54: 52,
}


def build(age: int, profile: RiskProfile, account_type: AccountType):
    return build_allocation_example(
        AllocationExampleInput(
            current_age=age,
            risk_profile=profile,
            account_type=account_type,
        )
    )


@pytest.mark.parametrize("account_type", [AccountType.DC, AccountType.IRP])
@pytest.mark.parametrize("band", sorted(BAND_REPRESENTATIVE_AGE))
@pytest.mark.parametrize("profile", sorted(RiskProfile))
def test_every_dc_irp_example_passes_risk_cap(
    account_type: AccountType, band: AgeBand, profile: RiskProfile
) -> None:
    evaluation = build(BAND_REPRESENTATIVE_AGE[band], profile, account_type)
    assert evaluation.weights is not None
    portfolio = PortfolioInput(
        account_type=account_type,
        holdings=[
            HoldingInput(
                holding_id="growth",
                amount_krw=evaluation.weights.growth_percent * Decimal("10000"),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
            HoldingInput(
                holding_id="defensive",
                amount_krw=(
                    evaluation.weights.safe_percent
                    + evaluation.weights.cash_percent
                )
                * Decimal("10000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
        ],
    )
    assert evaluate_risk_cap(portfolio).status == RuleStatus.PASS
    assert evaluation.dc_irp_cap_applied is True


def test_pension_savings_extension_applies_to_approved_cells_only() -> None:
    young = build(25, RiskProfile.AGGRESSIVE, AccountType.PENSION_SAVINGS)
    assert young.weights is not None
    assert young.weights.growth_percent == Decimal("90")
    thirties = build(35, RiskProfile.AGGRESSIVE, AccountType.PENSION_SAVINGS)
    assert thirties.weights is not None
    assert thirties.weights.growth_percent == Decimal("80")
    # 확장 셀이 아닌 조합과 DC 계좌는 기본 매트릭스를 그대로 쓴다.
    neutral = build(25, RiskProfile.RISK_NEUTRAL, AccountType.PENSION_SAVINGS)
    assert neutral.weights == ALLOCATION_MATRIX[AgeBand.AGE_20S][
        RiskProfile.RISK_NEUTRAL
    ]
    dc = build(25, RiskProfile.AGGRESSIVE, AccountType.DC)
    assert dc.weights is not None
    assert dc.weights.growth_percent == Decimal("70")


def test_market_shock_matches_spec_examples() -> None:
    young = build(25, RiskProfile.RISK_NEUTRAL, AccountType.DC)
    assert young.market_shock_percent == Decimal("-19.5")
    older = build(52, RiskProfile.RISK_NEUTRAL, AccountType.DC)
    assert older.market_shock_percent == Decimal("-9.5")


def test_display_returns_come_from_assumption_table() -> None:
    evaluation = build(25, RiskProfile.RISK_NEUTRAL, AccountType.DC)
    by_scenario = evaluation.display_net_return_percent_by_scenario
    assert by_scenario[AssumptionScenario.BASE] == Decimal("5.2")
    assert set(by_scenario) == set(AssumptionScenario)


def test_at_or_above_55_returns_no_example() -> None:
    evaluation = build(55, RiskProfile.RISK_NEUTRAL, AccountType.IRP)
    assert evaluation.age_band == AgeBand.AT_OR_ABOVE_55
    assert evaluation.weights is None
    assert evaluation.display_net_return_percent_by_scenario == {}
    assert evaluation.market_shock_percent is None


def test_educational_language_is_locked() -> None:
    evaluation = build(30, RiskProfile.ACTIVE, AccountType.IRP)
    assert "교육용 예시" in evaluation.educational_notice
    assert "추천이 아니라" in evaluation.educational_notice


def test_allocation_example_is_deterministic() -> None:
    first = build(40, RiskProfile.STABLE_SEEKING, AccountType.DC).model_dump(
        mode="json"
    )
    second = build(40, RiskProfile.STABLE_SEEKING, AccountType.DC).model_dump(
        mode="json"
    )
    assert first == second
