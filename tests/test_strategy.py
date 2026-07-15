from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine import (
    AccountType,
    ProfitLockInput,
    ReturnSubperiod,
    RiskBudgetInput,
    evaluate_historical_returns,
    evaluate_profit_lock,
    evaluate_risk_budget,
)


def subperiod(
    start: str, end: str, beginning: str, ending_before_flow: str
) -> ReturnSubperiod:
    return ReturnSubperiod(
        period_start=date.fromisoformat(start),
        period_end=date.fromisoformat(end),
        beginning_value_krw=Decimal(beginning),
        ending_value_before_flow_krw=Decimal(ending_before_flow),
    )


def test_twr_excludes_contribution_between_valuation_subperiods() -> None:
    result = evaluate_historical_returns(
        [
            subperiod("2026-01-01", "2026-01-31", "100", "110"),
            # A contribution raises the next beginning value from 110 to 150.
            subperiod("2026-01-31", "2026-02-28", "150", "165"),
        ],
        periods_per_year=12,
    )

    assert result.subperiod_returns_percent == [
        Decimal("10.0000"),
        Decimal("10.0000"),
    ]
    assert result.cumulative_return_percent == Decimal("21.0000")


def test_historical_return_reports_realized_volatility_and_drawdown() -> None:
    result = evaluate_historical_returns(
        [
            subperiod("2026-01-01", "2026-01-02", "100", "110"),
            subperiod("2026-01-02", "2026-01-03", "110", "88"),
            subperiod("2026-01-03", "2026-01-04", "88", "92.4"),
        ],
        periods_per_year=252,
    )

    assert result.cumulative_return_percent == Decimal("-7.6000")
    assert result.maximum_drawdown_percent == Decimal("-20.0000")
    assert result.annualized_volatility_percent > 0


def test_return_subperiods_must_be_ordered_and_non_overlapping() -> None:
    with pytest.raises(ValueError, match="ordered and non-overlapping"):
        evaluate_historical_returns(
            [
                subperiod("2026-01-02", "2026-01-04", "100", "101"),
                subperiod("2026-01-03", "2026-01-05", "101", "102"),
            ]
        )


def test_risk_budget_matches_document_example_and_dc_cap() -> None:
    result = evaluate_risk_budget(
        RiskBudgetInput(
            account_type=AccountType.DC,
            current_value_krw=Decimal("100000000"),
            minimum_target_at_55_krw=Decimal("120000000"),
            years_to_55=20,
            safe_rate_assumption_percent=Decimal("2.5"),
            risk_multiplier=Decimal("2.5"),
            suitability_limit_percent=Decimal("80"),
        )
    )

    assert result.preservation_floor_krw == Decimal("73232513.14")
    assert result.cushion_limit_percent == Decimal("66.9187")
    assert result.allowed_risky_percent == Decimal("66.9187")
    assert "미래 수익 예측" in result.assumption_notice


def test_pension_savings_uses_suitability_limit_not_dc_irp_cap() -> None:
    result = evaluate_risk_budget(
        RiskBudgetInput(
            account_type=AccountType.PENSION_SAVINGS,
            current_value_krw=Decimal("100000000"),
            minimum_target_at_55_krw=Decimal("10000000"),
            years_to_55=10,
            safe_rate_assumption_percent=Decimal("2.5"),
            risk_multiplier=Decimal("3"),
            suitability_limit_percent=Decimal("85"),
        )
    )

    assert result.account_limit_percent == Decimal("100.0000")
    assert result.allowed_risky_percent == Decimal("85.0000")


def test_profit_lock_uses_larger_trigger_without_double_counting() -> None:
    result = evaluate_profit_lock(
        ProfitLockInput(
            age=35,
            total_value_krw=Decimal("106000000"),
            tactical_value_krw=Decimal("36000000"),
            tactical_checkpoint_krw=Decimal("30000000"),
            tactical_target_percent=Decimal("30"),
        )
    )

    assert result.overweight_triggered is False
    assert result.checkpoint_triggered is True
    assert result.recommended_transfer_krw == Decimal("3000000.00")


def test_profit_lock_document_overweight_example_moves_excess() -> None:
    result = evaluate_profit_lock(
        ProfitLockInput(
            age=35,
            total_value_krw=Decimal("106000000"),
            tactical_value_krw=Decimal("37100000"),
            tactical_checkpoint_krw=Decimal("30000000"),
            tactical_target_percent=Decimal("30"),
        )
    )

    assert result.tactical_weight_percent == Decimal("35.0000")
    assert result.overweight_triggered is True
    assert result.recommended_transfer_krw == Decimal("5300000.00")


def test_age_fifty_locks_seventy_percent_of_checkpoint_profit() -> None:
    result = evaluate_profit_lock(
        ProfitLockInput(
            age=52,
            total_value_krw=Decimal("106000000"),
            tactical_value_krw=Decimal("36000000"),
            tactical_checkpoint_krw=Decimal("30000000"),
            tactical_target_percent=Decimal("30"),
        )
    )

    assert result.recommended_transfer_krw == Decimal("4200000.00")
    assert result.transfer_destination == "stabilization"


def test_profit_lock_rejects_tactical_value_above_total() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        ProfitLockInput(
            age=35,
            total_value_krw=Decimal("100"),
            tactical_value_krw=Decimal("101"),
            tactical_checkpoint_krw=Decimal("90"),
            tactical_target_percent=Decimal("30"),
        )
