"""Accumulation scenario simulation (아키텍처.md §2 module 5).

Every output is an educational assumption scenario from
docs/30_스펙/수익률_가정_모델.md, never a forecast. The net annual return is
applied at full precision; the spec's golden table only reproduces without
display rounding. The annual cost (0.5%p) is fixed by the assumption version
and is intentionally not a caller input, so unapproved assumptions cannot be
mixed in.
"""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import BaseModel, ConfigDict, Field

from .assumptions import (
    ALLOCATION_MATRIX,
    ASSUMPTION_SOURCE,
    ASSUMPTION_VERSION,
    age_band,
    net_annual_return_percent,
)
from .models import (
    AgeBand,
    AllocationWeights,
    AssumptionScenario,
    RiskProfile,
    SourceChip,
)
from .portfolio import MONEY_QUANTUM

ENGINE_NAME = "accumulation_simulation"
ENGINE_VERSION = "2026-07-15.1"
TARGET_AGE = 55
# TODO: 확인 필요 — 물가 가정 수치는 미확정(스펙에는 공식만 존재), 잠정 2.0%.
DEFAULT_INFLATION_PERCENT = Decimal("2.0")
ASSUMPTION_NOTICE = (
    "미래 예측이 아니라 사용자가 선택하는 교육용 가정 시나리오다. "
    "과거 관측수익률이나 전략의 실현성과와 혼합하지 않는다."
)
CALC_PRECISION = 50


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_age: int = Field(ge=20, le=100)
    risk_profile: RiskProfile
    current_balance_krw: Decimal = Field(
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    monthly_contribution_krw: Decimal = Field(
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    inflation_percent: Decimal = Field(
        default=DEFAULT_INFLATION_PERCENT,
        ge=0,
        le=100,
        allow_inf_nan=False,
    )


class BandSegment(BaseModel):
    age_band: AgeBand
    months: int
    weights: AllocationWeights
    net_annual_return_percent_by_scenario: dict[AssumptionScenario, Decimal]


class ScenarioProjection(BaseModel):
    scenario: AssumptionScenario
    nominal_value_at_55_krw: Decimal
    real_value_at_55_krw: Decimal
    investment_gain_krw: Decimal


class SimulationEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    assumption_version: str
    current_age: int
    target_age: int
    years_to_55: int
    months_to_55: int
    inflation_percent: Decimal
    total_principal_krw: Decimal
    projections: list[ScenarioProjection]
    band_segments: list[BandSegment]
    assumption_notice: str
    evidence: list[SourceChip]


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _band_segments(current_age: int, months: int) -> list[tuple[AgeBand, int]]:
    segments: list[tuple[AgeBand, int]] = []
    for month in range(months):
        band = age_band(current_age + month // 12)
        if segments and segments[-1][0] == band:
            segments[-1] = (band, segments[-1][1] + 1)
        else:
            segments.append((band, 1))
    return segments


def simulate_accumulation(inputs: SimulationInput) -> SimulationEvaluation:
    """Project the balance to age 55 under the approved assumption scenarios."""

    years = TARGET_AGE - inputs.current_age
    if years <= 0:
        # 만 55세 이상: 수익 예측 없이 현재 적립금만 표시한다.
        return SimulationEvaluation(
            engine_name=ENGINE_NAME,
            engine_version=ENGINE_VERSION,
            assumption_version=ASSUMPTION_VERSION,
            current_age=inputs.current_age,
            target_age=TARGET_AGE,
            years_to_55=0,
            months_to_55=0,
            inflation_percent=inputs.inflation_percent,
            total_principal_krw=_money(inputs.current_balance_krw),
            projections=[],
            band_segments=[],
            assumption_notice=ASSUMPTION_NOTICE,
            evidence=[ASSUMPTION_SOURCE],
        )

    months = years * 12
    raw_segments = _band_segments(inputs.current_age, months)
    band_segments = [
        BandSegment(
            age_band=band,
            months=segment_months,
            weights=ALLOCATION_MATRIX[band][inputs.risk_profile],
            net_annual_return_percent_by_scenario={
                scenario: net_annual_return_percent(
                    ALLOCATION_MATRIX[band][inputs.risk_profile], scenario
                )
                for scenario in AssumptionScenario
            },
        )
        for band, segment_months in raw_segments
    ]

    principal = (
        inputs.current_balance_krw
        + inputs.monthly_contribution_krw * Decimal(months)
    )
    projections: list[ScenarioProjection] = []
    with localcontext() as context:
        context.prec = CALC_PRECISION
        deflator = (
            Decimal(1) + inputs.inflation_percent / Decimal(100)
        ) ** Decimal(years)
        for scenario in AssumptionScenario:
            future_value = inputs.current_balance_krw
            for segment in band_segments:
                annual_percent = segment.net_annual_return_percent_by_scenario[
                    scenario
                ]
                growth = Decimal(1) + annual_percent / Decimal(100)
                monthly_rate = growth ** (Decimal(1) / Decimal(12)) - Decimal(1)
                for _ in range(segment.months):
                    # 월말 납입: 잔액을 먼저 굴리고 납입액을 더한다.
                    future_value = (
                        future_value * (Decimal(1) + monthly_rate)
                        + inputs.monthly_contribution_krw
                    )
            nominal = _money(future_value)
            projections.append(
                ScenarioProjection(
                    scenario=scenario,
                    nominal_value_at_55_krw=nominal,
                    real_value_at_55_krw=_money(future_value / deflator),
                    investment_gain_krw=_money(nominal - principal),
                )
            )

    return SimulationEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        assumption_version=ASSUMPTION_VERSION,
        current_age=inputs.current_age,
        target_age=TARGET_AGE,
        years_to_55=years,
        months_to_55=months,
        inflation_percent=inputs.inflation_percent,
        total_principal_krw=_money(principal),
        projections=projections,
        band_segments=band_segments,
        assumption_notice=ASSUMPTION_NOTICE,
        evidence=[ASSUMPTION_SOURCE],
    )
