from datetime import UTC, datetime
from uuid import UUID

from backend.app.ingestion import naver_news_repository as repository_module
from backend.app.ingestion.embeddings import EMBEDDING_MODEL
from backend.app.ingestion.market_news_policy import SELECTION_POLICY_VERSION
from backend.app.ingestion.naver_news_repository import (
    MAX_ACTIVE_NEWS,
    NaverNewsRepository,
    ReadyMarketNews,
)


class _RotationCursor:
    def __init__(
        self,
        current_count: int,
        *,
        actual_inserted_count: int | None = None,
    ) -> None:
        self.current_count = current_count
        self.actual_inserted_count = actual_inserted_count
        self.expired_count = 0
        self.inserted_count = 0
        self.rowcount = 0
        self._next_row: tuple[object, ...] | None = None
        self.statements: list[str] = []
        self.inserted_rows: list[dict[str, object]] = []

    def __enter__(self) -> "_RotationCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: str, params: tuple[object, ...] | None = None) -> None:
        compact = " ".join(statement.split())
        self.statements.append(compact)
        self.rowcount = 1
        self._next_row = None
        if compact.startswith("select count(*) from public.news_items"):
            final_count = self.current_count - self.expired_count + self.inserted_count
            self._next_row = (final_count,)
        elif compact.startswith("with oldest as"):
            requested_count = int(params[-1]) if params else 0
            self.expired_count = min(requested_count, self.current_count)
            self.rowcount = self.expired_count

    def executemany(self, statement: str, rows: list[dict[str, object]]) -> None:
        self.statements.append(" ".join(statement.split()))
        self.inserted_rows = rows
        self.inserted_count = (
            len(rows)
            if self.actual_inserted_count is None
            else min(self.actual_inserted_count, len(rows))
        )
        self.rowcount = self.inserted_count

    def fetchone(self) -> tuple[object, ...] | None:
        return self._next_row


class _Connection:
    def __init__(self, cursor: _RotationCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        self.rolled_back = exc_type is not None

    def cursor(self) -> _RotationCursor:
        return self._cursor


def _article(index: int) -> ReadyMarketNews:
    return ReadyMarketNews(
        search_query="한국 증시",
        title=f"시장 기사 {index}",
        description="시장 반응을 공식 발표했다.",
        publisher="연합뉴스",
        original_url=f"https://www.yna.co.kr/view/{index}",
        portal_url=f"https://n.news.naver.com/{index}",
        published_at=datetime(2026, 7, 17, 12, tzinfo=UTC),
        raw_metadata={},
        market_region="kr",
        market_topics=("indices",),
        canonical_url=f"https://www.yna.co.kr/view/{index}",
        normalized_title_hash=f"{index:064x}",
        event_fingerprint=f"{index + 1000:064x}",
        selection_score=90,
        selection_reasons=("market_impact:30",),
        selection_policy_version=SELECTION_POLICY_VERSION,
        selection_embedding=tuple([0.0] * 1024),
        selection_embedding_model=EMBEDDING_MODEL,
        summary_lines=("첫째 문장", "둘째 문장", "셋째 문장"),
        summary_model="test-model",
        summary_prompt_version="test-v2",
        source_content_sha256=f"{index + 2000:064x}",
    )


def _run_rotation(
    monkeypatch,
    current_count: int,
    article_count: int,
    *,
    actual_inserted_count: int | None = None,
):
    cursor = _RotationCursor(
        current_count,
        actual_inserted_count=actual_inserted_count,
    )
    connection = _Connection(cursor)
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _, **__: connection,
    )
    result = NaverNewsRepository("postgresql://test").complete_market_run(
        run_id=UUID(int=1),
        source_id=1,
        articles=[_article(index) for index in range(article_count)],
        raw_record_count=200,
        candidate_count=40,
        selected_count=article_count,
        rejected_record_count=160,
        processing_failures={},
    )
    return result, cursor, connection


def test_repository_disables_prepared_statements_for_transaction_pooler(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def connect(database_url: str, **kwargs: object) -> object:
        captured["database_url"] = database_url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(repository_module.psycopg, "connect", connect)

    repository = NaverNewsRepository("postgresql://test")

    assert repository._connect() is sentinel
    assert captured == {
        "database_url": "postgresql://test",
        "prepare_threshold": None,
    }


def test_full_store_waits_without_deleting_for_partial_batch(monkeypatch) -> None:
    result, cursor, connection = _run_rotation(monkeypatch, MAX_ACTIVE_NEWS, 19)

    assert result.inserted_count == 0
    assert result.expired_count == 0
    assert result.final_count == MAX_ACTIVE_NEWS
    assert result.held_for_full_batch is True
    assert cursor.inserted_rows == []
    assert not any(
        statement.startswith("with oldest as") for statement in cursor.statements
    )
    assert connection.rolled_back is False


def test_full_store_atomically_expires_oldest_twenty(monkeypatch) -> None:
    result, cursor, _ = _run_rotation(monkeypatch, MAX_ACTIVE_NEWS, 20)

    assert result.inserted_count == 20
    assert result.expired_count == 20
    assert result.final_count == MAX_ACTIVE_NEWS
    assert result.held_for_full_batch is False
    assert len(cursor.inserted_rows) == 20
    assert any("set is_active = false" in statement for statement in cursor.statements)
    assert not any(
        "delete from public.news_items" in item for item in cursor.statements
    )
    assert any("pg_advisory_xact_lock" in statement for statement in cursor.statements)


def test_full_store_expires_only_rows_actually_inserted_after_conflicts(
    monkeypatch,
) -> None:
    result, cursor, _ = _run_rotation(
        monkeypatch,
        MAX_ACTIVE_NEWS,
        20,
        actual_inserted_count=7,
    )

    assert result.inserted_count == 7
    assert result.expired_count == 7
    assert result.final_count == MAX_ACTIVE_NEWS
    insert_index = next(
        index
        for index, statement in enumerate(cursor.statements)
        if statement.startswith("insert into public.news_items")
    )
    expire_index = next(
        index
        for index, statement in enumerate(cursor.statements)
        if statement.startswith("with oldest as")
    )
    assert insert_index < expire_index
    assert "ingestion_run_id is distinct from" in cursor.statements[expire_index]


def test_full_store_does_not_expire_when_every_insert_conflicts(monkeypatch) -> None:
    result, cursor, _ = _run_rotation(
        monkeypatch,
        MAX_ACTIVE_NEWS,
        20,
        actual_inserted_count=0,
    )

    assert result.inserted_count == 0
    assert result.expired_count == 0
    assert result.final_count == MAX_ACTIVE_NEWS
    assert not any(
        statement.startswith("with oldest as") for statement in cursor.statements
    )


def test_store_below_cap_inserts_only_available_capacity(monkeypatch) -> None:
    result, cursor, _ = _run_rotation(monkeypatch, MAX_ACTIVE_NEWS - 10, 20)

    assert result.inserted_count == 10
    assert result.expired_count == 0
    assert result.final_count == MAX_ACTIVE_NEWS
    assert len(cursor.inserted_rows) == 10


def test_store_below_cap_keeps_existing_rows_when_inserts_conflict(monkeypatch) -> None:
    result, cursor, _ = _run_rotation(
        monkeypatch,
        MAX_ACTIVE_NEWS - 10,
        20,
        actual_inserted_count=4,
    )

    assert result.inserted_count == 4
    assert result.expired_count == 0
    assert result.final_count == MAX_ACTIVE_NEWS - 6
    assert not any(
        statement.startswith("with oldest as") for statement in cursor.statements
    )
