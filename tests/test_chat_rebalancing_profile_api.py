from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.api.deps import (
    get_optional_demo_user_context_repository,
    get_optional_investment_profile_repository,
)
from backend.app.auth import require_supabase_user_id
from backend.app.chat.user_context import DemoUserFinancialContext
from backend.app.engine import IncomeBasis
from backend.app.engine.profile import (
    QUESTIONS,
    ProfileSurveyInput,
    SurveyAnswer,
    evaluate_profile,
)
from backend.app.investment_profile_repository import (
    InvestmentProfileAnswer,
    InvestmentProfileAssessment,
    InvestmentProfilePreferences,
    StoredInvestmentProfile,
)
from backend.app.main import app

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _context() -> DemoUserFinancialContext:
    return DemoUserFinancialContext(
        auth_user_id=OWNER_ID,
        benchmark_user_id="USR09660",
        nickname="박준호",
        representative_age=35,
        customer_context="IRP 운용 고객",
        scenario_code="irp_builder",
        scenario_name="IRP 장기 운용",
        age_band="30대",
        risk_profile="active",
        investment_horizon_years=20,
        tax_year=2026,
        income_basis=IncomeBasis.UNKNOWN,
        income_amount_krw=Decimal("0"),
        dc_balance_krw=Decimal("0"),
        irp_balance_krw=Decimal("30000000"),
        pension_savings_balance_krw=Decimal("0"),
        total_pension_balance_krw=Decimal("30000000"),
        irp_contribution_krw=Decimal("0"),
        pension_savings_contribution_krw=Decimal("0"),
        as_of_date=date(2026, 7, 16),
        data_kind="mock",
        asset_classes=("etf",),
        defaulted_fields=(),
    )


def _stored_profile() -> tuple[StoredInvestmentProfile, str, str]:
    answers = [
        SurveyAnswer(
            question_code=question.code,
            selected_values=[question.options[0].value],
        )
        for question in QUESTIONS
    ]
    survey = ProfileSurveyInput(answers=answers)
    evaluation = evaluate_profile(survey)
    retirement_start_age = next(
        answer.selected_values[0]
        for answer in answers
        if answer.question_code == "retirement_start_age"
    )
    stored = StoredInvestmentProfile(
        assessment=InvestmentProfileAssessment(
            assessment_id=UUID("33333333-3333-3333-3333-333333333333"),
            owner_id=OWNER_ID,
            assessed_at=datetime.now(UTC),
            total_score=evaluation.total_score,
            min_score=evaluation.min_score,
            max_score=evaluation.max_score,
            score_percent=evaluation.score_percent,
            risk_profile=evaluation.risk_profile,
            engine_name=evaluation.engine_name,
            engine_version=evaluation.engine_version,
            rule_version=evaluation.rule_version,
            provisional=evaluation.provisional,
            answers=[
                InvestmentProfileAnswer(
                    question_code=question_code,
                    selected_value=selected_values[0],
                    selected_label=selected_values[0],
                    selected_score=0,
                )
                for question_code, selected_values in (
                    (answer.question_code, answer.selected_values) for answer in answers
                )
            ],
        ),
        preferences=InvestmentProfilePreferences(
            investment_advice_desired=True,
            investor_information_provided=True,
            confirmed_at=datetime.now(UTC),
            policy_version="2026-07-20.1",
        ),
    )
    return stored, retirement_start_age, str(evaluation.loss_tolerance_percent)


def test_rebalancing_profile_restores_saved_engine_inputs() -> None:
    stored, retirement_start_age, loss_tolerance_percent = _stored_profile()

    class ContextRepository:
        def get(self, owner_id: UUID):
            return _context() if owner_id == OWNER_ID else None

    class ProfileRepository:
        def get_latest(self, owner_id: UUID):
            return stored if owner_id == OWNER_ID else None

    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_optional_demo_user_context_repository] = (
        ContextRepository
    )
    app.dependency_overrides[get_optional_investment_profile_repository] = (
        ProfileRepository
    )
    try:
        with TestClient(app) as client:
            response = client.get("/chat/rebalancing-profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "account_type": "irp",
        "account_types": ["irp"],
        "current_age": 35,
        "retirement_start_age": int(retirement_start_age),
        "risk_profile": stored.assessment.risk_profile,
        "loss_tolerance_percent": loss_tolerance_percent,
    }

