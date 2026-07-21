from types import SimpleNamespace
from uuid import UUID

from backend.app.ingestion import resummarize_market_news
from backend.app.ingestion.naver_news_repository import ActiveMarketNewsSummary
from backend.app.ingestion.news_article import NewsArticleFetchError
from backend.app.ingestion.news_summarizer import NewsSummaryError, NewsSummaryOutput


def _items() -> list[ActiveMarketNewsSummary]:
    return [
        ActiveMarketNewsSummary(UUID(int=1), "첫 기사", "https://example.test/1"),
        ActiveMarketNewsSummary(UUID(int=2), "둘째 기사", "https://example.test/2"),
    ]


def test_resummary_dry_run_prepares_every_active_item(monkeypatch) -> None:
    class Repository:
        def load_active_market_news_summaries(self):
            return _items()

        def replace_active_market_news_summaries(self, **_):
            raise AssertionError("dry run must not update the database")

    class Summarizer:
        def __init__(self, **_):
            pass

        def summarize(self, **_):
            return NewsSummaryOutput(
                summary_lines=(
                    "핵심 사건이 발생했다.",
                    "수치가 확인됐다.",
                    "영향을 확인해야 한다.",
                )
            )

    monkeypatch.setattr(
        resummarize_market_news, "NaverNewsRepository", lambda _: Repository()
    )
    monkeypatch.setattr(resummarize_market_news, "NewsSummarizer", Summarizer)
    monkeypatch.setattr(
        resummarize_market_news,
        "fetch_news_article",
        lambda *_: SimpleNamespace(text="기사 원문", content_sha256="a" * 64),
    )

    result = resummarize_market_news.run_market_news_resummary(
        database_url="postgresql://test",
        api_key="test-key",
        model="test-model",
        prompt_version="news-summary-v3",
        expected_count=2,
        dry_run=True,
    )

    assert result["outcome"] == "ready"
    assert result["prepared"] == 2
    assert result["updated"] == 0


def test_resummary_does_not_update_when_any_active_item_fails(monkeypatch) -> None:
    class Repository:
        def load_active_market_news_summaries(self):
            return _items()

        def replace_active_market_news_summaries(self, **_):
            raise AssertionError("partial preparation must not update the database")

    class Summarizer:
        def __init__(self, **_):
            pass

        def summarize(self, **_):
            raise NewsSummaryError("validation_failed")

    monkeypatch.setattr(
        resummarize_market_news, "NaverNewsRepository", lambda _: Repository()
    )
    monkeypatch.setattr(resummarize_market_news, "NewsSummarizer", Summarizer)
    monkeypatch.setattr(
        resummarize_market_news,
        "fetch_news_article",
        lambda *_: (_ for _ in ()).throw(NewsArticleFetchError("article_too_short")),
    )

    result = resummarize_market_news.run_market_news_resummary(
        database_url="postgresql://test",
        api_key="test-key",
        model="test-model",
        prompt_version="news-summary-v3",
        expected_count=2,
    )

    assert result["outcome"] == "failed"
    assert result["prepared"] == 0
    assert result["updated"] == 0
    assert result["failures"] == {"article_too_short": 2}


def test_resummary_keeps_prepared_items_and_deletes_failed_items(monkeypatch) -> None:
    class Repository:
        def load_active_market_news_summaries(self):
            return _items()

        def replace_prepared_market_news_summaries_and_delete_failed(self, **kwargs):
            assert len(kwargs["summaries"]) == 1
            assert kwargs["expected_count"] == 2
            return 1, 1

    class Summarizer:
        def __init__(self, **_):
            pass

        def summarize(self, *, title, **_):
            if title == "둘째 기사":
                raise NewsSummaryError("validation_failed")
            return NewsSummaryOutput(
                summary_lines=(
                    "핵심 사건이 발생했다.",
                    "수치가 확인됐다.",
                    "영향을 확인해야 한다.",
                )
            )

    monkeypatch.setattr(
        resummarize_market_news, "NaverNewsRepository", lambda _: Repository()
    )
    monkeypatch.setattr(resummarize_market_news, "NewsSummarizer", Summarizer)
    monkeypatch.setattr(
        resummarize_market_news,
        "fetch_news_article",
        lambda *_: SimpleNamespace(text="기사 원문", content_sha256="a" * 64),
    )

    result = resummarize_market_news.run_market_news_resummary(
        database_url="postgresql://test",
        api_key="test-key",
        model="test-model",
        prompt_version="news-summary-v3",
        expected_count=2,
        concurrency=1,
        delete_failed=True,
    )

    assert result["outcome"] == "succeeded"
    assert result["updated"] == 1
    assert result["deleted"] == 1
