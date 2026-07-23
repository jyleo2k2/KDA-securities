import json
import threading
from datetime import UTC, datetime
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
        response = _service().ask(
            ChatRequest(message="IRP 위험자산 한도를 알려줘")
        )
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
    assert "대화 기록을 저장하고 있습니다." in response.text
    assert '"persisted": true' in response.text
    assert len(repository.saved) == 1


def test_authenticated_chat_stream_does_not_persist_sensitive_query() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": "주민등록번호 900101-1234567로 IRP를 확인해줘"
                },
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
    app.dependency_overrides[get_optional_demo_user_context_repository] = (
        lambda: NicknameRepository()
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
        "소득금액",
        "확인된 소득구간 표시율",
        "연금저축 당해연도 납입액",
        "IRP 당해연도 납입액",
        "합산 세액공제 대상 납입액",
        "확인된 소득구간 지방세 포함 예상 절세효과",
    ]


def test_sensitive_query_is_not_persisted_or_echoed() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/stream",
                json={
                    "message": (
                        "주민등록번호 900101-1234567로 IRP를 확인해줘"
                    )
                },
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
        ("phase", {"message": "요청을 확인하고 있습니다."}),
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
    assert repository.deleted == [
        {"owner_id": OWNER_ID, "session_id": SESSION_ID}
    ]


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
    app.dependency_overrides[get_optional_demo_user_context_repository] = (
        lambda: ParallelContextRepository()
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
    app.dependency_overrides[get_optional_demo_user_context_repository] = (
        lambda: UnavailableContextRepository()
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
