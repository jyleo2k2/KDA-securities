import json
import threading
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

import backend.app.api.chat as chat_api
from backend.app.api.deps import (
    get_chat_narrator,
    get_chat_repository,
    get_chat_service,
    get_chat_topic_guard,
    get_optional_chat_repository,
    get_optional_demo_user_context_repository,
)
from backend.app.auth import require_supabase_user_id
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import (
    ChatIntent,
    ChatRequest,
    ConversationContext,
    NewsConversationContext,
)
from backend.app.chat.query_planner import BlockedReason, plan_question
from backend.app.chat.repository import (
    ChatSessionAccessError,
    ChatSessionSummary,
    SavedChatExchange,
    StoredChatMessage,
)
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.chat.user_context import DemoUserFinancialContext
from backend.app.engine import IncomeBasis
from backend.app.main import app
from tests.conftest import FakeChatRepository as _BaseFakeChatRepository
from tests.conftest import final_sse_response, parse_sse

OWNER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER_MESSAGE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ASSISTANT_MESSAGE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
CHAT_HEADERS = {"Idempotency-Key": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"}


class FakeChatRepository(_BaseFakeChatRepository):
    def __init__(self) -> None:
        super().__init__(
            session_id=SESSION_ID,
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
        )
        self.deleted: list[dict[str, UUID]] = []
        self.deleted_all: list[UUID] = []

    def list_sessions(self, owner_id: UUID) -> list[ChatSessionSummary]:
        assert owner_id == OWNER_ID
        timestamp = datetime(2026, 7, 15, tzinfo=UTC)
        return [
            ChatSessionSummary(
                session_id=SESSION_ID,
                title="IRP 규칙",
                created_at=timestamp,
                updated_at=timestamp,
            )
        ]

    def get_messages(self, *, owner_id: UUID, session_id: UUID):
        assert owner_id == OWNER_ID
        assert session_id == SESSION_ID
        response = _service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))
        timestamp = datetime(2026, 7, 15, tzinfo=UTC)
        return [
            StoredChatMessage(
                message_id=USER_MESSAGE_ID,
                role="user",
                content="IRP 위험자산 한도를 알려줘",
                model_name=None,
                created_at=timestamp,
                evidence=(),
            ),
            StoredChatMessage(
                message_id=ASSISTANT_MESSAGE_ID,
                role="assistant",
                content=json.dumps(
                    {
                        "schema_version": 1,
                        "question_message_id": str(USER_MESSAGE_ID),
                        "response": response.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
                model_name=None,
                created_at=timestamp,
                evidence=(),
            ),
        ]

    def delete_session(self, *, owner_id: UUID, session_id: UUID) -> UUID:
        self.deleted.append({"owner_id": owner_id, "session_id": session_id})
        return session_id

    def delete_all_sessions(self, *, owner_id: UUID) -> int:
        self.deleted_all.append(owner_id)
        return 1


def test_authenticated_session_restores_server_context_over_client_context() -> None:
    trusted_id = "11111111-1111-4111-8111-111111111111"
    tampered_id = "22222222-2222-4222-8222-222222222222"
    trusted = ConversationContext(
        last_intent=ChatIntent.NEWS,
        news=NewsConversationContext(news_item_ids=[trusted_id]),
    )

    class Repository:
        def get_latest_conversation_context(self, *, owner_id, session_id):
            assert owner_id == OWNER_ID
            assert session_id == SESSION_ID
            return trusted

    request = chat_api.AuthenticatedChatRequest(
        message="첫 번째 기사 보여줘",
        session_id=SESSION_ID,
        conversation_context=ConversationContext(
            last_intent=ChatIntent.NEWS,
            news=NewsConversationContext(news_item_ids=[tampered_id]),
        ),
    )

    restored = chat_api._restore_session_conversation_context(
        request,
        Repository(),
        OWNER_ID,
    )

    assert restored.conversation_context == trusted


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


def _override_authenticated_dependencies(repository) -> None:
    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_chat_service] = _service
    app.dependency_overrides[get_chat_narrator] = lambda: None
    app.dependency_overrides[get_optional_chat_repository] = lambda: repository
    app.dependency_overrides[get_chat_repository] = lambda: repository


def test_authenticated_chat_persists_supported_response() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)
    assert payload["persisted"] is True
    assert payload["session_id"] == str(SESSION_ID)
    assert payload["response"]["intent"] == "account_rule"
    assert len(repository.saved) == 1
    assert repository.saved[0]["owner_id"] == OWNER_ID
    assert repository.saved[0]["idempotency_key"] == UUID(
        CHAT_HEADERS["Idempotency-Key"]
    )


class VerifiedNarrator:
    def narrate(self, response, **kwargs):
        return response.model_copy(
            update={
                "answer": "검증된 설명: IRP 일반 위험자산 한도는 70%입니다.",
                "narration_mode": "claude_verified",
                "model_name": "test-model",
            }
        )


class MustNotRunNarrator:
    def narrate(self, response, **kwargs):
        raise AssertionError("out-of-scope responses must not reach the narrator")


def test_authenticated_stream_saves_after_narration_update(monkeypatch) -> None:
    order: list[str] = []
    original_sse = chat_api._sse

    def traced_sse(event, payload):
        if event == "narration_update":
            order.append("narration_update")
        return original_sse(event, payload)

    class OrderingRepository(FakeChatRepository):
        def save_exchange(self, **kwargs):
            order.append("save_exchange")
            return super().save_exchange(**kwargs)

    repository = OrderingRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_chat_narrator] = VerifiedNarrator
    monkeypatch.setattr(chat_api, "_sse", traced_sse)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert order == ["narration_update", "save_exchange"]
    assert repository.saved[0]["response"].narration_mode == "claude_verified"


def test_authenticated_stream_skips_narrator_for_unsupported_question() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_chat_narrator] = MustNotRunNarrator
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "오늘 밥 뭐 먹었어?"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)
    assert payload["response"]["intent"] == "out_of_scope"
    assert payload["response"]["narration_mode"] == "deterministic"


def test_authenticated_stream_uses_topic_guard_only_after_unsupported_plan() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    calls: list[tuple[str, BlockedReason | None]] = []

    class RecoveringTopicGuard:
        def refine_plan(self, message, plan):
            calls.append((message, plan.blocked_reason))
            routed = plan_question("DC형, IRP, 연금저축은 뭐가 달라?")
            assert routed.intent is ChatIntent.ACCOUNT_RULE
            return routed.model_copy(
                update={"normalized_message": plan.normalized_message}
            )

    app.dependency_overrides[get_chat_topic_guard] = RecoveringTopicGuard
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "노후에 받는 돈은 언제부터 꺼내 써?"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)
    assert calls == [
        (
            "노후에 받는 돈은 언제부터 꺼내 써?",
            BlockedReason.UNSUPPORTED,
        )
    ]
    assert payload["response"]["intent"] == "account_rule"
    assert payload["persisted"] is True


def test_authenticated_chat_stream_persists_final_response() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "대화 기록을 저장하고 있습니다." not in response.text
    assert "답변을 정리했어요." in response.text
    assert '"persisted": true' in response.text
    assert len(repository.saved) == 1


def test_authenticated_chat_stream_does_not_persist_sensitive_query() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "주민등록번호 900101-1234567로 IRP를 확인해줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "대화 기록을 저장하고 있습니다." not in response.text
    assert "event: answer_delta" in response.text
    final_block = next(
        block
        for block in response.text.strip().split("\n\n")
        if block.startswith("event: response")
    )
    final = json.loads(final_block.split("data: ", 1)[1])
    assert final["persisted"] is False
    assert final["response"]["intent"] == "out_of_scope"
    assert "900101" not in response.text
    assert repository.saved == []


def test_authenticated_pension_tax_keeps_context_and_idempotency() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": (
                        "올해 연금저축에 600만원, IRP에 300만원을 납입했고 "
                        "세액공제 혜택을 알려줘"
                    ),
                    "conversation_context": {"account_type": "irp"},
                },
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)
    assert payload["persisted"] is True
    assert payload["response"]["intent"] == "pension_tax"
    assert payload["response"]["pension_tax_result"]["tax_credit"] is not None
    assert payload["response"]["answer"].startswith("고객님의 올해 연금세액공제 혜택")
    assert payload["response"]["conversation_context"]["account_type"] == "irp"
    assert repository.saved[0]["idempotency_key"] == UUID(
        CHAT_HEADERS["Idempotency-Key"]
    )


@pytest.mark.parametrize("nickname", ["정민재", "김연금"])
def test_authenticated_pension_tax_personalizes_any_user(nickname: str) -> None:
    class NicknameRepository:
        def get(self, owner_id):
            assert owner_id == OWNER_ID
            return None

        def get_nickname(self, owner_id):
            assert owner_id == OWNER_ID
            return nickname

    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_optional_demo_user_context_repository] = lambda: (
        NicknameRepository()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": (
                        "올해 연금저축에 600만원, IRP에 300만원을 납입했고 "
                        "총급여는 5000만원이야. 세액공제 혜택을 알려줘"
                    )
                },
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    payload = final_sse_response(response.text)
    assert payload["response"]["answer"].startswith(
        f"{nickname}님의 올해 연금세액공제 혜택을 정리했어요."
    )
    assert [item["label"] for item in payload["response"]["numeric_evidence"][:6]] == [
        "총급여액",
        "세액공제율",
        "올해 연금저축 납입액",
        "올해 IRP 납입액",
        "세액공제대상 납입액",
        "세액공제액",
    ]


def test_authenticated_missed_tax_credit_uses_saved_user_context() -> None:
    context = DemoUserFinancialContext(
        auth_user_id=OWNER_ID,
        benchmark_user_id="USR-MISSED-TAX",
        nickname="정민재",
        representative_age=35,
        customer_context="IRP 납입 고객",
        scenario_code="irp_tax_credit",
        scenario_name="IRP 세액공제",
        age_band="30대",
        risk_profile="balanced",
        investment_horizon_years=25,
        tax_year=2026,
        income_basis=IncomeBasis.GROSS_SALARY,
        income_amount_krw=Decimal("50000000"),
        dc_balance_krw=Decimal("0"),
        irp_balance_krw=Decimal("50000000"),
        pension_savings_balance_krw=Decimal("0"),
        total_pension_balance_krw=Decimal("50000000"),
        irp_contribution_krw=Decimal("7680000"),
        pension_savings_contribution_krw=Decimal("0"),
        as_of_date=date(2026, 7, 23),
        data_kind="mock",
    )

    class ContextRepository:
        def get(self, owner_id):
            assert owner_id == OWNER_ID
            return context

        def get_nickname(self, owner_id):
            assert owner_id == OWNER_ID
            return context.nickname

    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_optional_demo_user_context_repository] = lambda: (
        ContextRepository()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "내가 놓치고 있는 세액공제혜택을 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    payload = final_sse_response(response.text)["response"]
    assert payload["data_mode"] == "missed_pension_tax_credit_engine"
    assert payload["answer"].splitlines() == [
        "정민재님은 올해 217,800원 만큼의 세금을 덜 돌려받고 있어요.",
        "",
        "연금저축계좌나 IRP 또는 DC형 계좌에 1,320,000원 만큼을 추가로 납입하세요.",
        "",
        "그러면 정민재님의 최대 세액공제혜택 1,485,000원을 온전히 받을 수 있어요.",
    ]
    assert payload["limitations"][0] == (
        "실제 환급액은 소득세 결정세액 등에 따라 달라질 수 있으므로 자세한 "
        "내용은 금융기관에 확인하거나 세무전문가와 상담해야 해요."
    )


@pytest.mark.parametrize(
    (
        "owner_id",
        "benchmark_user_id",
        "nickname",
        "income_amount",
        "pension_savings_contribution",
        "irp_contribution",
        "expected_remaining",
        "expected_missed",
        "expected_maximum",
    ),
    (
        (
            "0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01",
            "USR09660",
            "박준호(가상)",
            "64640000",
            "0",
            "0",
            "9000000",
            "1188000",
            "1188000",
        ),
        (
            "1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02",
            "USR00540",
            "이서연(가상)",
            "61730000",
            "0",
            "0",
            "9000000",
            "1188000",
            "1188000",
        ),
        (
            "2f5cae61-5f80-4040-b3c2-9f33c4d93e03",
            "USR03419",
            "정민재(가상)",
            "97500000",
            "3840000",
            "4920000",
            "240000",
            "31680",
            "1188000",
        ),
        (
            "306dbf72-6091-4141-84d3-a044d5ea4f04",
            "USR08633",
            "김하린(가상)",
            "38810000",
            "0",
            "0",
            "9000000",
            "1485000",
            "1485000",
        ),
        (
            "417ec083-71a2-4242-95e4-b155e6fb5005",
            "USR00109",
            "최지훈(가상)",
            "54050000",
            "0",
            "7680000",
            "1320000",
            "217800",
            "1485000",
        ),
    ),
)
def test_all_login_candidates_complete_pension_tax_follow_up_flow(
    owner_id: str,
    benchmark_user_id: str,
    nickname: str,
    income_amount: str,
    pension_savings_contribution: str,
    irp_contribution: str,
    expected_remaining: str,
    expected_missed: str,
    expected_maximum: str,
) -> None:
    context = DemoUserFinancialContext(
        auth_user_id=UUID(owner_id),
        benchmark_user_id=benchmark_user_id,
        nickname=nickname,
        representative_age=40,
        customer_context="로그인 후보 사용자 회귀 테스트",
        scenario_code="authenticated_pension_tax_flow",
        scenario_name="로그인 사용자 연금세액공제",
        age_band="로그인 후보",
        risk_profile="balanced",
        investment_horizon_years=20,
        tax_year=2026,
        income_basis=IncomeBasis.GROSS_SALARY,
        income_amount_krw=Decimal(income_amount),
        dc_balance_krw=Decimal("0"),
        irp_balance_krw=Decimal("0"),
        pension_savings_balance_krw=Decimal("0"),
        total_pension_balance_krw=Decimal("0"),
        irp_contribution_krw=Decimal(irp_contribution),
        pension_savings_contribution_krw=Decimal(pension_savings_contribution),
        as_of_date=date(2026, 7, 23),
        data_kind="mock",
    )
    expected_name = nickname.replace("(가상)", "")
    service = _service()

    def ask(message: str):
        authenticated = chat_api.AuthenticatedChatRequest(message=message)
        request = chat_api._authenticated_request(authenticated, context)
        planning_request = chat_api._authenticated_planning_request(
            authenticated, request
        )
        response, _ = chat_api._authenticated_response(
            request=request,
            plan=service.plan(planning_request),
            service=service,
            context=context,
            nickname=nickname,
        )
        return response

    tax_response = ask("올해 받을 수 있는 연금세액공제가 궁금해.")
    assert tax_response.answer.startswith(
        f"{expected_name}님의 올해 연금세액공제 혜택을 정리했어요."
    )
    assert [item.follow_up_id for item in tax_response.suggested_follow_ups] == [
        "tax_to_diff",
        "tax_missed_benefit",
    ]

    missed_response = ask("내가 놓치고 있는 세액공제혜택을 알려줘")
    assert missed_response.data_mode == "missed_pension_tax_credit_engine"
    assert missed_response.answer.splitlines() == [
        (
                f"{expected_name}님은 올해 {Decimal(expected_missed):,.0f}원 만큼의 "
            "세금을 덜 돌려받고 있어요."
        ),
        "",
        (
            "연금저축계좌나 IRP 또는 DC형 계좌에 "
            f"{Decimal(expected_remaining):,.0f}원 만큼을 추가로 납입하세요."
        ),
        "",
        (
                f"그러면 {expected_name}님의 최대 세액공제혜택 "
            f"{Decimal(expected_maximum):,.0f}원을 온전히 받을 수 있어요."
        ),
    ]

    account_response = ask("DC형, IRP, 연금저축은 뭐가 달라?")
    assert account_response.data_mode == "verified_pension_account_brief"
    account_content = account_response.model_dump_json()
    assert "연금저축펀드" in account_content
    assert "개인형 퇴직연금(IRP)" in account_content
    assert "DC형 퇴직연금" in account_content


def test_sensitive_query_is_not_persisted_or_echoed() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": ("주민등록번호 900101-1234567로 IRP를 확인해줘")},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = final_sse_response(response.text)
    assert payload["persisted"] is False
    assert payload["session_id"] is None
    assert "900101" not in response.text
    assert repository.saved == []


def test_blocked_query_works_without_chat_database() -> None:
    _override_authenticated_dependencies(None)
    try:
        with TestClient(app) as client:
            blocked = client.post(
                "/chat/stream",
                json={"message": "이 상품을 대신 매수해줘"},
                headers=CHAT_HEADERS,
            )
            supported = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert blocked.status_code == 200
    assert final_sse_response(blocked.text)["persisted"] is False

    assert supported.status_code == 200
    supported_events = parse_sse(supported.text)
    assert (
        "error",
        {
            "code": "DATABASE_NOT_CONFIGURED",
            "message": "Chat database is not configured",
        },
    ) in supported_events


def test_existing_session_without_repository_errors_before_answer_delta() -> None:
    _override_authenticated_dependencies(None)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "IRP 위험자산 한도를 알려줘",
                    "session_id": str(SESSION_ID),
                },
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    events = parse_sse(response.text)
    assert events == [
        ("phase", {"message": "질문을 살펴보고 있어요."}),
        (
            "error",
            {
                "code": "DATABASE_NOT_CONFIGURED",
                "message": "Chat database is not configured",
            },
        ),
    ]


def test_chat_requires_bearer_authentication() -> None:
    repository = FakeChatRepository()
    app.dependency_overrides[get_chat_service] = _service
    app.dependency_overrides[get_chat_narrator] = lambda: None
    app.dependency_overrides[get_optional_chat_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_chat_metadata_requires_bearer_authentication() -> None:
    app.dependency_overrides[get_chat_service] = _service
    try:
        with TestClient(app) as client:
            responses = [
                client.get(path)
                for path in (
                    "/chat/capabilities",
                    "/chat/scenarios",
                    "/chat/heroes",
                )
            ]
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [401, 401, 401]


def test_authenticated_chat_metadata_returns_demo_data() -> None:
    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_chat_service] = _service
    try:
        with TestClient(app) as client:
            capabilities = client.get("/chat/capabilities")
            scenarios = client.get("/chat/scenarios")
            heroes = client.get("/chat/heroes")
    finally:
        app.dependency_overrides.clear()

    assert capabilities.status_code == 200
    assert "dc_dormant" in capabilities.json()["scenario_codes"]
    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 6
    assert heroes.status_code == 200
    assert len(heroes.json()) == 6


def test_delete_chat_session_requires_bearer_authentication() -> None:
    repository = FakeChatRepository()
    app.dependency_overrides[get_chat_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.delete(f"/chat/sessions/{SESSION_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert repository.deleted == []


def test_delete_all_chat_sessions_requires_bearer_authentication() -> None:
    repository = FakeChatRepository()
    app.dependency_overrides[get_chat_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.delete("/chat/sessions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert repository.deleted_all == []


def test_session_history_returns_current_chat_response_contract() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            sessions = client.get("/chat/sessions")
            messages = client.get(f"/chat/sessions/{SESSION_ID}/messages")
    finally:
        app.dependency_overrides.clear()

    assert sessions.status_code == 200
    assert sessions.json()[0]["session_id"] == str(SESSION_ID)
    assert messages.status_code == 200
    payload = messages.json()
    assert payload[0]["role"] == "user"
    assert payload[1]["response"]["intent"] == "account_rule"
    assert payload[1]["question_message_id"] == str(USER_MESSAGE_ID)


def test_authenticated_user_can_delete_owned_session() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.delete(f"/chat/sessions/{SESSION_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert repository.deleted == [{"owner_id": OWNER_ID, "session_id": SESSION_ID}]


def test_authenticated_user_can_delete_all_owned_sessions() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.delete("/chat/sessions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert repository.deleted_all == [OWNER_ID]


class ForeignSessionRepository(FakeChatRepository):
    def get_messages(self, *, owner_id: UUID, session_id: UUID):
        raise ChatSessionAccessError("not found")

    def delete_session(self, *, owner_id: UUID, session_id: UUID) -> UUID:
        raise ChatSessionAccessError("not found")


def test_foreign_session_is_reported_as_not_found() -> None:
    repository = ForeignSessionRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.get(f"/chat/sessions/{uuid4()}/messages")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_foreign_session_delete_is_reported_as_not_found() -> None:
    repository = ForeignSessionRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.delete(f"/chat/sessions/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


class UnavailableRepository(FakeChatRepository):
    def save_exchange(self, **kwargs) -> SavedChatExchange:
        raise psycopg.OperationalError("database unavailable")

    def delete_session(self, *, owner_id: UUID, session_id: UUID) -> UUID:
        raise psycopg.OperationalError("database unavailable")


class InvalidStoredResponseRepository(FakeChatRepository):
    def __init__(self, failing_operation: str) -> None:
        super().__init__()
        self.failing_operation = failing_operation

    def find_idempotent_exchange(self, **kwargs) -> SavedChatExchange | None:
        if self.failing_operation == "find":
            raise RuntimeError("stored response is invalid")
        return super().find_idempotent_exchange(**kwargs)

    def save_exchange(self, **kwargs) -> SavedChatExchange:
        if self.failing_operation == "save":
            raise RuntimeError("stored response is invalid")
        return super().save_exchange(**kwargs)


@pytest.mark.parametrize("failing_operation", ["find", "save"])
def test_invalid_stored_response_emits_stream_error(failing_operation: str) -> None:
    _override_authenticated_dependencies(
        InvalidStoredResponseRepository(failing_operation)
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        "error",
        {
            "code": "DATA_SOURCE_UNAVAILABLE",
            "message": "Chat database is unavailable",
        },
    ) in parse_sse(response.text)


def test_delete_database_failure_returns_service_unavailable() -> None:
    _override_authenticated_dependencies(UnavailableRepository())
    try:
        with TestClient(app) as client:
            response = client.delete(f"/chat/sessions/{SESSION_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_database_failure_is_distinct_from_auth_failure() -> None:
    _override_authenticated_dependencies(UnavailableRepository())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        "error",
        {
            "code": "DATA_SOURCE_UNAVAILABLE",
            "message": "Chat database is unavailable",
        },
    ) in parse_sse(response.text)


class UnavailableChatService(ChatService):
    def ask(self, request, *, plan=None):
        raise psycopg.OperationalError("retrieval unavailable")


def test_retrieval_failure_does_not_leave_an_orphan_question() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_chat_service] = lambda: UnavailableChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        "error",
        {
            "code": "DATA_SOURCE_UNAVAILABLE",
            "message": "Chat data source is unavailable",
        },
    ) in parse_sse(response.text)
    assert repository.saved == []


def test_authenticated_chat_requires_a_uuid_idempotency_key() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream", json={"message": "IRP 위험자산 한도를 알려줘"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert repository.saved == []


class ReplayChatRepository(FakeChatRepository):
    def find_idempotent_exchange(self, **kwargs) -> SavedChatExchange | None:
        return SavedChatExchange(
            session_id=SESSION_ID,
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
            replayed=True,
            response=_service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘")),
        )


def test_authenticated_chat_replays_before_generating_or_persisting() -> None:
    repository = ReplayChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert final_sse_response(response.text)["idempotency_replayed"] is True
    assert repository.saved == []


def test_authenticated_chat_loads_session_and_demo_context_in_parallel() -> None:
    barrier = threading.Barrier(2, timeout=1)

    class ParallelRepository(FakeChatRepository):
        def get_latest_conversation_context(self, *, owner_id, session_id):
            assert (owner_id, session_id) == (OWNER_ID, SESSION_ID)
            barrier.wait()
            return None

    class ParallelContextRepository:
        def get(self, owner_id):
            assert owner_id == OWNER_ID
            barrier.wait()
            return None

        def get_nickname(self, owner_id):
            assert owner_id == OWNER_ID
            return None

    repository = ParallelRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_optional_demo_user_context_repository] = lambda: (
        ParallelContextRepository()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "IRP 위험자산 한도를 알려줘",
                    "session_id": str(SESSION_ID),
                },
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert final_sse_response(response.text)["persisted"] is True


def test_demo_context_database_failure_does_not_stop_authenticated_chat() -> None:
    class ContextRestoringRepository(FakeChatRepository):
        def get_latest_conversation_context(self, *, owner_id, session_id):
            assert (owner_id, session_id) == (OWNER_ID, SESSION_ID)
            return None

    class UnavailableContextRepository:
        def get(self, owner_id):
            assert owner_id == OWNER_ID
            raise psycopg.OperationalError("database unavailable")

        def get_nickname(self, owner_id):
            assert owner_id == OWNER_ID
            return None

    repository = ContextRestoringRepository()
    _override_authenticated_dependencies(repository)
    app.dependency_overrides[get_optional_demo_user_context_repository] = lambda: (
        UnavailableContextRepository()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "IRP 위험자산 한도를 알려줘",
                    "session_id": str(SESSION_ID),
                },
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert final_sse_response(response.text)["persisted"] is True


@pytest.mark.parametrize("content", ["not-json", "[]", '"legacy"', "1"])
def test_message_parser_keeps_unreadable_assistant_payload_safe(
    content: str,
) -> None:
    from backend.app.api.chat import _message_out

    message = StoredChatMessage(
        message_id=uuid4(),
        role="assistant",
        content=content,
        model_name=None,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        evidence=(),
    )

    parsed = _message_out(message)

    assert parsed.response is None
    assert parsed.question_message_id is None
    assert parsed.content == "저장된 답변 형식을 읽을 수 없습니다."
