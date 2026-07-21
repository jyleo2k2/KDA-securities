from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.deps import get_engine_audit_repository
from backend.app.auth import require_supabase_user_id
from backend.app.engine import (
    AccountType,
    HoldingInput,
    PortfolioInput,
    RiskTreatment,
    RuleStatus,
    StatutoryException,
    evaluate_risk_cap,
)
from backend.app.engine.audit import validate_rule_parameters
from backend.app.main import app, health, risk_cap, risk_cap_audited


def holding(
    holding_id: str,
    amount_krw: str,
    treatment: RiskTreatment,
    exception: StatutoryException | None = None,
) -> HoldingInput:
    return HoldingInput(
        holding_id=holding_id,
        amount_krw=Decimal(amount_krw),
        risk_treatment=treatment,
        statutory_exception=exception,
    )


def test_dc_exactly_seventy_percent_passes() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.DC,
        holdings=[
            holding("equity", "700000", RiskTreatment.GENERAL_RISKY),
            holding("deposit", "300000", RiskTreatment.CAPITAL_PRESERVATION),
        ],
    )

    result = evaluate_risk_cap(portfolio)

    assert result.total_amount_krw == Decimal("1000000.00")
    assert result.general_risky_ratio_percent == Decimal("70.00")
    assert result.limit_percent == Decimal("70.00")
    assert result.excess_general_risky_amount_krw == Decimal("0.00")
    assert result.within_limit is True
    assert result.status == RuleStatus.PASS


def test_irp_above_seventy_percent_reports_exact_excess() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.IRP,
        holdings=[
            holding("equity", "70010", RiskTreatment.GENERAL_RISKY),
            holding("deposit", "29990", RiskTreatment.CAPITAL_PRESERVATION),
        ],
    )

    result = evaluate_risk_cap(portfolio)

    assert result.general_risky_ratio_percent == Decimal("70.01")
    assert result.excess_general_risky_amount_krw == Decimal("10.00")
    assert result.within_limit is False
    assert result.status == RuleStatus.FAIL


def test_explicit_eligible_tdf_is_separate_from_general_risky_assets() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.DC,
        holdings=[
            holding("equity", "50000", RiskTreatment.GENERAL_RISKY),
            holding(
                "tdf",
                "50000",
                RiskTreatment.STATUTORY_EXCEPTION,
                StatutoryException.ELIGIBLE_TDF,
            ),
        ],
    )

    result = evaluate_risk_cap(portfolio)

    assert result.general_risky_amount_krw == Decimal("50000.00")
    assert result.statutory_exception_amount_krw == Decimal("50000.00")
    assert result.general_risky_ratio_percent == Decimal("50.00")
    assert result.evidence[0].statutory_exception_krw == Decimal("50000.00")
    assert result.status == RuleStatus.PASS


def test_exception_treatment_requires_explicit_exception_type() -> None:
    with pytest.raises(ValidationError, match="statutory_exception is required"):
        holding("tdf", "100000", RiskTreatment.STATUTORY_EXCEPTION)


def test_ordinary_holding_cannot_smuggle_exception_type() -> None:
    with pytest.raises(ValidationError, match="statutory_exception is required"):
        holding(
            "equity",
            "100000",
            RiskTreatment.GENERAL_RISKY,
            StatutoryException.DEFAULT_OPTION,
        )


def test_pension_savings_has_no_dc_irp_aggregate_cap() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.PENSION_SAVINGS,
        holdings=[holding("equity", "100000", RiskTreatment.GENERAL_RISKY)],
    )

    result = evaluate_risk_cap(portfolio)

    assert result.general_risky_ratio_percent == Decimal("100.00")
    assert result.limit_percent is None
    assert result.excess_general_risky_amount_krw is None
    assert result.within_limit is None
    assert result.status == RuleStatus.NOT_APPLICABLE


def test_pension_savings_rejects_dc_irp_exception_rule() -> None:
    with pytest.raises(ValidationError, match="do not apply to pension_savings"):
        PortfolioInput(
            account_type=AccountType.PENSION_SAVINGS,
            holdings=[
                holding(
                    "tdf",
                    "100000",
                    RiskTreatment.STATUTORY_EXCEPTION,
                    StatutoryException.ELIGIBLE_TDF,
                )
            ],
        )


def test_db_account_is_not_supported_by_the_guidance_engine() -> None:
    with pytest.raises(ValidationError):
        PortfolioInput.model_validate(
            {
                "account_type": "db",
                "holdings": [
                    {
                        "holding_id": "deposit",
                        "amount_krw": "100000",
                        "risk_treatment": "capital_preservation",
                    }
                ],
            }
        )


def test_zero_value_portfolio_is_rejected_instead_of_passing() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        PortfolioInput(
            account_type=AccountType.DC,
            holdings=[holding("empty", "0", RiskTreatment.CAPITAL_PRESERVATION)],
        )


def test_result_is_deterministic_and_json_serializable() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.IRP,
        holdings=[
            holding("equity", "0.10", RiskTreatment.GENERAL_RISKY),
            holding("deposit", "0.20", RiskTreatment.CAPITAL_PRESERVATION),
        ],
    )

    first = evaluate_risk_cap(portfolio)
    second = evaluate_risk_cap(portfolio)

    assert first == second
    assert first.total_amount_krw == Decimal("0.30")
    assert first.general_risky_ratio_percent == Decimal("33.33")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_fastapi_exposes_health_and_engine_golden_path() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.DC,
        holdings=[
            holding("equity", "700000", RiskTreatment.GENERAL_RISKY),
            holding("deposit", "300000", RiskTreatment.CAPITAL_PRESERVATION),
        ],
    )

    assert {route.path for route in app.routes} >= {
        "/health",
        "/engine/risk-cap",
        "/engine/risk-cap/audited",
    }
    assert health() == {"status": "ok"}
    assert risk_cap(portfolio).status == RuleStatus.PASS


def test_audit_rejects_database_rule_drift() -> None:
    portfolio = PortfolioInput(
        account_type=AccountType.DC,
        holdings=[
            holding("equity", "600000", RiskTreatment.GENERAL_RISKY),
            holding("deposit", "400000", RiskTreatment.CAPITAL_PRESERVATION),
        ],
    )
    evidence = evaluate_risk_cap(portfolio).evidence[0]

    validate_rule_parameters(
        {"max_percent": "70", "included_treatments": ["general_risky"]},
        evidence,
    )
    with pytest.raises(RuntimeError, match="does not match"):
        validate_rule_parameters(
            {"max_percent": "80", "included_treatments": ["general_risky"]},
            evidence,
        )


def test_audited_endpoint_records_authenticated_owner_and_returns_run_id() -> None:
    owner_id = UUID("11111111-1111-1111-1111-111111111111")
    run_id = UUID("22222222-2222-2222-2222-222222222222")
    recorded = []

    class Recorder:
        def record(self, evaluation, *, owner_id=None):
            recorded.append((evaluation, owner_id))
            return run_id

    portfolio = PortfolioInput(
        account_type=AccountType.IRP,
        holdings=[
            holding("equity", "500000", RiskTreatment.GENERAL_RISKY),
            holding("deposit", "500000", RiskTreatment.CAPITAL_PRESERVATION),
        ],
    )

    response = risk_cap_audited(
        portfolio,
        owner_id=owner_id,
        recorder=Recorder(),
    )

    assert response.run_id == run_id
    assert recorded == [(response.evaluation, owner_id)]


def test_audited_endpoint_returns_created() -> None:
    expected_owner_id = UUID("11111111-1111-1111-1111-111111111111")

    class Recorder:
        def record(self, _evaluation, *, owner_id: UUID) -> UUID:
            assert owner_id == expected_owner_id
            return UUID("22222222-2222-2222-2222-222222222222")

    app.dependency_overrides[require_supabase_user_id] = lambda: expected_owner_id
    app.dependency_overrides[get_engine_audit_repository] = Recorder
    try:
        with TestClient(app) as client:
            response = client.post(
                "/engine/risk-cap/audited",
                json={
                    "account_type": "irp",
                    "holdings": [
                        {
                            "holding_id": "equity",
                            "amount_krw": "500000",
                            "risk_treatment": "general_risky",
                        },
                        {
                            "holding_id": "deposit",
                            "amount_krw": "500000",
                            "risk_treatment": "capital_preservation",
                        },
                    ],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
