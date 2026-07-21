from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.api.deps import get_investment_profile_repository
from backend.app.auth import require_supabase_user_id
from backend.app.engine.profile import QUESTIONS, evaluate_profile
from backend.app.investment_profile_repository import (
    InvestmentProfileAnswer,
    InvestmentProfileAssessment,
    InvestmentProfilePreferences,
    StoredInvestmentProfile,
)
from backend.app.main import app

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_OWNER_ID = UUID("22222222-2222-2222-2222-222222222222")


def _payload(**preferences: bool) -> dict:
    return {
        "survey": {
            "answers": [
                {"question_code": question.code, "selected_score": 3}
                for question in QUESTIONS
            ]
        },
        "investment_advice_desired": preferences.get(
            "investment_advice_desired", True
        ),
        "investor_information_provided": preferences.get(
            "investor_information_provided", True
        ),
    }


def _stored(owner_id: UUID) -> StoredInvestmentProfile:
    evaluation = evaluate_profile(_survey())
    return StoredInvestmentProfile(
        assessment=InvestmentProfileAssessment(
            assessment_id=UUID("33333333-3333-3333-3333-333333333333"),
            owner_id=owner_id,
            assessed_at=datetime(2026, 1, 13, tzinfo=UTC),
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
                    question_code=question.code,
                    selected_value="sample",
                    selected_label="예시",
                    selected_score=3,
                )
                for question in QUESTIONS
            ],
        ),
        preferences=InvestmentProfilePreferences(
            investment_advice_desired=True,
            investor_information_provided=True,
            confirmed_at=datetime(2026, 1, 13, tzinfo=UTC),
            policy_version="2026-07-20.1",
        ),
    )


def _survey():
    from backend.app.engine.profile import ProfileSurveyInput

    return ProfileSurveyInput.model_validate(_payload()["survey"])


def test_get_returns_explicit_empty_for_an_owner_without_an_assessment() -> None:
    class Repository:
        def get_latest(self, owner_id: UUID):
            assert owner_id == OWNER_ID
            return None

    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_investment_profile_repository] = Repository
    try:
        with TestClient(app) as client:
            response = client.get("/me/investment-profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"assessment": None, "preferences": None}


def test_post_uses_authenticated_owner_and_existing_engine_evaluation() -> None:
    recorded = []

    class Repository:
        def record(self, *, owner_id, survey, evaluation, preferences):
            recorded.append((owner_id, survey, evaluation, preferences))
            return _stored(owner_id)

    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_investment_profile_repository] = Repository
    try:
        with TestClient(app) as client:
            response = client.post("/me/investment-profile", json=_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert recorded[0][0] == OWNER_ID
    assert recorded[0][2] == evaluate_profile(recorded[0][1])
    assert response.json()["assessment"]["risk_profile"] == "risk_neutral"


def test_post_rejects_inconsistent_confirmation_preferences() -> None:
    class Repository:
        def record(self, **_kwargs):
            raise AssertionError("invalid confirmation must not be stored")

    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_investment_profile_repository] = Repository
    try:
        response = TestClient(app).post(
            "/me/investment-profile",
            json=_payload(
                investment_advice_desired=True,
                investor_information_provided=False,
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_profile_endpoints_require_authentication() -> None:
    response = TestClient(app).get("/me/investment-profile")

    assert response.status_code == 401


def test_get_returns_only_the_authenticated_owners_profile() -> None:
    class Repository:
        def get_latest(self, owner_id: UUID):
            return _stored(owner_id) if owner_id == OWNER_ID else None

    app.dependency_overrides[require_supabase_user_id] = lambda: OTHER_OWNER_ID
    app.dependency_overrides[get_investment_profile_repository] = Repository
    try:
        with TestClient(app) as client:
            response = client.get("/me/investment-profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"assessment": None, "preferences": None}
