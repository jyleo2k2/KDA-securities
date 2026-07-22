from datetime import UTC, datetime
from uuid import UUID

from backend.app.retrieval import repository as repository_module
from backend.app.retrieval.repository import NewsMatch, RetrievalRepository


class _Cursor:
    def __init__(self) -> None:
        self.statement = ""
        self.params: tuple[object, ...] = ()
        self.rows = [
            (
                "11111111-1111-4111-8111-111111111111",
                "연금 뉴스",
                "메타데이터 요약",
                "https://example.test/news/1",
                None,
                datetime(2026, 7, 16, tzinfo=UTC),
                ("요약 1", "요약 2", "요약 3"),
            )
        ]

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statement = statement
        self.params = params

    def __iter__(self):
        return iter(self.rows)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


def test_recent_market_news_is_deterministic_and_filters_active_summaries(
    monkeypatch,
) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    results = RetrievalRepository("postgresql://test").recent_market_news(
        region="us", days=5, limit=3
    )

    assert results == [NewsMatch(*cursor.rows[0])]
    assert "selection_policy_version is not null" in cursor.statement
    assert "is_active" in cursor.statement
    assert "%s::text is null" in cursor.statement
    assert "market_region = %s" in cursor.statement
    assert "summary_status = 'succeeded'" in cursor.statement
    assert "not (id = any(%s::uuid[]))" in cursor.statement
    assert "row_number() over" in cursor.statement
    assert "coalesce(market_topics, array[]::text[])" in cursor.statement
    assert "topic_match desc" in cursor.statement
    assert "selection_score desc" in cursor.statement
    assert "published_at desc" in cursor.statement
    assert "order by random()" not in cursor.statement
    assert cursor.params == ([], "us", "us", [], 5, "us", 3)


def test_recent_market_news_balances_regions_and_excludes_seen_ids(monkeypatch) -> None:
    cursor = _Cursor()
    seen_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    RetrievalRepository("postgresql://test").recent_market_news(
        region=None,
        days=5,
        limit=3,
        exclude_item_ids=(seen_id, "tampered"),
    )

    assert "partition by market_region" in cursor.statement
    assert "region_rank = 1" in cursor.statement
    assert "not (id = any(%s::uuid[]))" in cursor.statement
    assert cursor.params == ([], None, None, [seen_id], 5, None, 3)


def test_recent_market_news_prioritizes_preferred_topics(monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    RetrievalRepository("postgresql://test").recent_market_news(
        preferred_topics=("monetary_policy", "macro"),
        days=5,
        limit=3,
    )

    assert cursor.params[0] == ["monetary_policy", "macro"]
    assert "topic_match desc" in cursor.statement


def test_news_by_ids_preserves_caller_order(monkeypatch) -> None:
    cursor = _Cursor()
    first = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    base = cursor.rows[0][1:]
    cursor.rows = [(first, *base), (second, *base)]
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    results = RetrievalRepository("postgresql://test").news_by_ids((second, first))

    assert [UUID(item.item_id) for item in results] == [UUID(second), UUID(first)]
    assert "where id = any(%s::uuid[])" in cursor.statement
    assert cursor.params == ([second, first],)


def test_news_by_ids_rejects_tampered_ids_without_query(monkeypatch) -> None:
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: (_ for _ in ()).throw(AssertionError("database should not run")),
    )

    assert RetrievalRepository("postgresql://test").news_by_ids(("tampered",)) == []


def test_summarized_news_by_canonical_urls_returns_completed_matches(
    monkeypatch,
) -> None:
    cursor = _Cursor()
    canonical_url = "https://example.test/canonical/1"
    cursor.rows = [(canonical_url, *cursor.rows[0])]
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    results = RetrievalRepository(
        "postgresql://test"
    ).summarized_news_by_canonical_urls((canonical_url, canonical_url))

    assert results == {canonical_url: NewsMatch(*cursor.rows[0][1:])}
    assert "canonical_url = any(%s::text[])" in cursor.statement
    assert "summary_status = 'succeeded'" in cursor.statement
    assert "cardinality(summary_lines) = 3" in cursor.statement
    assert cursor.params == ([canonical_url],)
