from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import (
    get_chat_narrator,
    get_chat_service,
    get_demo_user_context_repository,
    get_optional_chat_repository,
    get_optional_demo_user_context_repository,
)
from backend.app.auth import require_supabase_user_id
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatResponse, CompletedSurveyProfile
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.chat.user_context import (
    DemoUserContextRepository,
    DemoUserFinancialContext,
    apply_demo_context_evidence,
)
from backend.app.engine import AccountType, EducationalRiskProfile, IncomeBasis
from backend.app.main import app
from tests.conftest import FakeChatRepository, final_sse_response

OWNER_ID = UUID("0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01")
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260716060630_add_demo_user_financial_context.sql"
)


def _context() -> DemoUserFinancialContext:
    return DemoUserFinancialContext(
        auth_user_id=OWNER_ID,
        nickname="박준호(가상)",
        representative_age=46,
        customer_context="DC 적립금 방치형 고객",
        scenario_code="dc_dormant",
        scenario_name="DC형 방치",
        age_band="40대",
        risk_profile="balanced",
        investment_horizon_years=20,
        tax_year=2026,
        income_basis=IncomeBasis.UNKNOWN,
        income_amount_krw=Decimal("0"),
        dc_balance_krw=Decimal("60000000"),
        irp_balance_krw=Decimal("0"),
        pension_savings_balance_krw=Decimal("0"),
        total_pension_balance_krw=Decimal("60000000"),
        irp_contribution_krw=Decimal("0"),
        pension_savings_contribution_krw=Decimal("0"),
        as_of_date=date(2026, 7, 16),
        data_kind="mock",
        defaulted_fields=(
            "income_amount_krw",
            "irp_contribution_krw",
            "pension_savings_contribution_krw",
            "irp_balance_krw",
            "pension_savings_balance_krw",
        ),
    )


class FakeContextRepository:
    def get(self, auth_user_id: UUID) -> DemoUserFinancialContext | None:
        return _context() if auth_user_id == OWNER_ID else None


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


def _override_chat() -> None:
    context_repository = FakeContextRepository()
    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_optional_chat_repository] = lambda: (
        FakeChatRepository()
    )
    app.dependency_overrides[get_optional_demo_user_context_repository] = lambda: (
        context_repository
    )
    app.dependency_overrides[get_demo_user_context_repository] = lambda: (
        context_repository
    )
    app.dependency_overrides[get_chat_service] = _service
    app.dependency_overrides[get_chat_narrator] = lambda: None


def test_migration_keeps_demo_context_server_only_and_maps_six_users() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.demo_user_financial_context" in sql
    assert "enable row level security" in sql
    assert "auth.uid()) = auth_user_id" in sql
    assert "revoke all privileges" in sql
    assert "to service_role" in sql
    assert sql.count("@kda-demo.invalid") == 0
    assert sql.count("::uuid") == 6


def test_repository_normalizes_missing_database_values_to_zero() -> None:
    row = (
        OWNER_ID,
        "박준호(가상)",
        46,
        "DC 방치형",
        "dc_dormant",
        "DC형 방치",
        "40대",
        "balanced",
        20,
        2026,
        None,
        None,
        None,
        None,
        date(2026, 7, 16),
        "mock",
        Decimal("60000000"),
        Decimal("0"),
        Decimal("0"),
        Decimal("60000000"),
        1,
        0,
        0,
    )

    context = DemoUserContextRepository._context_from_row(row)

    assert context.income_basis == IncomeBasis.UNKNOWN
    assert context.income_amount_krw == 0
    assert context.irp_contribution_krw == 0
    assert context.pension_savings_contribution_krw == 0
    assert context.irp_balance_krw == 0
    assert set(context.defaulted_fields) >= {
        "income_amount_krw",
        "irp_contribution_krw",
        "pension_savings_contribution_krw",
        "irp_balance_krw",
    }


def test_authenticated_profile_uses_database_age_and_all_positive_accounts() -> None:
    profile = CompletedSurveyProfile(
        account_type=AccountType.IRP,
        account_types=[AccountType.IRP, AccountType.PENSION_SAVINGS],
        current_age=30,
        retirement_start_age=55,
        risk_profile=EducationalRiskProfile.RISK_NEUTRAL,
        loss_tolerance_percent=Decimal("10"),
    )

    personalized = _context().personalize_survey_profile(profile)

    assert personalized is not None
    assert personalized.current_age == 46
    assert personalized.account_type == AccountType.DC
    assert personalized.account_types == [AccountType.DC]
    assert personalized.risk_profile == EducationalRiskProfile.RISK_NEUTRAL
    assert personalized.loss_tolerance_percent == Decimal("10")


def test_payout_user_is_not_forced_into_accumulation_portfolio_engine() -> None:
    profile = CompletedSurveyProfile(
        account_type=AccountType.IRP,
        current_age=30,
        retirement_start_age=60,
        risk_profile=EducationalRiskProfile.STABLE_SEEKING,
        loss_tolerance_percent=Decimal("10"),
    )
    payout = _context().model_copy(update={"representative_age": 60})

    assert payout.personalize_survey_profile(profile) is None


@pytest.mark.parametrize(
    (
        "nickname",
        "age",
        "dc_balance",
        "irp_balance",
        "pension_savings_balance",
        "expected_accounts",
    ),
    (
        ("박준호(가상)", 46, 60_000_000, 0, 0, [AccountType.DC]),
        (
            "이서연(가상)",
            34,
            0,
            30_000_000,
            20_000_000,
            [AccountType.IRP, AccountType.PENSION_SAVINGS],
        ),
        (
            "정민재(가상)",
            32,
            100_000_000,
            50_000_000,
            40_000_000,
            [AccountType.DC, AccountType.IRP, AccountType.PENSION_SAVINGS],
        ),
        (
            "김하린(가상)",
            29,
            18_000_000,
            0,
            3_600_000,
            [AccountType.DC, AccountType.PENSION_SAVINGS],
        ),
        (
            "최지훈(가상)",
            47,
            65_000_000,
            12_000_000,
            9_000_000,
            [AccountType.DC, AccountType.IRP, AccountType.PENSION_SAVINGS],
        ),
        ("윤정희(가상)", 60, 0, 110_000_000, 45_000_000, None),
    ),
)
def test_all_six_demo_users_get_database_account_scope(
    nickname: str,
    age: int,
    dc_balance: int,
    irp_balance: int,
    pension_savings_balance: int,
    expected_accounts: list[AccountType] | None,
) -> None:
    profile = CompletedSurveyProfile(
        account_type=AccountType.IRP,
        current_age=30,
        retirement_start_age=60,
        risk_profile=EducationalRiskProfile.RISK_NEUTRAL,
        loss_tolerance_percent=Decimal("10"),
    )
    context = _context().model_copy(
        update={
            "nickname": nickname,
            "representative_age": age,
            "dc_balance_krw": Decimal(dc_balance),
            "irp_balance_krw": Decimal(irp_balance),
            "pension_savings_balance_krw": Decimal(pension_savings_balance),
        }
    )

    personalized = context.personalize_survey_profile(profile)

    if expected_accounts is None:
        assert personalized is None
    else:
        assert personalized is not None
        assert personalized.current_age == age
        assert personalized.account_types == expected_accounts


def test_zero_default_notice_is_not_added_to_unrelated_unavailable_response() -> None:
    response = apply_demo_context_evidence(
        ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer="ETF 데이터가 준비되지 않았습니다.",
            data_mode="unavailable",
        ),
        _context(),
    )

    assert not any("0원으로 처리" in item for item in response.limitations)
    assert not any("가상 목데이터" in item for item in response.limitations)


def test_me_endpoint_returns_authenticated_database_context() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/me/pension-context",
                headers={"Authorization": "Bearer test"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_code"] == "dc_dormant"
    assert payload["dc_balance_krw"] == "60000000"
    assert payload["irp_balance_krw"] == "0"
    assert payload["income_amount_krw"] == "0"


def test_authenticated_chat_answers_balance_from_loaded_context() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "내 IRP와 연금저축 현재 잔액을 알려줘"},
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    assert payload["data_mode"] == "authenticated_mock_context"
    assert payload["sources"][0]["evidence_id"] == "mock:user_context"
    assert "IRP 0원" in payload["answer"]
    assert "연금저축 0원" in payload["answer"]


def test_authenticated_tax_uses_database_context_not_client_values() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "내 연금계좌 세액공제를 계산해줘",
                    "scenario_code": "overlap_risk_concentration",
                    "pension_tax": {
                        "tax_year": 2026,
                        "income_basis": "gross_salary",
                        "income_amount_krw": "50000000",
                        "pension_savings": {
                            "balance_krw": "30000000",
                            "current_year_contribution_krw": "6000000",
                        },
                        "irp": {
                            "balance_krw": "50000000",
                            "current_year_contribution_krw": "3000000",
                        },
                        "withdrawal_reason": "general",
                        "irp_deferred_income_status": "none",
                    },
                },
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    credit = payload["pension_tax_result"]["tax_credit"]
    assert credit["pension_savings_contribution_krw"] == "0.00"
    assert credit["irp_contribution_krw"] == "0.00"
    assert payload["data_mode"] == "authenticated_mock_context_engine"
    assert any(source["data_boundary"] == "mock" for source in payload["sources"])
    assert payload["conversation_context"]["scenario_code"] == "dc_dormant"


def test_authenticated_scenario_code_cannot_be_spoofed() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "목계좌 시나리오를 진단해줘",
                    "scenario_code": "overlap_risk_concentration",
                },
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    assert payload["scenario_evaluation"]["scenario_code"] == "dc_dormant"
    assert payload["sources"][0]["locator"] == "database://mock-scenarios/current"


def test_authenticated_strategy_replaces_fixed_demo_age_and_account_scope() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "내 나이에 맞는 연금 운용 전략을 알려줘",
                    "survey_profile": {
                        "account_type": "irp",
                        "account_types": ["irp", "pension_savings"],
                        "current_age": 30,
                        "retirement_start_age": 55,
                        "risk_profile": "risk_neutral",
                        "loss_tolerance_percent": 10,
                    },
                },
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    survey = payload["conversation_context"]["survey_profile"]
    assert survey["current_age"] == 46
    assert survey["account_type"] == "dc"
    assert survey["account_types"] == ["dc"]
    assert "DC형 계좌용 교육 포트폴리오 데이터 저장소" in payload["answer"]
    assert not any("0원으로 처리" in item for item in payload["limitations"])
