from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from backend.app.ingestion import naver_market_news
from backend.app.ingestion.market_news_policy import MARKET_QUERIES
from backend.app.ingestion.naver_news import NaverNewsItem, NaverNewsResponse
from backend.app.ingestion.naver_news_repository import MarketNewsRotationResult
from backend.app.ingestion.news_summarizer import NewsSummaryOutput


def test_market_news_pipeline_commits_only_selected_completed_summary(
    monkeypatch,
) -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    item = NaverNewsItem(
        title="한국은행 기준금리 발표에 코스피 2% 하락",
        description=("한국은행이 기준금리를 발표했고 코스피는 2% 하락했다고 집계했다."),
        original_url="https://www.yna.co.kr/view/AKR1",
        portal_url="https://n.news.naver.com/mnews/article/001/1",
        published_at=now - timedelta(hours=1),
        raw_metadata={"title": "시장 기사"},
    )

    class Repository:
        def __init__(self) -> None:
            self.completed = []

        def start_market_run(self, *, queries, **_):
            assert queries == (MARKET_QUERIES[0].query,)
            return UUID(int=1), 1

        def load_market_identities(self):
            return []

        def complete_market_run(self, **kwargs):
            self.completed = kwargs["articles"]
            return MarketNewsRotationResult(1, 0, 1, False)

        def fail_run(self, *_):
            raise AssertionError("failure path must not run")

    class Embedder:
        def embed(self, texts):
            assert len(texts) == 1
            vector = [0.0] * 1024
            vector[0] = 1.0
            return [vector]

    class Summarizer:
        def __init__(self, **_):
            pass

        def summarize(self, **_):
            return NewsSummaryOutput(
                summary_lines=("첫째 문장", "둘째 문장", "셋째 문장")
            )

    repository = Repository()
    monkeypatch.setattr(naver_market_news, "MARKET_QUERIES", (MARKET_QUERIES[0],))
    monkeypatch.setattr(naver_market_news, "NaverNewsRepository", lambda _: repository)
    monkeypatch.setattr(
        naver_market_news,
        "fetch_naver_news",
        lambda *_, **__: NaverNewsResponse(1, 1, 1, 1, [item], ()),
    )
    monkeypatch.setattr(naver_market_news, "get_query_embedder", lambda: Embedder())
    monkeypatch.setattr(
        naver_market_news,
        "fetch_news_article",
        lambda *_: SimpleNamespace(text="시장 기사 원문", content_sha256="a" * 64),
    )
    monkeypatch.setattr(naver_market_news, "NewsSummarizer", Summarizer)

    result = naver_market_news.run_market_news_ingestion(
        client_id="id",
        client_secret="secret",
        database_url="postgresql://test",
        api_key="anthropic",
        model="test-model",
        prompt_version="test-v2",
        now=now,
    )

    assert result["outcome"] == "succeeded"
    assert result["selected"] == 1
    assert result["summarized"] == 1
    assert result["inserted"] == 1
    assert len(repository.completed) == 1
    assert repository.completed[0].summary_lines == (
        "첫째 문장",
        "둘째 문장",
        "셋째 문장",
    )


def test_market_news_pipeline_backfills_only_the_requested_day(monkeypatch) -> None:
    window_end = datetime(2026, 7, 14, tzinfo=UTC)
    window_start = window_end - timedelta(days=1)
    target = NaverNewsItem(
        title="한국은행 기준금리 발표에 코스피 2% 하락",
        description="한국은행 기준금리 발표 뒤 코스피가 2% 하락했다고 집계했다.",
        original_url="https://www.yna.co.kr/view/AKR2",
        portal_url="https://n.news.naver.com/mnews/article/001/2",
        published_at=window_end - timedelta(hours=1),
        raw_metadata={"title": "과거 시장 기사"},
    )
    newer = NaverNewsItem(
        title="한국은행 기준금리 발표에 코스피 2% 하락",
        description="한국은행 기준금리 발표 뒤 코스피가 2% 하락했다고 집계했다.",
        original_url="https://www.yna.co.kr/view/AKR3",
        portal_url="https://n.news.naver.com/mnews/article/001/3",
        published_at=window_end + timedelta(days=7),
        raw_metadata={"title": "새 시장 기사"},
    )

    class Repository:
        def start_market_run(self, **_):
            return UUID(int=2), 1

        def load_market_identities(self):
            return []

        def complete_market_run(self, **kwargs):
            self.articles = kwargs["articles"]
            return MarketNewsRotationResult(1, 0, 1, False)

        def fail_run(self, *_):
            raise AssertionError("failure path must not run")

    class Embedder:
        def embed(self, texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

    class Summarizer:
        def __init__(self, **_):
            pass

        def summarize(self, **_):
            return NewsSummaryOutput(summary_lines=("첫째", "둘째", "셋째"))

    repository = Repository()
    calls: list[int] = []

    def fetch(*_, start, **__):
        calls.append(start)
        item = newer if start == 1 else target
        return NaverNewsResponse(100, start, 50, 50, [item] * 50, ())

    monkeypatch.setattr(naver_market_news, "MARKET_QUERIES", (MARKET_QUERIES[0],))
    monkeypatch.setattr(naver_market_news, "NaverNewsRepository", lambda _: repository)
    monkeypatch.setattr(naver_market_news, "fetch_naver_news", fetch)
    monkeypatch.setattr(naver_market_news, "get_query_embedder", lambda: Embedder())
    monkeypatch.setattr(
        naver_market_news,
        "fetch_news_article",
        lambda *_: SimpleNamespace(text="시장 기사 원문", content_sha256="b" * 64),
    )
    monkeypatch.setattr(naver_market_news, "NewsSummarizer", Summarizer)

    result = naver_market_news.run_market_news_ingestion(
        client_id="id",
        client_secret="secret",
        database_url="postgresql://test",
        api_key="anthropic",
        model="test-model",
        prompt_version="test-v2",
        now=window_end,
        window_start=window_start,
        max_pages=2,
    )

    assert calls == [1, 51]
    assert result["outcome"] == "succeeded"
    assert result["selected"] == 1
    assert len(repository.articles) == 1
    assert repository.articles[0].published_at == target.published_at
