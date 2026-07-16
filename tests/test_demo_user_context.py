from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

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
from backend.app.chat.repository import SavedChatExchange
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.chat.user_context import (
    DemoUserContextRepository,
    DemoUserFinancialContext,
)
from backend.app.engine import IncomeBasis
from backend.app.main import app

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


class FakeChatRepository:
    def find_idempotent_exchange(self, **kwargs):
        return None

    def save_exchange(self, **kwargs) -> SavedChatExchange:
        return SavedChatExchange(
            session_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            response=kwargs["response"],
        )


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
                "/chat",
                json={"message": "내 IRP와 연금저축 현재 잔액을 알려줘"},
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["response"]
    assert payload["data_mode"] == "authenticated_mock_context"
    assert payload["sources"][0]["evidence_id"] == "mock:user_context"
    assert "IRP 0원" in payload["answer"]
    assert "연금저축 0원" in payload["answer"]


def test_authenticated_tax_uses_database_context_not_client_values() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
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
    payload = response.json()["response"]
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
                "/chat",
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
    payload = response.json()["response"]
    assert payload["scenario_evaluation"]["scenario_code"] == "dc_dormant"
    assert payload["sources"][0]["locator"] == "database://mock-scenarios/current"
