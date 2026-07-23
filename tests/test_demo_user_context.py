from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.chat import (
    AuthenticatedChatRequest,
    _authenticated_planning_request,
    _authenticated_request,
)
from backend.app.api.deps import (
    get_chat_narrator,
    get_chat_service,
    get_demo_user_context_repository,
    get_optional_chat_repository,
    get_optional_demo_user_context_repository,
    get_optional_investment_profile_repository,
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
from backend.app.retrieval.repository import NewsMatch
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
        benchmark_user_id="USR09660",
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
        asset_classes=("deposit",),
        defaulted_fields=(
            "income_amount_krw",
            "irp_contribution_krw",
            "pension_savings_contribution_krw",
            "irp_balance_krw",
            "pension_savings_balance_krw",
        ),
    )


def test_authenticated_planning_distinguishes_explicit_tax_payload() -> None:
    implicit_request = AuthenticatedChatRequest(message="결과를 알려줘")
    implicit_chat = _authenticated_request(implicit_request, _context())
    explicit_request = AuthenticatedChatRequest(
        message="결과를 알려줘",
        pension_tax=_context().to_pension_tax_input(),
    )
    explicit_chat = _authenticated_request(explicit_request, _context())

    assert implicit_chat.pension_tax is not None
    assert (
        _authenticated_planning_request(implicit_request, implicit_chat).pension_tax
        is None
    )
    assert (
        _authenticated_planning_request(explicit_request, explicit_chat).pension_tax
        is not None
    )


class FakeContextRepository:
    def get(self, auth_user_id: UUID) -> DemoUserFinancialContext | None:
        return _context() if auth_user_id == OWNER_ID else None


class FakeProfileOnlyContextRepository:
    def get(self, auth_user_id: UUID) -> None:
        return None

    def get_nickname(self, auth_user_id: UUID) -> str | None:
        return "김민재" if auth_user_id == OWNER_ID else None


class TopicAwareNewsRepository:
    def __init__(self) -> None:
        self.preferred_topics: tuple[str, ...] = ()

    def recent_market_news(
        self,
        *,
        region=None,
        days=5,
        limit=3,
        exclude_item_ids=(),
        preferred_topics=(),
    ):
        self.preferred_topics = preferred_topics
        return [
            NewsMatch(
                item_id="11111111-1111-4111-8111-111111111111",
                title="금리 변화와 채권시장",
                description=None,
                original_url="https://example.test/news/1",
                portal_url=None,
                published_at=datetime(2026, 7, 19, tzinfo=UTC),
                summary_lines=("요약 1", "요약 2", "요약 3"),
            )
        ][:limit]

    def latest_news(self, search_query, *, limit=10):
        raise AssertionError("증시뉴스는 market 조회를 사용해야 합니다")

    def news_by_ids(self, item_ids):
        return []


def _service(news=None) -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=news,
    )


def _override_chat(
    context_repository: FakeContextRepository
    | FakeProfileOnlyContextRepository
    | None = None,
    news_repository=None,
) -> None:
    context_repository = context_repository or FakeContextRepository()
    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_optional_chat_repository] = lambda: (
        FakeChatRepository()
    )
    app.dependency_overrides[get_optional_demo_user_context_repository] = lambda: (
        context_repository
    )
    app.dependency_overrides[get_optional_investment_profile_repository] = lambda: None
    app.dependency_overrides[get_demo_user_context_repository] = lambda: (
        context_repository
    )
    app.dependency_overrides[get_chat_service] = lambda: _service(news_repository)
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
        "USR09660",
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
        ("deposit",),
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
    assert context.asset_classes == ("deposit",)
    assert context.preferred_news_topics == (
        "monetary_policy",
        "macro",
        "fx_rates",
    )


class _ContextCursor:
    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row
        self.query = ""

    def __enter__(self) -> "_ContextCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, _params: tuple[object, ...]) -> None:
        self.query = query

    def fetchone(self) -> tuple[object, ...]:
        return self._row


class _ContextConnection:
    def __init__(self, cursor: _ContextCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _ContextCursor:
        return self._cursor


class _ContextPool:
    def __init__(self, cursor: _ContextCursor) -> None:
        self._connection = _ContextConnection(cursor)

    @contextmanager
    def connection(self):
        yield self._connection


def test_repository_reads_common_account_snapshot_tables() -> None:
    row = (
        OWNER_ID,
        "USR09660",
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
        ("deposit",),
    )
    cursor = _ContextCursor(row)
    repository = DemoUserContextRepository(
        "postgresql://test",
        pool=_ContextPool(cursor),
    )

    context = repository.get(OWNER_ID)

    assert context is not None
    assert context.dc_balance_krw == Decimal("60000000")
    assert "pension_accounts" in cursor.query
    assert "account_snapshots" in cursor.query
    assert "account_holding_snapshots" in cursor.query
    assert "mock_accounts" not in cursor.query
    assert "mock_holdings" not in cursor.query


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


def test_authenticated_news_prioritizes_topics_from_server_owned_assets() -> None:
    news = TopicAwareNewsRepository()
    _override_chat(news_repository=news)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "증시뉴스 알려줘"},
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    assert news.preferred_topics == _context().preferred_news_topics
    assert any("자산군과 연관된 뉴스 주제" in item for item in payload["limitations"])
    assert any(
        source["evidence_id"] == "mock:user_context"
        for source in payload["sources"]
    )


def test_authenticated_tax_rule_uses_verified_brief_without_salutation() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "연금계좌 규칙 알려줘"},
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    assert payload["data_mode"] == "verified_pension_tax_rule_brief"
    assert payload["salutation"] is None


def test_authenticated_deferred_topic_addresses_server_nickname_once() -> None:
    _override_chat()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "연금으로 받을 때 세금은?"},
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    assert payload["data_mode"] == "verified_pension_account_deferred_topic"
    assert payload["salutation"] == "박준호(가상)님"


def test_authenticated_overview_uses_profile_without_financial_context() -> None:
    _override_chat(FakeProfileOnlyContextRepository())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "연금계좌 전체적으로 정리해줘"},
                headers={
                    "Authorization": "Bearer test",
                    "Idempotency-Key": str(uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)["response"]
    assert payload["salutation"] == "김민재님"


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
    assert credit["pension_savings_contribution_krw"] == "0"
    assert credit["irp_contribution_krw"] == "0"
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
