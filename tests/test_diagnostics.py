from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.diagnostics import (
    CHECK_CASH_IDLE,
    CHECK_CONCENTRATION,
    CHECK_RISK_CAP,
    DIAGNOSTICS_SOURCE,
    ENGINE_VERSION,
    AccountHolding,
    AccountInput,
    evaluate_account_diagnostics,
)
from backend.app.engine.models import (
    AccountType,
    AssetClass,
    RiskTreatment,
    RuleStatus,
    StatutoryException,
)
from backend.app.engine.portfolio import evaluate_risk_cap
from tests.scenario_fixtures import (
    dc_dormant_account,
    overlap_dc_account,
    overlap_irp_account,
    overlap_pension_savings_account,
    uninvested_irp_account,
    uninvested_pension_savings_account,
)


def finding(evaluation, check_code):
    return next(f for f in evaluation.findings if f.check_code == check_code)


def test_dc_dormant_scenario_flags_cash_idle_only() -> None:
    evaluation = evaluate_account_diagnostics(dc_dormant_account())
    cash = finding(evaluation, CHECK_CASH_IDLE)
    assert cash.status == RuleStatus.FAIL
    assert cash.measured_percent == Decimal("100.00")
    assert finding(evaluation, CHECK_RISK_CAP).status == RuleStatus.PASS
    concentration = finding(evaluation, CHECK_CONCENTRATION)
    assert concentration.status == RuleStatus.NOT_APPLICABLE


def test_uninvested_scenario_flags_cash_idle_per_account() -> None:
    irp = evaluate_account_diagnostics(uninvested_irp_account())
    assert finding(irp, CHECK_CASH_IDLE).status == RuleStatus.FAIL
    savings = evaluate_account_diagnostics(uninvested_pension_savings_account())
    assert finding(savings, CHECK_CASH_IDLE).status == RuleStatus.FAIL
    assert finding(savings, CHECK_RISK_CAP).status == RuleStatus.NOT_APPLICABLE


def test_overlap_dc_scenario_separates_tdf_and_flags_concentration() -> None:
    evaluation = evaluate_account_diagnostics(overlap_dc_account())
    assert finding(evaluation, CHECK_CASH_IDLE).status == RuleStatus.PASS
    risk_cap = finding(evaluation, CHECK_RISK_CAP)
    assert risk_cap.status == RuleStatus.PASS
    assert risk_cap.measured_percent == Decimal("60.00")
    assert evaluation.risk_cap.statutory_exception_amount_krw == Decimal(
        "20000000.00"
    )
    concentration = finding(evaluation, CHECK_CONCENTRATION)
    assert concentration.status == RuleStatus.FAIL
    assert concentration.subject_asset_class == AssetClass.GLOBAL_EQUITY
    assert concentration.measured_percent == Decimal("60.00")


def test_overlap_irp_scenario_passes_cap_but_flags_concentration() -> None:
    evaluation = evaluate_account_diagnostics(overlap_irp_account())
    risk_cap = finding(evaluation, CHECK_RISK_CAP)
    assert risk_cap.status == RuleStatus.PASS
    assert risk_cap.measured_percent == Decimal("68.00")
    assert finding(evaluation, CHECK_CONCENTRATION).status == RuleStatus.FAIL


def test_overlap_pension_savings_has_no_cap_but_flags_concentration() -> None:
    evaluation = evaluate_account_diagnostics(overlap_pension_savings_account())
    assert finding(evaluation, CHECK_RISK_CAP).status == RuleStatus.NOT_APPLICABLE
    concentration = finding(evaluation, CHECK_CONCENTRATION)
    assert concentration.status == RuleStatus.FAIL
    assert concentration.measured_percent == Decimal("90.00")


def _cash_ratio_account(cash_krw: str, equity_krw: str) -> AccountInput:
    return AccountInput(
        account_id="boundary",
        account_type=AccountType.DC,
        holdings=[
            AccountHolding(
                holding_id="cash-1",
                instrument_name="현금성 모형",
                asset_class=AssetClass.CASH,
                amount_krw=Decimal(cash_krw),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
            AccountHolding(
                holding_id="equity-1",
                instrument_name="주식형 모형",
                asset_class=AssetClass.DOMESTIC_EQUITY,
                amount_krw=Decimal(equity_krw),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
        ],
    )


def test_cash_idle_threshold_boundary() -> None:
    below = evaluate_account_diagnostics(_cash_ratio_account("7999", "2001"))
    assert finding(below, CHECK_CASH_IDLE).status == RuleStatus.PASS
    at_threshold = evaluate_account_diagnostics(_cash_ratio_account("8000", "2000"))
    assert finding(at_threshold, CHECK_CASH_IDLE).status == RuleStatus.FAIL


def test_diagnostics_exposes_approved_threshold_policy_source() -> None:
    evaluation = evaluate_account_diagnostics(_cash_ratio_account("8000", "2000"))

    assert evaluation.engine_version == ENGINE_VERSION == "2026-07-23.1"
    assert DIAGNOSTICS_SOURCE.label == (
        "계좌별 진단 운영 기준 (현금성 80%·비현금 단일 자산군 50%)"
    )
    assert DIAGNOSTICS_SOURCE.as_of.isoformat() == "2026-07-23"


def test_risk_cap_finding_is_delegated_not_recomputed() -> None:
    account = overlap_dc_account()
    evaluation = evaluate_account_diagnostics(account)
    delegated = evaluate_risk_cap(account.to_portfolio_input())
    assert evaluation.risk_cap.model_dump(mode="json") == delegated.model_dump(
        mode="json"
    )


def test_pension_savings_rejects_dc_irp_exception_via_reused_rules() -> None:
    with pytest.raises(ValidationError):
        AccountInput(
            account_id="invalid",
            account_type=AccountType.PENSION_SAVINGS,
            holdings=[
                AccountHolding(
                    holding_id="tdf-1",
                    instrument_name="적격 TDF 모형",
                    asset_class=AssetClass.ELIGIBLE_TDF,
                    amount_krw=Decimal("1000000"),
                    risk_treatment=RiskTreatment.STATUTORY_EXCEPTION,
                    statutory_exception=StatutoryException.ELIGIBLE_TDF,
                )
            ],
        )


def test_diagnostics_are_deterministic() -> None:
    account = overlap_dc_account()
    first = evaluate_account_diagnostics(account).model_dump(mode="json")
    second = evaluate_account_diagnostics(account).model_dump(mode="json")
    assert first == second
