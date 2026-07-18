from datetime import UTC, datetime

from backend.app.retrieval import repository as repository_module
from backend.app.retrieval.repository import NewsMatch, RetrievalRepository


class _Cursor:
    def __init__(self) -> None:
        self.statement = ""
        self.params: tuple[object, ...] = ()
        self.rows = [
            (
                "news-1",
                "연금 뉴스",
                "연합뉴스",
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


def test_random_recent_news_filters_five_days_and_future_rows(monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    results = RetrievalRepository("postgresql://test").random_recent_news(
        "연금", days=5, limit=3
    )

    assert results == [NewsMatch(*cursor.rows[0])]
    assert "published_at >= now() - make_interval(days => %s)" in cursor.statement
    assert "published_at <= now()" in cursor.statement
    assert "summary_status = 'succeeded'" in cursor.statement
    assert "cardinality(summary_lines) = 3" in cursor.statement
    assert "order by random()" in cursor.statement
    assert cursor.params == ("연금", 5, 3)


def test_recent_market_news_is_deterministic_for_one_region(monkeypatch) -> None:
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
    assert "selection_score desc" in cursor.statement
    assert "order by random()" not in cursor.statement
    assert cursor.params == ("us", "us", [], 5, "us", 3)


def test_recent_market_news_balances_regions_and_excludes_seen_ids(monkeypatch) -> None:
    cursor = _Cursor()
    seen_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    RetrievalRepository("postgresql://test").recent_market_news(
        region=None, days=5, limit=3, exclude_item_ids=(seen_id,)
    )

    assert "partition by market_region" in cursor.statement
    assert "region_rank = 1" in cursor.statement
    assert "not (id = any(%s::uuid[]))" in cursor.statement
    assert cursor.params == (None, None, [seen_id], 5, None, 3)


def test_news_by_ids_uses_only_valid_requested_ids(monkeypatch) -> None:
    cursor = _Cursor()
    item_id = "11111111-1111-4111-8111-111111111111"
    cursor.rows = [(item_id, *cursor.rows[0][1:])]
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    results = RetrievalRepository("postgresql://test").news_by_ids((item_id,))

    assert [item.item_id for item in results] == [item_id]
    assert "where id = any(%s::uuid[])" in cursor.statement
    assert cursor.params == ([item_id],)


def test_news_by_ids_rejects_tampered_non_uuid_without_query(monkeypatch) -> None:
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: (_ for _ in ()).throw(AssertionError("database should not run")),
    )

    assert RetrievalRepository("postgresql://test").news_by_ids(("not-a-uuid",)) == []
