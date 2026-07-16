import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import (
    get_chat_narrator,
    get_chat_repository,
    get_chat_service,
    get_optional_chat_repository,
)
from backend.app.auth import require_supabase_user_id
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatRequest
from backend.app.chat.repository import (
    ChatSessionAccessError,
    ChatSessionSummary,
    SavedChatExchange,
    StoredChatMessage,
)
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.main import app

OWNER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER_MESSAGE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ASSISTANT_MESSAGE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
CHAT_HEADERS = {"Idempotency-Key": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"}


class FakeChatRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_exchange(self, **kwargs) -> SavedChatExchange:
        self.saved.append(kwargs)
        return SavedChatExchange(
            session_id=SESSION_ID,
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
        )

    def find_idempotent_exchange(self, **kwargs) -> SavedChatExchange | None:
        return None

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
                "/chat",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["persisted"] is True
    assert payload["session_id"] == str(SESSION_ID)
    assert payload["response"]["intent"] == "account_rule"
    assert len(repository.saved) == 1
    assert repository.saved[0]["owner_id"] == OWNER_ID
    assert repository.saved[0]["idempotency_key"] == UUID(
        CHAT_HEADERS["Idempotency-Key"]
    )


def test_authenticated_pension_tax_keeps_context_and_idempotency() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
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
    payload = response.json()
    assert payload["persisted"] is True
    assert payload["response"]["intent"] == "pension_tax"
    assert payload["response"]["pension_tax_result"]["tax_credit"] is not None
    assert payload["response"]["conversation_context"]["account_type"] == "irp"
    assert repository.saved[0]["idempotency_key"] == UUID(
        CHAT_HEADERS["Idempotency-Key"]
    )


def test_sensitive_query_is_not_persisted_or_echoed() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
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
    payload = response.json()
    assert payload["persisted"] is False
    assert payload["session_id"] is None
    assert "900101" not in response.text
    assert repository.saved == []


def test_blocked_query_works_without_chat_database() -> None:
    _override_authenticated_dependencies(None)
    try:
        with TestClient(app) as client:
            blocked = client.post(
                "/chat",
                json={"message": "이 상품을 대신 매수해줘"},
                headers=CHAT_HEADERS,
            )
            supported = client.post(
                "/chat",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert blocked.status_code == 200
    assert blocked.json()["persisted"] is False
    assert supported.status_code == 503


def test_chat_requires_bearer_authentication() -> None:
    repository = FakeChatRepository()
    app.dependency_overrides[get_chat_service] = _service
    app.dependency_overrides[get_chat_narrator] = lambda: None
    app.dependency_overrides[get_optional_chat_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


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


class ForeignSessionRepository(FakeChatRepository):
    def get_messages(self, *, owner_id: UUID, session_id: UUID):
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


class UnavailableRepository(FakeChatRepository):
    def save_exchange(self, **kwargs) -> SavedChatExchange:
        raise psycopg.OperationalError("database unavailable")


def test_database_failure_is_distinct_from_auth_failure() -> None:
    _override_authenticated_dependencies(UnavailableRepository())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat database is unavailable"


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
                "/chat",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat data source is unavailable"
    assert repository.saved == []


def test_authenticated_chat_requires_a_uuid_idempotency_key() -> None:
    repository = FakeChatRepository()
    _override_authenticated_dependencies(repository)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat", json={"message": "IRP 위험자산 한도를 알려줘"}
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
                "/chat",
                json={"message": "IRP 위험자산 한도를 알려줘"},
                headers=CHAT_HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["idempotency_replayed"] is True
    assert repository.saved == []


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
