from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.assumptions import (
    ALLOCATION_MATRIX,
    PENSION_SAVINGS_EXTENSION,
    age_band,
    display_net_return_percent,
    market_shock_percent,
    net_annual_return_percent,
)
from backend.app.engine.models import (
    AgeBand,
    AllocationWeights,
    AssumptionScenario,
    RiskProfile,
)

# 수익률_가정_모델.md 연령·성향별 모델표의 표시용 순수익률(기준 시나리오, 0.1%p).
DISPLAY_BASE_RETURN_GOLDEN = {
    (AgeBand.AGE_20S, RiskProfile.STABLE): "3.4",
    (AgeBand.AGE_20S, RiskProfile.STABLE_SEEKING): "4.3",
    (AgeBand.AGE_20S, RiskProfile.RISK_NEUTRAL): "5.2",
    (AgeBand.AGE_20S, RiskProfile.ACTIVE): "5.5",
    (AgeBand.AGE_20S, RiskProfile.AGGRESSIVE): "5.6",
    (AgeBand.AGE_30S, RiskProfile.STABLE): "3.1",
    (AgeBand.AGE_30S, RiskProfile.STABLE_SEEKING): "4.0",
    (AgeBand.AGE_30S, RiskProfile.RISK_NEUTRAL): "4.9",
    (AgeBand.AGE_30S, RiskProfile.ACTIVE): "5.4",
    (AgeBand.AGE_30S, RiskProfile.AGGRESSIVE): "5.6",
    (AgeBand.AGE_40S, RiskProfile.STABLE): "2.8",
    (AgeBand.AGE_40S, RiskProfile.STABLE_SEEKING): "3.6",
    (AgeBand.AGE_40S, RiskProfile.RISK_NEUTRAL): "4.4",
    (AgeBand.AGE_40S, RiskProfile.ACTIVE): "4.9",
    (AgeBand.AGE_40S, RiskProfile.AGGRESSIVE): "5.5",
    (AgeBand.AGE_50_54, RiskProfile.STABLE): "2.8",
    (AgeBand.AGE_50_54, RiskProfile.STABLE_SEEKING): "3.1",
    (AgeBand.AGE_50_54, RiskProfile.RISK_NEUTRAL): "4.0",
    (AgeBand.AGE_50_54, RiskProfile.ACTIVE): "4.5",
    (AgeBand.AGE_50_54, RiskProfile.AGGRESSIVE): "5.0",
}


def test_matrix_display_returns_match_spec_table() -> None:
    for (band, profile), expected in DISPLAY_BASE_RETURN_GOLDEN.items():
        weights = ALLOCATION_MATRIX[band][profile]
        actual = display_net_return_percent(weights, AssumptionScenario.BASE)
        assert actual == Decimal(expected), (band, profile)


def test_matrix_covers_modeled_bands_and_all_profiles() -> None:
    assert set(ALLOCATION_MATRIX) == {
        AgeBand.AGE_20S,
        AgeBand.AGE_30S,
        AgeBand.AGE_40S,
        AgeBand.AGE_50_54,
    }
    for cells in ALLOCATION_MATRIX.values():
        assert set(cells) == set(RiskProfile)
        for weights in cells.values():
            total = (
                weights.growth_percent + weights.safe_percent + weights.cash_percent
            )
            assert total == Decimal("100")


def test_dc_irp_matrix_growth_never_exceeds_70_percent() -> None:
    for cells in ALLOCATION_MATRIX.values():
        for weights in cells.values():
            assert weights.growth_percent <= Decimal("70")


def test_pension_savings_extension_cells() -> None:
    young = PENSION_SAVINGS_EXTENSION[(AgeBand.AGE_20S, RiskProfile.AGGRESSIVE)]
    assert (young.growth_percent, young.safe_percent, young.cash_percent) == (
        Decimal("90"),
        Decimal("10"),
        Decimal("0"),
    )
    thirties = PENSION_SAVINGS_EXTENSION[(AgeBand.AGE_30S, RiskProfile.AGGRESSIVE)]
    assert (thirties.growth_percent, thirties.safe_percent, thirties.cash_percent) == (
        Decimal("80"),
        Decimal("20"),
        Decimal("0"),
    )


def test_age_band_boundaries() -> None:
    assert age_band(20) == AgeBand.AGE_20S
    assert age_band(29) == AgeBand.AGE_20S
    assert age_band(30) == AgeBand.AGE_30S
    assert age_band(39) == AgeBand.AGE_30S
    assert age_band(40) == AgeBand.AGE_40S
    assert age_band(49) == AgeBand.AGE_40S
    assert age_band(50) == AgeBand.AGE_50_54
    assert age_band(54) == AgeBand.AGE_50_54
    assert age_band(55) == AgeBand.AT_OR_ABOVE_55
    assert age_band(70) == AgeBand.AT_OR_ABOVE_55
    with pytest.raises(ValueError):
        age_band(19)


def test_market_shock_matches_spec_examples() -> None:
    neutral_20s = ALLOCATION_MATRIX[AgeBand.AGE_20S][RiskProfile.RISK_NEUTRAL]
    assert market_shock_percent(neutral_20s) == Decimal("-19.5")
    neutral_50s = ALLOCATION_MATRIX[AgeBand.AGE_50_54][RiskProfile.RISK_NEUTRAL]
    assert market_shock_percent(neutral_50s) == Decimal("-9.5")


def test_net_return_is_full_precision_and_display_rounds() -> None:
    weights = ALLOCATION_MATRIX[AgeBand.AGE_20S][RiskProfile.RISK_NEUTRAL]
    assert net_annual_return_percent(weights, AssumptionScenario.BASE) == Decimal(
        "5.15"
    )
    assert display_net_return_percent(weights, AssumptionScenario.BASE) == Decimal(
        "5.2"
    )


def test_allocation_weights_reject_partial_allocation() -> None:
    with pytest.raises(ValidationError):
        AllocationWeights(
            growth_percent=Decimal("50"),
            safe_percent=Decimal("30"),
            cash_percent=Decimal("10"),
        )
