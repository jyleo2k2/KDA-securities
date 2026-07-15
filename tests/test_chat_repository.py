from uuid import UUID, uuid4

import pytest

from backend.app.chat import repository as repository_module
from backend.app.chat.orchestrator import (
    AnswerNarrative,
    AnswerSource,
    AnswerStatus,
    EvidenceAnswer,
)
from backend.app.chat.query_planner import QueryIntent, QueryPlan
from backend.app.chat.repository import ChatRepository, ChatSessionAccessError


def _answer() -> EvidenceAnswer:
    return EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=QueryPlan(intent=QueryIntent.ACCOUNT_RULE),
        narrative=AnswerNarrative(
            facts="근거 문장",
            external_opinion="없음",
            service_interpretation="문서 검색 결과",
            limitations="청크 범위 한정",
        ),
        sources=(
            AnswerSource(
                title="공식 문서",
                url="https://official.example/doc",
                document_id="119dc356-8b89-44bc-ab34-3fd6b06f553c",
                chunk_id=42,
            ),
        ),
        data_boundary="verified_knowledge",
    )


def test_evidence_rows_link_assistant_to_document_chunk_and_source() -> None:
    message_id = uuid4()

    rows = ChatRepository._evidence_rows(message_id, _answer())

    assert rows == [
        {
            "message_id": message_id,
            "document_id": UUID("119dc356-8b89-44bc-ab34-3fd6b06f553c"),
            "chunk_id": 42,
            "news_item_id": None,
            "source_locator": "https://official.example/doc",
            "quote_text": "근거 문장",
            "rank": 1,
        }
    ]


def test_owner_check_uses_session_and_owner_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Cursor:
        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self) -> None:
            return None

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor()

    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda database_url: Connection(),
    )
    repository = ChatRepository("postgresql://test/database")
    owner_id = uuid4()
    session_id = uuid4()

    with pytest.raises(ChatSessionAccessError):
        repository.get_messages(owner_id=owner_id, session_id=session_id)

    assert "id = %s and owner_id = %s" in str(captured["sql"])
    assert captured["params"] == (session_id, owner_id)


def test_evidence_failure_rolls_back_assistant_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assistant_message_id = uuid4()
    user_message_id = uuid4()
    captured: dict[str, object] = {}

    class Cursor:
        execute_count = 0

        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            self.execute_count += 1
            if self.execute_count == 2:
                captured["assistant_params"] = params

        def fetchone(self) -> tuple[object, ...]:
            if self.execute_count == 1:
                return (1,)
            return (assistant_message_id,)

        def executemany(self, sql: str, params: list[dict[str, object]]) -> None:
            raise RuntimeError("evidence insert failed")

    class Connection:
        rolled_back = False

        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def __enter__(self) -> "Connection":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: object,
        ) -> None:
            self.rolled_back = exc_type is not None

        def cursor(self) -> Cursor:
            return self.cursor_instance

    connection = Connection()
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda database_url: connection,
    )
    repository = ChatRepository("postgresql://test/database")

    with pytest.raises(RuntimeError, match="evidence insert failed"):
        repository.save_assistant_answer(
            owner_id=uuid4(),
            session_id=uuid4(),
            user_message_id=user_message_id,
            answer=_answer(),
            model_name="deterministic",
        )

    assert connection.rolled_back is True
    assert str(user_message_id) in str(captured["assistant_params"])
