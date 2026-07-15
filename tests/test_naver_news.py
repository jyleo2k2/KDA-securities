import unicodedata
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from backend.app.ingestion import naver as naver_ingestion
from backend.app.ingestion.naver_news import (
    NaverNewsApiError,
    NaverNewsItem,
    NaverNewsResponse,
    fetch_naver_news,
)
from backend.app.text_normalization import normalize_search_text


def _client(payload: dict[str, object], status_code: int = 200) -> httpx.Client:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_naver_news_normalizes_metadata_without_article_body() -> None:
    payload = {
        "total": 1,
        "start": 1,
        "display": 1,
        "items": [
            {
                "title": "<b>연금</b> 시장 소식",
                "originallink": "https://publisher.example/article/1",
                "link": "https://n.news.naver.com/article/1",
                "description": "&quot;연금&quot; 관련 요약",
                "pubDate": "Tue, 14 Jul 2026 10:00:00 +0900",
                "articleBody": "저장하면 안 되는 기사 본문",
            }
        ],
    }
    with _client(payload) as client:
        response = fetch_naver_news(
            client,
            client_id="id",
            client_secret="secret",
            query="연금",
            display=1,
        )

    item = response.items[0]
    assert item.title == "연금 시장 소식"
    assert item.description == '"연금" 관련 요약'
    assert item.original_url == "https://publisher.example/article/1"
    assert item.published_at is not None
    assert set(item.raw_metadata) == {
        "title",
        "originallink",
        "link",
        "description",
        "pubDate",
    }
    assert item.raw_metadata["title"] == "연금 시장 소식"
    assert not hasattr(item, "article_body")


def test_naver_news_error_does_not_echo_credentials() -> None:
    with (
        _client({}, status_code=401) as client,
        pytest.raises(NaverNewsApiError) as error,
    ):
        fetch_naver_news(
            client,
            client_id="never-print-id",
            client_secret="never-print-secret",
            query="연금",
        )

    assert "never-print-id" not in str(error.value)
    assert "never-print-secret" not in str(error.value)


def test_naver_news_keeps_valid_rows_and_reports_rejections() -> None:
    payload = {
        "total": 2,
        "start": 1,
        "display": 2,
        "items": [
            {
                "title": "<b>정상</b> 기사",
                "originallink": "https://publisher.example/valid",
                "link": "https://n.news.naver.com/valid",
                "description": "<i>요약</i>",
                "pubDate": "Tue, 14 Jul 2026 10:00:00 +0900",
            },
            {
                "title": "날짜 없는 기사",
                "link": "https://n.news.naver.com/invalid",
                "pubDate": "not-a-date",
            },
        ],
    }

    with _client(payload) as client:
        response = fetch_naver_news(
            client,
            client_id="id",
            client_secret="secret",
            query="연금",
            display=2,
        )

    assert response.raw_item_count == 2
    assert len(response.items) == 1
    assert response.rejected_count == 1
    assert response.rejected_reasons == ("invalid_pub_date",)
    assert response.outcome == "partial"
    assert response.items[0].description == "요약"


def test_naver_news_rejects_response_when_all_items_are_invalid() -> None:
    payload = {
        "total": 2,
        "start": 1,
        "display": 2,
        "items": [
            {"title": "URL 없음", "pubDate": "Tue, 14 Jul 2026 10:00:00 +0900"},
            {
                "title": "날짜 없음",
                "link": "https://n.news.naver.com/2",
            },
        ],
    }

    with (
        _client(payload) as client,
        pytest.raises(NaverNewsApiError, match="no valid items") as error,
    ):
        fetch_naver_news(
            client,
            client_id="id",
            client_secret="secret",
            query="연금",
            display=2,
        )

    assert "missing_url" in str(error.value)
    assert "invalid_pub_date" in str(error.value)


def test_naver_news_normalizes_query_before_api_request() -> None:
    captured_query = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_query
        captured_query = request.url.params["query"]
        return httpx.Response(
            200,
            json={"total": 0, "start": 1, "display": 0, "items": []},
        )

    decomposed_query = unicodedata.normalize("NFD", "삼성전자")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetch_naver_news(
            client,
            client_id="id",
            client_secret="secret",
            query=f"  {decomposed_query}\n  최신   뉴스  ",
        )

    assert captured_query == "삼성전자 최신 뉴스"
    assert normalize_search_text("  연금\t 뉴스 ") == "연금 뉴스"


def test_naver_ingestion_uses_one_canonical_query_for_api_and_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_queries: list[str] = []
    run_id = UUID("00000000-0000-0000-0000-000000000001")

    class FakeRepository:
        def __init__(self, _: str) -> None:
            pass

        def start_run(self, *, query: str, **_: object) -> tuple[UUID, int]:
            observed_queries.append(query)
            return run_id, 1

        def complete_run(self, *, query: str, **_: object) -> int:
            observed_queries.append(query)
            return 1

        def fail_run(self, _: UUID, __: Exception) -> None:
            raise AssertionError("failure path must not run")

    def fake_fetch(*_: object, query: str, **__: object) -> NaverNewsResponse:
        observed_queries.append(query)
        item = NaverNewsItem(
            title="기사",
            description=None,
            original_url="https://publisher.example/1",
            portal_url=None,
            published_at=datetime.fromisoformat("2026-07-14T10:00:00+09:00"),
            raw_metadata={},
        )
        return NaverNewsResponse(1, 1, 1, 1, [item], ())

    monkeypatch.setattr(naver_ingestion, "NaverNewsRepository", FakeRepository)
    monkeypatch.setattr(naver_ingestion, "fetch_naver_news", fake_fetch)

    result = naver_ingestion.run_live_ingestion(
        client_id="not-logged",
        client_secret="not-logged",
        database_url="postgresql://example.invalid/db",
        fetch_only=False,
        query="  연금\n  최신   뉴스 ",
        display=1,
        start=1,
        sort="date",
    )

    assert observed_queries == ["연금 최신 뉴스"] * 3
    assert result["query"] == "연금 최신 뉴스"
    assert result["outcome"] == "succeeded"


@pytest.mark.parametrize(
    ("outcome", "exit_code"),
    [("succeeded", 0), ("partial", 1), ("failed", 1)],
)
def test_naver_cli_exit_code_reflects_full_success_only(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    exit_code: int,
) -> None:
    args = SimpleNamespace(
        query="연금",
        display=1,
        start=1,
        sort="date",
        fetch_only=True,
    )
    settings = SimpleNamespace(
        naver_api_hub_client_id=SecretStr("not-logged"),
        naver_api_hub_client_secret=SecretStr("not-logged"),
        database_url=None,
    )
    monkeypatch.setattr(
        naver_ingestion,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda: args),
    )
    monkeypatch.setattr(naver_ingestion, "get_settings", lambda: settings)
    monkeypatch.setattr(
        naver_ingestion,
        "run_live_ingestion",
        lambda **_: {"outcome": outcome},
    )

    assert naver_ingestion.main() == exit_code
