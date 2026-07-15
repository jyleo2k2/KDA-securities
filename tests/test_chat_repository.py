import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.app.chat import repository as repository_module
from backend.app.chat.models import (
    ChatIntent,
    ChatResponse,
    DataBoundary,
    SourceEvidence,
)
from backend.app.chat.repository import ChatRepository, ChatSessionAccessError


class FakeCursor:
    def __init__(self, fetchone_rows, *, fail_on_assistant: bool = False) -> None:
        self._fetchone_rows = list(fetchone_rows)
        self.fail_on_assistant = fail_on_assistant
        self.executed: list[tuple[str, object]] = []
        self.many: list[tuple[str, list[dict[str, object]]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None) -> None:
        normalized = " ".join(query.split())
        self.executed.append((normalized, params))
        if self.fail_on_assistant and "'assistant'" in normalized:
            raise repository_module.psycopg.OperationalError("write failed")

    def executemany(self, query, params) -> None:
        self.many.append((" ".join(query.split()), list(params)))

    def fetchone(self):
        return self._fetchone_rows.pop(0) if self._fetchone_rows else None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.exit_exception = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.exit_exception = exc_type
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor


def _response() -> ChatResponse:
    news_id = uuid4()
    return ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer="검증된 계좌 규칙 답변입니다.",
        data_mode="verified_knowledge",
        model_name="claude-test",
        sources=[
            SourceEvidence(
                evidence_id="knowledge:42",
                label="공식 지식",
                locator="https://example.test/knowledge",
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            ),
            SourceEvidence(
                evidence_id=f"news:{news_id}",
                label="뉴스",
                locator="https://example.test/news",
                data_boundary=DataBoundary.NEWS_METADATA,
            ),
            SourceEvidence(
                evidence_id="engine:risk_cap",
                label="규칙 엔진",
                locator="engine://risk-cap",
                data_boundary=DataBoundary.ENGINE,
            ),
        ],
    )


def test_message_order_keeps_same_timestamp_exchanges_together() -> None:
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)
    first_user_id = UUID("00000000-0000-4000-8000-000000000001")
    second_user_id = UUID("00000000-0000-4000-8000-000000000002")
    first_assistant_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    second_assistant_id = UUID("00000000-0000-4000-8000-000000000000")

    def assistant_content(question_id: UUID) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "question_message_id": str(question_id),
                "response": {},
            }
        )

    rows = [
        (
            second_assistant_id,
            "assistant",
            assistant_content(second_user_id),
            None,
            timestamp,
        ),
        (second_user_id, "user", "second", None, timestamp),
        (
            first_assistant_id,
            "assistant",
            assistant_content(first_user_id),
            None,
            timestamp,
        ),
        (first_user_id, "user", "first", None, timestamp),
    ]

    ordered = repository_module._order_message_rows(rows)

    assert [row[0] for row in ordered] == [
        first_user_id,
        first_assistant_id,
        second_user_id,
        second_assistant_id,
    ]
    assert [row[1] for row in ordered] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_save_exchange_is_one_transaction_with_relational_evidence(
    monkeypatch,
) -> None:
    session_id, user_message_id, assistant_message_id = (
        uuid4(),
        uuid4(),
        uuid4(),
    )
    cursor = FakeCursor(
        [(session_id,), (user_message_id,), (assistant_message_id,)]
    )
    connection = FakeConnection(cursor)
    connection_calls: list[str] = []

    def connect(database_url: str) -> FakeConnection:
        connection_calls.append(database_url)
        return connection

    monkeypatch.setattr(repository_module.psycopg, "connect", connect)

    saved = ChatRepository("postgresql://test").save_exchange(
        owner_id=uuid4(),
        question="IRP 규칙을 알려줘",
        response=_response(),
    )

    assert connection_calls == ["postgresql://test"]
    assert saved.session_id == session_id
    assert saved.user_message_id == user_message_id
    assert saved.assistant_message_id == assistant_message_id
    assistant_params = next(
        params
        for query, params in cursor.executed
        if "'assistant'" in query
    )
    payload = json.loads(assistant_params[1])
    assert payload["schema_version"] == 1
    assert payload["question_message_id"] == str(user_message_id)
    assert payload["response"]["answer"] == "검증된 계좌 규칙 답변입니다."
    assert assistant_params[2] == "claude-test"
    assert len(cursor.many) == 1
    evidence_rows = cursor.many[0][1]
    assert len(evidence_rows) == 2
    assert evidence_rows[0]["chunk_id"] == 42
    assert evidence_rows[0]["quote_text"] is None
    assert evidence_rows[1]["news_item_id"] is not None
    assert all(row["document_id"] is None for row in evidence_rows)


def test_existing_session_is_locked_with_owner_id(monkeypatch) -> None:
    session_id = uuid4()
    owner_id = uuid4()
    cursor = FakeCursor([(1,), (uuid4(),), (uuid4(),)])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda database_url: connection,
    )

    ChatRepository("postgresql://test").save_exchange(
        owner_id=owner_id,
        session_id=session_id,
        question="IRP 규칙",
        response=_response(),
    )

    lock_query, lock_params = cursor.executed[0]
    assert "for update" in lock_query
    assert lock_params == (session_id, owner_id)


def test_foreign_session_fails_before_message_insert(monkeypatch) -> None:
    cursor = FakeCursor([None])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda database_url: connection,
    )

    with pytest.raises(ChatSessionAccessError):
        ChatRepository("postgresql://test").save_exchange(
            owner_id=uuid4(),
            session_id=uuid4(),
            question="IRP 규칙",
            response=_response(),
        )

    assert len(cursor.executed) == 1
    assert "for update" in cursor.executed[0][0]


def test_assistant_failure_rolls_back_the_same_connection(monkeypatch) -> None:
    cursor = FakeCursor(
        [(uuid4(),), (uuid4(),)], fail_on_assistant=True
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda database_url: connection,
    )

    with pytest.raises(repository_module.psycopg.OperationalError):
        ChatRepository("postgresql://test").save_exchange(
            owner_id=uuid4(),
            question="IRP 규칙",
            response=_response(),
        )

    assert connection.exit_exception is repository_module.psycopg.OperationalError
    assert any("'user'" in query for query, _ in cursor.executed)
    assert any("'assistant'" in query for query, _ in cursor.executed)
