"""Approved long-term return assumptions (scenario data, not forecasts).

Single source: docs/30_스펙/수익률_가정_모델.md. Every figure here is an
educational assumption scenario chosen by the user; it must never be mixed
with observed historical returns or presented as a prediction
(docs/30_스펙/데이터_품질_계약.md §1 ``scenario`` data kind).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .models import (
    AgeBand,
    AllocationWeights,
    AssetBucket,
    AssumptionScenario,
    RiskProfile,
    SourceChip,
)

ASSUMPTION_VERSION = "2026-07-20.2"
ASSUMPTION_SOURCE = SourceChip(
    label="수익률 가정 모델",
    reference="docs/30_스펙/수익률_가정_모델.md",
    as_of=date(2026, 7, 20),
)
INFLATION_ASSUMPTION_SOURCE = SourceChip(
    label="한국은행 물가안정목표 기반 기본 물가가정 2.0%",
    reference="https://www.bok.or.kr/portal/main/contents.do?menuNo=200291",
    as_of=date(2026, 7, 20),
)
ANNUAL_COST_PERCENT = Decimal("0.5")
DISPLAY_PERCENT_QUANTUM = Decimal("0.1")

# Anchored to J.P. Morgan 2026 long-term assumptions (global equity 7.0%,
# US intermediate treasuries 4.0%); low/high bound the base scenario.
BUCKET_RETURN_PERCENT: dict[AssumptionScenario, dict[AssetBucket, Decimal]] = {
    AssumptionScenario.LOW: {
        AssetBucket.GROWTH: Decimal("3.0"),
        AssetBucket.SAFE: Decimal("2.0"),
        AssetBucket.CASH: Decimal("1.5"),
    },
    AssumptionScenario.BASE: {
        AssetBucket.GROWTH: Decimal("7.0"),
        AssetBucket.SAFE: Decimal("4.0"),
        AssetBucket.CASH: Decimal("2.5"),
    },
    AssumptionScenario.HIGH: {
        AssetBucket.GROWTH: Decimal("9.0"),
        AssetBucket.SAFE: Decimal("5.0"),
        AssetBucket.CASH: Decimal("3.0"),
    },
}


def _weights(growth: str, safe: str, cash: str) -> AllocationWeights:
    return AllocationWeights(
        growth_percent=Decimal(growth),
        safe_percent=Decimal(safe),
        cash_percent=Decimal(cash),
    )


# 성장/안전/현금. The approved pension-calculator contract extends the
# AGE_50_54 allocation unchanged for ages 55 and above (2026-07-20 decision).
ALLOCATION_MATRIX: dict[AgeBand, dict[RiskProfile, AllocationWeights]] = {
    AgeBand.AGE_20S: {
        RiskProfile.STABLE: _weights("20", "30", "50"),
        RiskProfile.STABLE_SEEKING: _weights("40", "35", "25"),
        RiskProfile.RISK_NEUTRAL: _weights("60", "30", "10"),
        RiskProfile.ACTIVE: _weights("70", "25", "5"),
        RiskProfile.AGGRESSIVE: _weights("70", "30", "0"),
    },
    AgeBand.AGE_30S: {
        RiskProfile.STABLE: _weights("10", "40", "50"),
        RiskProfile.STABLE_SEEKING: _weights("30", "45", "25"),
        RiskProfile.RISK_NEUTRAL: _weights("50", "40", "10"),
        RiskProfile.ACTIVE: _weights("65", "30", "5"),
        RiskProfile.AGGRESSIVE: _weights("70", "30", "0"),
    },
    AgeBand.AGE_40S: {
        RiskProfile.STABLE: _weights("0", "50", "50"),
        RiskProfile.STABLE_SEEKING: _weights("15", "60", "25"),
        RiskProfile.RISK_NEUTRAL: _weights("35", "55", "10"),
        RiskProfile.ACTIVE: _weights("50", "45", "5"),
        RiskProfile.AGGRESSIVE: _weights("65", "35", "0"),
    },
    AgeBand.AGE_50_54: {
        RiskProfile.STABLE: _weights("0", "50", "50"),
        RiskProfile.STABLE_SEEKING: _weights("0", "75", "25"),
        RiskProfile.RISK_NEUTRAL: _weights("20", "70", "10"),
        RiskProfile.ACTIVE: _weights("35", "60", "5"),
        RiskProfile.AGGRESSIVE: _weights("50", "50", "0"),
    },
    AgeBand.AT_OR_ABOVE_55: {
        RiskProfile.STABLE: _weights("0", "50", "50"),
        RiskProfile.STABLE_SEEKING: _weights("0", "75", "25"),
        RiskProfile.RISK_NEUTRAL: _weights("20", "70", "10"),
        RiskProfile.ACTIVE: _weights("35", "60", "5"),
        RiskProfile.AGGRESSIVE: _weights("50", "50", "0"),
    },
}

# 연금저축펀드 has no 70% aggregate cap, so the educational example may extend
# beyond the DC/IRP matrix for these cells only.
PENSION_SAVINGS_EXTENSION: dict[tuple[AgeBand, RiskProfile], AllocationWeights] = {
    (AgeBand.AGE_20S, RiskProfile.AGGRESSIVE): _weights("90", "10", "0"),
    (AgeBand.AGE_30S, RiskProfile.AGGRESSIVE): _weights("80", "20", "0"),
}

# Explicit downside shock, kept separate from return scenarios by design.
MARKET_SHOCK_PERCENT: dict[AssetBucket, Decimal] = {
    AssetBucket.GROWTH: Decimal("-30"),
    AssetBucket.SAFE: Decimal("-5"),
    AssetBucket.CASH: Decimal("0"),
}

MINIMUM_MODELED_AGE = 20


def age_band(age: int) -> AgeBand:
    if age < MINIMUM_MODELED_AGE:
        raise ValueError("assumption model defines age bands from age 20 only")
    if age >= 55:
        return AgeBand.AT_OR_ABOVE_55
    if age >= 50:
        return AgeBand.AGE_50_54
    if age >= 40:
        return AgeBand.AGE_40S
    if age >= 30:
        return AgeBand.AGE_30S
    return AgeBand.AGE_20S


def net_annual_return_percent(
    weights: AllocationWeights, scenario: AssumptionScenario
) -> Decimal:
    """Full-precision net annual return in percent (no display rounding).

    The golden accumulation table only reproduces with the unrounded value;
    rounding to 0.1%p is display-only (`display_net_return_percent`).
    """

    bucket_returns = BUCKET_RETURN_PERCENT[scenario]
    gross = (
        weights.growth_percent * bucket_returns[AssetBucket.GROWTH]
        + weights.safe_percent * bucket_returns[AssetBucket.SAFE]
        + weights.cash_percent * bucket_returns[AssetBucket.CASH]
    ) / Decimal("100")
    return gross - ANNUAL_COST_PERCENT


def display_net_return_percent(
    weights: AllocationWeights, scenario: AssumptionScenario
) -> Decimal:
    return net_annual_return_percent(weights, scenario).quantize(
        DISPLAY_PERCENT_QUANTUM, rounding=ROUND_HALF_UP
    )


def market_shock_percent(weights: AllocationWeights) -> Decimal:
    return (
        weights.growth_percent * MARKET_SHOCK_PERCENT[AssetBucket.GROWTH]
        + weights.safe_percent * MARKET_SHOCK_PERCENT[AssetBucket.SAFE]
        + weights.cash_percent * MARKET_SHOCK_PERCENT[AssetBucket.CASH]
    ) / Decimal("100")
