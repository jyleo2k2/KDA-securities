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


def test_random_recent_market_news_filters_selected_us_summaries(monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(
        repository_module.psycopg,
        "connect",
        lambda _: _Connection(cursor),
    )

    results = RetrievalRepository("postgresql://test").random_recent_market_news(
        region="us", days=5, limit=3
    )

    assert results == [NewsMatch(*cursor.rows[0])]
    assert "selection_policy_version is not null" in cursor.statement
    assert "%s::text is null" in cursor.statement
    assert "market_region = %s" in cursor.statement
    assert "summary_status = 'succeeded'" in cursor.statement
    assert "order by random()" in cursor.statement
    assert cursor.params == ("us", "us", 5, 3)
