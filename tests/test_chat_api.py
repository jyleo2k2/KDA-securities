import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.chat import (
    get_authenticated_chat_service,
    get_chat_repository,
    get_demo_chat_service,
    router,
)
from backend.app.auth import require_supabase_user_id
from backend.app.chat.orchestrator import (
    AnswerNarrative,
    AnswerSource,
    AnswerStatus,
    EvidenceAnswer,
)
from backend.app.chat.query_planner import QueryIntent, QueryPlan
from backend.app.chat.repository import (
    ChatSessionAccessError,
    ChatSessionSummary,
    StoredChatMessage,
    StoredMessageEvidence,
)


def _answer() -> EvidenceAnswer:
    return EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=QueryPlan(intent=QueryIntent.ACCOUNT_RULE),
        narrative=AnswerNarrative(
            facts="검증된 규칙입니다.",
            external_opinion="없음",
            service_interpretation="규칙 문서를 설명했습니다.",
            limitations="검색 청크 범위에 한정됩니다.",
        ),
        sources=(
            AnswerSource(
                title="공식 규칙",
                url="https://official.example/rule",
                document_id="119dc356-8b89-44bc-ab34-3fd6b06f553c",
                chunk_id=17,
            ),
        ),
        data_boundary="verified_knowledge",
    )


class _Service:
    def answer_question(self, question: str, **kwargs: object) -> EvidenceAnswer:
        return _answer()


class _Repository:
    def __init__(self, owner_id: UUID) -> None:
        self.owner_id = owner_id
        self.session_id = uuid4()
        self.user_message_id = uuid4()
        self.assistant_message_id = uuid4()
        self.saved_answer: EvidenceAnswer | None = None

    def save_user_question(self, **kwargs: object) -> tuple[UUID, UUID]:
        if kwargs["owner_id"] != self.owner_id:
            raise ChatSessionAccessError
        return self.session_id, self.user_message_id

    def save_assistant_answer(self, **kwargs: object) -> UUID:
        if kwargs["owner_id"] != self.owner_id:
            raise ChatSessionAccessError
        self.saved_answer = kwargs["answer"]  # type: ignore[assignment]
        return self.assistant_message_id

    def list_sessions(self, owner_id: UUID) -> list[ChatSessionSummary]:
        assert owner_id == self.owner_id
        now = datetime(2026, 7, 15, tzinfo=UTC)
        return [ChatSessionSummary(self.session_id, "규칙 질문", now, now)]

    def get_messages(
        self, *, owner_id: UUID, session_id: UUID
    ) -> list[StoredChatMessage]:
        if owner_id != self.owner_id or session_id != self.session_id:
            raise ChatSessionAccessError
        evidence = StoredMessageEvidence(
            document_id=UUID("119dc356-8b89-44bc-ab34-3fd6b06f553c"),
            chunk_id=17,
            news_item_id=None,
            source_locator="https://official.example/rule",
            quote_text="검증된 규칙입니다.",
            rank=1,
        )
        return [
            StoredChatMessage(
                message_id=self.assistant_message_id,
                role="assistant",
                content=json.dumps(
                    {
                        "question_message_id": str(self.user_message_id),
                        "answer": json.loads(_answer().model_dump_json()),
                    }
                ),
                model_name="deterministic",
                created_at=datetime(2026, 7, 15, tzinfo=UTC),
                evidence=(evidence,),
            )
        ]


def _client(owner_id: UUID, repository: _Repository) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_supabase_user_id] = lambda: owner_id
    app.dependency_overrides[get_chat_repository] = lambda: repository
    app.dependency_overrides[get_authenticated_chat_service] = lambda: _Service()
    app.dependency_overrides[get_demo_chat_service] = lambda: _Service()
    return TestClient(app)


def test_authenticated_chat_saves_question_answer_and_evidence_payload() -> None:
    owner_id = uuid4()
    repository = _Repository(owner_id)
    client = _client(owner_id, repository)

    response = client.post("/chat", json={"question": "IRP 규칙을 설명해줘"})

    assert response.status_code == 200
    assert response.json()["session_id"] == str(repository.session_id)
    assert repository.saved_answer is not None
    assert repository.saved_answer.sources[0].chunk_id == 17


def test_demo_chat_is_not_persisted() -> None:
    owner_id = uuid4()
    repository = _Repository(owner_id)
    client = _client(owner_id, repository)

    response = client.post("/chat/demo", json={"question": "IRP 규칙"})

    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert repository.saved_answer is None


def test_foreign_session_is_hidden_as_not_found() -> None:
    owner_id = uuid4()
    repository = _Repository(owner_id)
    client = _client(owner_id, repository)

    response = client.get(f"/chat/sessions/{uuid4()}/messages")

    assert response.status_code == 404


def test_reopened_message_contains_original_answer_and_evidence() -> None:
    owner_id = uuid4()
    repository = _Repository(owner_id)
    client = _client(owner_id, repository)

    response = client.get(
        f"/chat/sessions/{repository.session_id}/messages"
    )

    assert response.status_code == 200
    message = response.json()[0]
    assert message["question_message_id"] == str(repository.user_message_id)
    assert message["answer"]["sources"][0]["url"].endswith("/rule")
    assert message["evidence"][0]["chunk_id"] == 17
    assert message["evidence"][0]["source_locator"].endswith("/rule")


def test_chat_route_requires_supabase_user_dependency() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/chat", json={"question": "IRP 규칙"})

    assert response.status_code == 401


def test_chat_database_outage_returns_service_unavailable() -> None:
    owner_id = uuid4()

    class DatabaseOutageRepository(_Repository):
        def save_user_question(self, **kwargs: object) -> tuple[UUID, UUID]:
            del kwargs
            raise ConnectionError("database unavailable")

    repository = DatabaseOutageRepository(owner_id)
    client = _client(owner_id, repository)

    response = client.post("/chat", json={"question": "IRP 규칙을 알려줘"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat database is unavailable"


def test_demo_data_source_outage_returns_service_unavailable() -> None:
    class DataSourceOutageService:
        def answer_question(self, question: str, **kwargs: object) -> EvidenceAnswer:
            del question, kwargs
            raise ConnectionError("database unavailable")

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_demo_chat_service] = lambda: (
        DataSourceOutageService()
    )
    client = TestClient(app)

    response = client.post("/chat/demo", json={"question": "IRP 규칙"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat data source is unavailable"
