import httpx
import pytest

from backend.app.ingestion.naver_news import (
    NaverNewsApiError,
    fetch_naver_news,
)


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
    assert not hasattr(item, "article_body")
    assert set(item.raw_metadata) <= {
        "title",
        "originallink",
        "link",
        "description",
        "pubDate",
    }


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


def test_naver_news_partial_response_rejects_missing_metadata() -> None:
    payload = {
        "total": 2,
        "start": 1,
        "display": 2,
        "items": [
            {
                "title": "정상 기사",
                "originallink": "https://publisher.example/1",
                "link": "https://n.news.naver.com/1",
                "description": "요약",
                "pubDate": "Tue, 14 Jul 2026 10:00:00 +0900",
                "article_body": "저장하면 안 되는 기사 전문",
            },
            {"title": "발행일 없는 기사", "originallink": "https://example.test/2"},
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

    assert len(response.items) == 1
    assert response.rejected_count == 1
    assert response.rejected_reasons == ("item[1]: missing_required_metadata",)
    assert "article_body" not in response.items[0].raw_metadata
