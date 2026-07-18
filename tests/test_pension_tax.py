from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.chat.tools import (
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)
from backend.app.engine import (
    NonPensionWithdrawalInput,
    PensionTaxScenarioInput,
    WithdrawalCalculationMode,
    WithdrawalCalculationStatus,
    WithdrawalReason,
    calculate_pension_tax_credit,
    estimate_non_pension_withdrawal_tax,
)


def scenario(**updates) -> PensionTaxScenarioInput:
    payload = {
        "tax_year": 2026,
        "income_basis": "gross_salary",
        "income_amount_krw": "55000000",
        "pension_savings": {
            "balance_krw": "30000000",
            "current_year_contribution_krw": "6000000",
            "prior_year_non_deducted_principal_krw": "0",
        },
        "irp": {
            "balance_krw": "50000000",
            "current_year_contribution_krw": "3000000",
            "prior_year_non_deducted_principal_krw": "0",
        },
        "withdrawal_reason": "general",
        "irp_deferred_income_status": "none",
    }
    payload.update(updates)
    return PensionTaxScenarioInput.model_validate(payload)


def test_tax_credit_applies_account_and_combined_limits() -> None:
    result = calculate_pension_tax_credit(scenario().to_tax_credit_input())

    assert result.pension_savings_eligible_contribution_krw == Decimal("6000000")
    assert result.irp_eligible_contribution_krw == Decimal("3000000")
    assert result.total_eligible_contribution_krw == Decimal("9000000")
    assert result.unused_combined_limit_krw == Decimal("0")
    assert len(result.rate_scenarios) == 1
    assert result.rate_scenarios[0].local_inclusive_display_rate_percent == Decimal(
        "16.5"
    )
    assert result.rate_scenarios[0].estimated_tax_credit_krw == Decimal("1485000")


def test_tax_credit_uses_high_income_rate_and_allows_irp_only() -> None:
    result = calculate_pension_tax_credit(
        scenario(
            income_amount_krw="55000001",
            pension_savings={
                "balance_krw": "0",
                "current_year_contribution_krw": "0",
            },
            irp={
                "balance_krw": "9000000",
                "current_year_contribution_krw": "9000000",
            },
            irp_deferred_income_status="unknown",
        ).to_tax_credit_input()
    )

    assert result.pension_savings_eligible_contribution_krw == 0
    assert result.irp_eligible_contribution_krw == Decimal("9000000")
    assert result.rate_scenarios[0].local_inclusive_display_rate_percent == Decimal(
        "13.2"
    )
    assert result.rate_scenarios[0].estimated_tax_credit_krw == Decimal("1188000")


def test_unknown_income_returns_both_display_rate_scenarios() -> None:
    result = calculate_pension_tax_credit(
        scenario(income_basis="unknown", income_amount_krw=None).to_tax_credit_input()
    )

    assert result.rate_determined is False
    assert {
        item.local_inclusive_display_rate_percent for item in result.rate_scenarios
    } == {Decimal("13.2"), Decimal("16.5")}


def test_simple_max_withdrawal_reproduces_document_example() -> None:
    inputs = scenario(
        pension_savings={
            "balance_krw": "30000000",
            "current_year_contribution_krw": "0",
        },
        irp={
            "balance_krw": "50000000",
            "current_year_contribution_krw": "0",
        },
        irp_deferred_income_status="unknown",
    )

    result = estimate_non_pension_withdrawal_tax(inputs.to_withdrawal_input())

    assert result.calculation_mode == WithdrawalCalculationMode.SIMPLIFIED_MAX
    assert result.assumed_other_income_tax_base_krw == Decimal("80000000")
    assert result.estimated_max_other_income_withholding_krw == Decimal(
        "13200000"
    )
    assert any("이연퇴직소득" in item for item in result.assumptions)


def test_current_year_contributions_are_excluded_before_taxable_amount() -> None:
    result = estimate_non_pension_withdrawal_tax(scenario().to_withdrawal_input())

    assert result.calculation_mode == WithdrawalCalculationMode.SOURCE_AWARE
    assert result.total_current_year_contribution_excluded_krw == Decimal(
        "9000000"
    )
    assert result.assumed_other_income_tax_base_krw == Decimal("71000000")
    assert result.estimated_max_other_income_withholding_krw == Decimal(
        "11715000"
    )


def test_known_non_deducted_principal_and_deferred_income_are_excluded() -> None:
    result = estimate_non_pension_withdrawal_tax(
        scenario(
            pension_savings={
                "balance_krw": "30000000",
                "current_year_contribution_krw": "0",
                "prior_year_non_deducted_principal_krw": "1000000",
            },
            irp={
                "balance_krw": "50000000",
                "current_year_contribution_krw": "0",
                "prior_year_non_deducted_principal_krw": "2000000",
            },
            irp_deferred_income_status="known",
            irp_deferred_retirement_income_krw="20000000",
        ).to_withdrawal_input()
    )

    assert result.total_prior_year_non_deducted_principal_excluded_krw == Decimal(
        "3000000"
    )
    assert result.total_deferred_retirement_income_excluded_krw == Decimal(
        "20000000"
    )
    assert result.assumed_other_income_tax_base_krw == Decimal("57000000")
    assert result.estimated_max_other_income_withholding_krw == Decimal("9405000")


@pytest.mark.parametrize("reason", ("unavoidable", "unknown"))
def test_non_general_withdrawal_requires_review(reason: str) -> None:
    result = estimate_non_pension_withdrawal_tax(
        scenario(withdrawal_reason=reason).to_withdrawal_input()
    )

    assert result.status == WithdrawalCalculationStatus.REQUIRES_REVIEW
    assert result.estimated_max_other_income_withholding_krw is None


def test_unavoidable_reason_does_not_require_account_balances() -> None:
    result = estimate_non_pension_withdrawal_tax(
        NonPensionWithdrawalInput(
            withdrawal_reason=WithdrawalReason.UNAVOIDABLE
        )
    )

    assert result.status == WithdrawalCalculationStatus.REQUIRES_REVIEW
    assert result.total_balance_krw is None
    assert result.estimated_max_other_income_withholding_krw is None


def test_input_requires_consistent_income_and_deferred_status() -> None:
    with pytest.raises(ValidationError):
        scenario(income_basis="gross_salary", income_amount_krw=None)
    with pytest.raises(ValidationError):
        scenario(
            irp_deferred_income_status="known",
            irp_deferred_retirement_income_krw=None,
        )
    with pytest.raises(ValidationError):
        scenario(tax_year=2025)


def test_chat_tools_are_thin_engine_wrappers() -> None:
    inputs = scenario()
    credit_inputs = inputs.to_tax_credit_input()
    withdrawal_inputs = inputs.to_withdrawal_input()

    assert calculate_pension_tax_credit_tool(
        credit_inputs
    ) == calculate_pension_tax_credit(credit_inputs)
    assert estimate_non_pension_withdrawal_tax_tool(
        withdrawal_inputs
    ) == estimate_non_pension_withdrawal_tax(withdrawal_inputs)
