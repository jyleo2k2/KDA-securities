import hashlib
import json
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.engine import (
    AccountType,
    PensionCalculatorInput,
    RiskProfile,
    SimulationInput,
    calculate_pension,
    simulate_accumulation,
)
from backend.app.engine.assumptions import (
    ALLOCATION_MATRIX,
    age_band,
    net_annual_return_percent,
)
from backend.app.engine.educational_portfolio import (
    EducationalPortfolioInput,
    calculate_target_allocation,
)
from backend.app.engine.educational_portfolio import (
    RiskProfile as EducationalRiskProfile,
)
from backend.app.engine.pension_calculator import _allocation, _tax_rates
from backend.app.main import app

client = TestClient(app)


def _input(**updates) -> PensionCalculatorInput:
    values = {
        "current_age": 25,
        "contribution_end_age": 65,
        "monthly_contribution_krw": Decimal("300000"),
        "current_balance_krw": Decimal("10000000"),
        "account_type": AccountType.IRP,
        "risk_profile": RiskProfile.RISK_NEUTRAL,
        "payout_years": 20,
    }
    values.update(updates)
    return PensionCalculatorInput(**values)


def test_yearly_principal_gain_balance_identity() -> None:
    result = calculate_pension(_input())

    assert all(
        year.cumulative_principal_krw + year.cumulative_gain_krw
        == year.balance_krw
        for year in result.yearly
    )


def test_last_year_matches_headline_total() -> None:
    result = calculate_pension(_input())

    assert result.yearly[-1].balance_krw == result.headline.total_krw


def test_total_principal_is_balance_plus_all_contributions() -> None:
    inputs = _input()
    result = calculate_pension(inputs)

    assert result.headline.total_principal_krw == Decimal("154000000")


def test_age_band_boundaries_recalculate_and_55_extension_stays_equal() -> None:
    profile = RiskProfile.RISK_NEUTRAL
    changed_boundaries = ((29, 30), (39, 40), (49, 50))
    for before_age, after_age in changed_boundaries:
        before_weights = _allocation(
            account_type=AccountType.IRP,
            age=before_age,
            profile=profile,
        )
        after_weights = _allocation(
            account_type=AccountType.IRP,
            age=after_age,
            profile=profile,
        )
        assert age_band(before_age) != age_band(after_age)
        assert before_weights != after_weights
        assert net_annual_return_percent(
            before_weights, _input().scenario
        ) != net_annual_return_percent(after_weights, _input().scenario)

    before_55 = _allocation(
        account_type=AccountType.IRP,
        age=54,
        profile=profile,
    )
    at_55 = _allocation(
        account_type=AccountType.IRP,
        age=55,
        profile=profile,
    )
    assert age_band(54) != age_band(55)
    assert before_55 == at_55
    assert ALLOCATION_MATRIX[age_band(54)][profile] == ALLOCATION_MATRIX[
        age_band(55)
    ][profile]


def test_tax_rates_change_at_70_and_80() -> None:
    result = calculate_pension(
        _input(
            current_age=55,
            contribution_end_age=69,
            monthly_contribution_krw=Decimal("0"),
            current_balance_krw=Decimal("1000000"),
            payout_years=12,
        )
    )

    assert result.tax.withholding_rate_percent_by_year == [
        Decimal("5.5"),
        *([Decimal("4.4")] * 10),
        Decimal("3.3"),
    ]


def test_annual_15m_threshold_is_strictly_greater_than() -> None:
    exact_rates, exact_exceeds = _tax_rates(
        annual_payout=Decimal("15000000"),
        pension_start_age=65,
        payout_years=5,
    )
    over_rates, over_exceeds = _tax_rates(
        annual_payout=Decimal("15000001"),
        pension_start_age=65,
        payout_years=5,
    )

    assert exact_exceeds is False
    assert exact_rates == [Decimal("5.5")] * 5
    assert over_exceeds is True
    assert over_rates == [Decimal("16.5")] * 5


def test_payout_years_five_records_withdrawal_limit_excess() -> None:
    result = calculate_pension(_input(payout_years=5))

    warning = next(
        item
        for item in result.warnings
        if item.startswith("pension_withdrawal_limit_exceeded_years:")
    )
    assert warning == "pension_withdrawal_limit_exceeded_years:1,2,3,4,5"


def test_all_dc_irp_strategies_respect_growth_cap() -> None:
    for account_type in (AccountType.DC, AccountType.IRP):
        result = calculate_pension(_input(account_type=account_type))
        assert all(
            strategy.growth_percent <= Decimal("70")
            for strategy in result.strategies
        )


def test_default_strategy_counts_match_profile_rules() -> None:
    stable = calculate_pension(_input(risk_profile=RiskProfile.STABLE))
    aggressive = calculate_pension(_input(risk_profile=RiskProfile.AGGRESSIVE))

    assert sum(strategy.default_visible for strategy in stable.strategies) == 1
    assert sum(strategy.default_visible for strategy in aggressive.strategies) == 3


def test_strategies_include_display_metadata() -> None:
    strategies = calculate_pension(_input()).strategies

    assert {strategy.presentation.strategy_id for strategy in strategies} == {
        strategy.strategy_id for strategy in strategies
    }
    aggressive = next(
        strategy
        for strategy in strategies
        if strategy.strategy_id == "barbell_growth_tactical"
    )
    assert aggressive.presentation.display_name == "테마 집중 전략"
    assert aggressive.presentation.risk_badge == "공격투자형"


def test_out_of_profile_strategy_is_never_default_visible() -> None:
    for profile in RiskProfile:
        result = calculate_pension(_input(risk_profile=profile))
        assert not any(
            strategy.default_visible and not strategy.within_profile
            for strategy in result.strategies
        )


def test_same_input_produces_same_output() -> None:
    inputs = _input(account_type=AccountType.PENSION_SAVINGS)

    assert calculate_pension(inputs).model_dump(mode="json") == calculate_pension(
        inputs
    ).model_dump(mode="json")


def test_existing_simulation_still_returns_current_balance_at_55() -> None:
    result = simulate_accumulation(
        SimulationInput(
            current_age=55,
            risk_profile=RiskProfile.RISK_NEUTRAL,
            current_balance_krw=Decimal("10000000"),
            monthly_contribution_krw=Decimal("300000"),
        )
    )

    assert result.years_to_55 == 0
    assert result.total_principal_krw == Decimal("10000000.00")
    assert result.projections == []
    assert result.band_segments == []


def test_educational_portfolio_120_case_allocation_regression() -> None:
    ages = (25, 35, 45, 52)
    retirement_ages = (55, 60)
    losses = {
        EducationalRiskProfile.STABLE: Decimal("8"),
        EducationalRiskProfile.STABLE_SEEKING: Decimal("12"),
        EducationalRiskProfile.RISK_NEUTRAL: Decimal("20"),
        EducationalRiskProfile.ACTIVE: Decimal("28"),
        EducationalRiskProfile.AGGRESSIVE: Decimal("40"),
    }
    rows = []
    for account_type in AccountType:
        for age in ages:
            for retirement_age in retirement_ages:
                for profile in EducationalRiskProfile:
                    request = EducationalPortfolioInput(
                        account_type=account_type,
                        age=age,
                        retirement_start_age=retirement_age,
                        risk_profile=profile,
                        loss_tolerance_percent=losses[profile],
                    )
                    _, allocation = calculate_target_allocation(request)
                    rows.append(
                        {
                            "input": request.model_dump(mode="json"),
                            "allocation": {
                                key: str(value)
                                if isinstance(value, Decimal)
                                else value
                                for key, value in allocation.items()
                            },
                        }
                    )

    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    assert len(rows) == 120
    assert hashlib.sha256(payload.encode()).hexdigest() == (
        "cad181f6ba0a1c5e667b1d3041b16ef44481f55ef54b5cc1d2bec2daa4d621d4"
    )


def test_api_contract_and_validation() -> None:
    payload = _input().model_dump(mode="json")
    response = client.post("/engine/pension-calculator", json=payload)

    assert response.status_code == 200
    assert isinstance(response.json()["headline"]["total_krw"], str)

    for invalid in (
        {**payload, "payout_years": 4},
        {**payload, "strategy_id": "unknown"},
        {**payload, "contribution_end_age": 25},
        {
            **payload,
            "monthly_contribution_krw": "0",
            "current_balance_krw": "0",
        },
    ):
        assert client.post(
            "/engine/pension-calculator", json=invalid
        ).status_code == 422
