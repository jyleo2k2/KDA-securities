import unicodedata
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from backend.app.ingestion import naver as naver_ingestion
from backend.app.ingestion import naver_news_repository as naver_repository_module
from backend.app.ingestion.naver_news import (
    NaverNewsAllItemsRejectedError,
    NaverNewsApiError,
    NaverNewsItem,
    NaverNewsResponse,
    fetch_naver_news,
)
from backend.app.ingestion.naver_news_repository import (
    NaverNewsLoadResult,
    NaverNewsRepository,
    NaverNewsRepositoryError,
)
from backend.app.text_normalization import normalize_search_text


class _TransitionCursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.last_params: tuple[object, ...] | None = None

    def __enter__(self) -> "_TransitionCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _: str, params: tuple[object, ...]) -> None:
        self.last_params = params

    def executemany(self, _: str, __: list[dict[str, object]]) -> None:
        return None


class _TransitionConnection:
    def __init__(self, cursor: _TransitionCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False

    def __enter__(self) -> "_TransitionConnection":
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        self.rolled_back = exc_type is not None

    def cursor(self) -> _TransitionCursor:
        return self._cursor


class _CompletionCursor(_TransitionCursor):
    def __init__(self, inserted_count: int) -> None:
        super().__init__(rowcount=0)
        self.inserted_count = inserted_count
        self.statements: list[str] = []
        self.metadata: dict[str, object] | None = None

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.last_params = params
        self.rowcount = 1
        if "update public.ingestion_runs" in statement:
            self.metadata = params[3].obj

    def executemany(
        self, statement: str, _: list[dict[str, object]]
    ) -> None:
        self.statements.append(statement)
        self.rowcount = self.inserted_count


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
                "title": "&lt;b&gt;연금&lt;/b&gt; 시장 소식",
                "originallink": "https://publisher.example/article/1",
                "link": "https://n.news.naver.com/article/1",
                "description": "&lt;i&gt;&quot;연금&quot;&lt;/i&gt; 관련 요약",
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
        pytest.raises(NaverNewsAllItemsRejectedError) as error,
    ):
        fetch_naver_news(
            client,
            client_id="id",
            client_secret="secret",
            query="연금",
            display=2,
        )

    assert error.value.total == 2
    assert error.value.raw_item_count == 2
    assert error.value.rejected_count == 2
    assert error.value.rejected_reasons == ("missing_url", "invalid_pub_date")


def test_naver_all_invalid_result_preserves_structured_rejection_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = NaverNewsAllItemsRejectedError(
        total=2,
        raw_item_count=2,
        rejected_reasons=("missing_url", "invalid_pub_date"),
    )

    def fake_fetch(*_: object, **__: object) -> NaverNewsResponse:
        raise error

    monkeypatch.setattr(naver_ingestion, "fetch_naver_news", fake_fetch)

    result = naver_ingestion.run_live_ingestion(
        client_id="not-logged",
        client_secret="not-logged",
        database_url=None,
        fetch_only=True,
        query="연금",
        display=2,
        start=1,
        sort="date",
    )

    assert result["outcome"] == "failed"
    assert result["total"] == 2
    assert result["raw_received"] == 2
    assert result["received"] == 0
    assert result["rejected"] == 2
    assert result["rejection_reasons"] == ["missing_url", "invalid_pub_date"]


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

        def complete_run(self, *, query: str, **_: object) -> NaverNewsLoadResult:
            observed_queries.append(query)
            return NaverNewsLoadResult(inserted_count=1, duplicate_count=0)

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


def test_naver_ingestion_pages_until_age_cutoff_and_filters_old_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starts: list[int] = []
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    recent = NaverNewsItem(
        title="최근 기사",
        description=None,
        original_url="https://publisher.example/recent",
        portal_url=None,
        published_at=now - timedelta(days=1),
        raw_metadata={},
    )
    old = NaverNewsItem(
        title="오래된 기사",
        description=None,
        original_url="https://publisher.example/old",
        portal_url=None,
        published_at=now - timedelta(days=8),
        raw_metadata={},
    )

    def fake_fetch(*_: object, start: int, **__: object) -> NaverNewsResponse:
        starts.append(start)
        items = [recent] * 100 if start == 1 else [recent] * 99 + [old]
        return NaverNewsResponse(250, start, 100, 100, items, ())

    monkeypatch.setattr(naver_ingestion, "fetch_naver_news", fake_fetch)

    result = naver_ingestion.run_live_ingestion(
        client_id="not-logged",
        client_secret="not-logged",
        database_url=None,
        fetch_only=True,
        query="연금",
        display=100,
        start=1,
        sort="date",
        max_pages=10,
        max_age_days=7,
        now=now,
    )

    assert starts == [1, 101]
    assert result["pages_fetched"] == 2
    assert result["raw_received"] == 200
    assert result["received"] == 199


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
        max_pages=1,
        max_age_days=None,
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


def test_naver_completion_requires_one_running_row_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _TransitionCursor(rowcount=0)
    connection = _TransitionConnection(cursor)
    monkeypatch.setattr(
        naver_repository_module.psycopg,
        "connect",
        lambda _: connection,
    )
    repository = NaverNewsRepository("postgresql://example.invalid/db")

    with pytest.raises(NaverNewsRepositoryError, match="not running"):
        repository.complete_run(
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
            source_id=1,
            query="연금",
            response=NaverNewsResponse(0, 1, 0, 0, [], ()),
        )

    assert connection.rolled_back is True


def test_naver_completion_inserts_only_new_urls_and_records_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _CompletionCursor(inserted_count=1)
    connection = _TransitionConnection(cursor)
    monkeypatch.setattr(
        naver_repository_module.psycopg,
        "connect",
        lambda _: connection,
    )
    repository = NaverNewsRepository("postgresql://example.invalid/db")
    published_at = datetime(2026, 7, 16, 10, tzinfo=UTC)
    items = [
        NaverNewsItem(
            title=f"기사 {index}",
            description=None,
            original_url=f"https://publisher.example/{index}",
            portal_url=None,
            published_at=published_at - timedelta(hours=index),
            raw_metadata={},
        )
        for index in range(2)
    ]

    result = repository.complete_run(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        source_id=1,
        query="연금",
        response=NaverNewsResponse(2, 1, 2, 2, items, (), pages_fetched=1),
    )

    assert result == NaverNewsLoadResult(inserted_count=1, duplicate_count=1)
    assert any(
        "on conflict (source_id, original_url) do nothing" in statement
        for statement in cursor.statements
    )
    assert cursor.metadata is not None
    assert cursor.metadata["inserted_record_count"] == 1
    assert cursor.metadata["duplicate_record_count"] == 1
    assert cursor.metadata["pages_fetched"] == 1


@pytest.mark.parametrize(("rowcount", "expected"), [(1, True), (0, False)])
def test_naver_fail_run_returns_exact_result_and_preserves_rejections(
    monkeypatch: pytest.MonkeyPatch,
    rowcount: int,
    expected: bool,
) -> None:
    cursor = _TransitionCursor(rowcount=rowcount)
    connection = _TransitionConnection(cursor)
    monkeypatch.setattr(
        naver_repository_module.psycopg,
        "connect",
        lambda _: connection,
    )
    repository = NaverNewsRepository("postgresql://example.invalid/db")

    changed = repository.fail_run(
        UUID("00000000-0000-0000-0000-000000000001"),
        NaverNewsAllItemsRejectedError(
            total=2,
            raw_item_count=2,
            rejected_reasons=("missing_url", "invalid_pub_date"),
        ),
    )

    assert changed is expected
    assert cursor.last_params is not None
    metadata = cursor.last_params[1].obj
    assert metadata["raw_record_count"] == 2
    assert metadata["rejected_record_count"] == 2
    assert metadata["rejection_reasons"] == ["missing_url", "invalid_pub_date"]
