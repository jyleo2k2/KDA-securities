from decimal import ROUND_HALF_UP, Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.models import AgeBand, AssumptionScenario, RiskProfile
from backend.app.engine.simulation import (
    ASSUMPTION_NOTICE,
    SimulationInput,
    simulate_accumulation,
)

TEN_MILLION = Decimal("10000000")
MONTHLY = Decimal("300000")
HUNDRED_THOUSAND = Decimal("100000")
MILLION = Decimal("1000000")

# 수익률_가정_모델.md 기준 시나리오 골든표 (적립금 1,000만원·월 30만원·월말 납입).
GOLDEN_PRINCIPAL = {
    25: Decimal("118000000"),
    35: Decimal("82000000"),
    45: Decimal("46000000"),
    52: Decimal("20800000"),
}
GOLDEN_BASE_AT_55 = {
    (25, RiskProfile.STABLE): "193100000",
    (25, RiskProfile.STABLE_SEEKING): "222300000",
    (25, RiskProfile.RISK_NEUTRAL): "259900000",
    (25, RiskProfile.ACTIVE): "287000000",
    (25, RiskProfile.AGGRESSIVE): "310800000",
    (35, RiskProfile.STABLE): "113200000",
    (35, RiskProfile.STABLE_SEEKING): "122800000",
    (35, RiskProfile.RISK_NEUTRAL): "135800000",
    (35, RiskProfile.ACTIVE): "145000000",
    (35, RiskProfile.AGGRESSIVE): "154100000",
    (45, RiskProfile.STABLE): "54400000",
    (45, RiskProfile.STABLE_SEEKING): "56300000",
    (45, RiskProfile.RISK_NEUTRAL): "59200000",
    (45, RiskProfile.ACTIVE): "61200000",
    (45, RiskProfile.AGGRESSIVE): "63200000",
    (52, RiskProfile.STABLE): "22100000",
    (52, RiskProfile.STABLE_SEEKING): "22300000",
    (52, RiskProfile.RISK_NEUTRAL): "22700000",
    (52, RiskProfile.ACTIVE): "22900000",
    (52, RiskProfile.AGGRESSIVE): "23200000",
}
# 위험중립형 낮음/높음 (25·35세는 0.01억, 45·52세는 10만원 표시 단위).
GOLDEN_RISK_NEUTRAL_LOW_HIGH = {
    25: (MILLION, "160000000", "337000000"),
    35: (MILLION, "100000000", "159000000"),
    45: (HUNDRED_THOUSAND, "51000000", "63900000"),
    52: (HUNDRED_THOUSAND, "21600000", "23200000"),
}


def rounded(value: Decimal, unit: Decimal) -> Decimal:
    return (value / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit


def simulate(age: int, profile: RiskProfile):
    return simulate_accumulation(
        SimulationInput(
            current_age=age,
            risk_profile=profile,
            current_balance_krw=TEN_MILLION,
            monthly_contribution_krw=MONTHLY,
        )
    )


def projection(evaluation, scenario: AssumptionScenario):
    return next(p for p in evaluation.projections if p.scenario == scenario)


@pytest.mark.parametrize(("age", "profile"), sorted(GOLDEN_BASE_AT_55))
def test_base_scenario_matches_spec_golden_table(
    age: int, profile: RiskProfile
) -> None:
    evaluation = simulate(age, profile)
    assert evaluation.total_principal_krw == GOLDEN_PRINCIPAL[age]
    base = projection(evaluation, AssumptionScenario.BASE)
    expected = Decimal(GOLDEN_BASE_AT_55[(age, profile)])
    assert rounded(base.nominal_value_at_55_krw, HUNDRED_THOUSAND) == expected


@pytest.mark.parametrize("age", sorted(GOLDEN_RISK_NEUTRAL_LOW_HIGH))
def test_low_and_high_scenarios_match_spec(age: int) -> None:
    unit, low_expected, high_expected = GOLDEN_RISK_NEUTRAL_LOW_HIGH[age]
    evaluation = simulate(age, RiskProfile.RISK_NEUTRAL)
    low = projection(evaluation, AssumptionScenario.LOW)
    high = projection(evaluation, AssumptionScenario.HIGH)
    assert rounded(low.nominal_value_at_55_krw, unit) == Decimal(low_expected)
    assert rounded(high.nominal_value_at_55_krw, unit) == Decimal(high_expected)


def test_at_or_above_55_shows_balance_only() -> None:
    evaluation = simulate(55, RiskProfile.RISK_NEUTRAL)
    assert evaluation.projections == []
    assert evaluation.band_segments == []
    assert evaluation.months_to_55 == 0
    assert evaluation.total_principal_krw == TEN_MILLION


def test_age_54_uses_single_band_for_twelve_months() -> None:
    evaluation = simulate(54, RiskProfile.RISK_NEUTRAL)
    assert evaluation.months_to_55 == 12
    assert len(evaluation.band_segments) == 1
    segment = evaluation.band_segments[0]
    assert segment.age_band == AgeBand.AGE_50_54
    assert segment.months == 12


def test_band_transitions_recompute_allocation() -> None:
    evaluation = simulate(25, RiskProfile.RISK_NEUTRAL)
    assert [
        (segment.age_band, segment.months) for segment in evaluation.band_segments
    ] == [
        (AgeBand.AGE_20S, 60),
        (AgeBand.AGE_30S, 120),
        (AgeBand.AGE_40S, 120),
        (AgeBand.AGE_50_54, 60),
    ]


def test_zero_contribution_compounds_balance_only() -> None:
    evaluation = simulate_accumulation(
        SimulationInput(
            current_age=45,
            risk_profile=RiskProfile.RISK_NEUTRAL,
            current_balance_krw=TEN_MILLION,
            monthly_contribution_krw=Decimal("0"),
        )
    )
    assert evaluation.total_principal_krw == TEN_MILLION
    base = projection(evaluation, AssumptionScenario.BASE)
    assert base.nominal_value_at_55_krw > TEN_MILLION
    assert base.investment_gain_krw == (
        base.nominal_value_at_55_krw - TEN_MILLION
    )


def test_real_value_is_nominal_deflated_by_inflation() -> None:
    evaluation = simulate(25, RiskProfile.RISK_NEUTRAL)
    base = projection(evaluation, AssumptionScenario.BASE)
    deflator = (Decimal("1.02")) ** 30
    recomputed = base.nominal_value_at_55_krw / deflator
    assert abs(base.real_value_at_55_krw - recomputed) <= Decimal("0.01")


def test_assumption_language_is_locked() -> None:
    evaluation = simulate(35, RiskProfile.ACTIVE)
    assert evaluation.assumption_notice == ASSUMPTION_NOTICE
    assert evaluation.assumption_notice.startswith("미래 예측이 아니라")
    assert "교육용 가정 시나리오" in evaluation.assumption_notice
    assert evaluation.evidence[0].reference == "docs/30_스펙/수익률_가정_모델.md"


def test_simulation_is_deterministic() -> None:
    first = simulate(30, RiskProfile.AGGRESSIVE).model_dump(mode="json")
    second = simulate(30, RiskProfile.AGGRESSIVE).model_dump(mode="json")
    assert first == second


def test_age_below_modeled_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SimulationInput(
            current_age=19,
            risk_profile=RiskProfile.STABLE,
            current_balance_krw=TEN_MILLION,
            monthly_contribution_krw=MONTHLY,
        )
