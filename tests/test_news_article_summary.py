from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from backend.app.ingestion import naver_summaries, news_article
from backend.app.ingestion.naver_news_repository import PendingNewsSummary
from backend.app.ingestion.news_article import (
    NewsArticleFetchError,
    extract_article_text,
    fetch_news_article,
)
from backend.app.ingestion.news_summarizer import (
    MAX_SUMMARY_LINE_CHARS,
    NewsSummarizer,
    NewsSummaryError,
    NewsSummaryOutput,
    source_spans,
    validate_summary_against_source,
)


def _article_html() -> str:
    paragraph = (
        "퇴직연금 제도 운영기관은 가입자 교육과 자산운용 정보 제공을 "
        "강화한다고 밝혔다. "
        "이번 발표에는 제도 현황과 향후 공개 일정에 관한 설명이 포함됐다. "
    )
    return f"<html><body><article><p>{paragraph * 5}</p></article></body></html>"


def test_extract_article_text_returns_substantial_body() -> None:
    text = extract_article_text(_article_html())

    assert len(text) >= 200
    assert "가입자 교육" in text


def test_article_fetch_rejects_loopback_address() -> None:
    with pytest.raises(NewsArticleFetchError, match="non_public_address"):
        news_article._assert_public_url("http://127.0.0.1/private")


def test_article_fetch_extracts_text_and_hash_without_storing_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(news_article, "_assert_public_url", lambda _: None)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            stream=httpx.ByteStream(_article_html().encode("utf-8")),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        article = fetch_news_article(client, "https://publisher.example/article")

    assert "<article>" not in article.text
    assert len(article.content_sha256) == 64
    assert article.final_url == "https://publisher.example/article"


def test_summary_validation_rejects_numbers_absent_from_source() -> None:
    summary = NewsSummaryOutput(
        summary_lines=(
            "기관이 연금 제도 개선안을 발표했다.",
            "가입자 안내를 강화한다고 설명했다.",
            "관련 예산은 999원이라고 밝혔다.",
        )
    )

    with pytest.raises(NewsSummaryError, match="validation_failed"):
        validate_summary_against_source(summary, "기관이 제도 개선안을 발표했다.")


def test_summary_output_requires_exactly_three_clean_lines() -> None:
    with pytest.raises(ValueError):
        NewsSummaryOutput(summary_lines=("한 줄", "두 줄"))


def test_summary_output_rejects_a_line_that_exceeds_mobile_contract() -> None:
    with pytest.raises(ValueError):
        NewsSummaryOutput(
            summary_lines=(
                "가" * (MAX_SUMMARY_LINE_CHARS + 1),
                "둘째 문장입니다.",
                "셋째 문장입니다.",
            )
        )


def test_summary_validation_rejects_recommendations_even_when_source_has_them() -> None:
    summary = NewsSummaryOutput(
        summary_lines=(
            "회사가 실적을 발표했다.",
            "매수를 권한다는 의견이 나왔다.",
            "주가 변동 가능성을 확인해야 한다.",
        )
    )

    with pytest.raises(NewsSummaryError, match="validation_failed"):
        validate_summary_against_source(
            summary,
            "회사가 실적을 발표했고 매수를 권한다는 의견이 나왔다.",
        )


def test_summary_validation_requires_a_speaker_for_outlook() -> None:
    summary = NewsSummaryOutput(
        summary_lines=(
            "회사가 실적을 발표했다.",
            "매출은 10% 늘었다.",
            "시장 반등을 전망했다.",
        )
    )

    with pytest.raises(NewsSummaryError, match="validation_failed"):
        validate_summary_against_source(
            summary,
            "회사가 실적을 발표했고 매출은 10% 늘었다. 시장 반등을 전망했다.",
        )


def test_summarizer_parses_native_three_line_output() -> None:
    summarizer = NewsSummarizer(
        api_key="test-key",
        model="test-model",
        prompt_version="test-v1",
    )
    payload = json.dumps(
        {"selected_indices": [0, 1, 2]},
        ensure_ascii=False,
    )

    def respond(*_: object) -> ModelResponse:
        return ModelResponse(parts=[TextPart(payload)])

    article = (
        "기관이 연금 제도 개선안을 발표했다. 가입자 교육을 강화한다고 설명했다. "
        "세부 일정은 추후 공개한다고 밝혔다."
    )
    with summarizer.agent.override(model=FunctionModel(respond)):
        result = summarizer.summarize(title="연금 제도 개선", article_text=article)

    assert result.summary_lines == (
        "기관이 연금 제도 개선안을 발표했다.",
        "가입자 교육을 강화한다고 설명했다.",
        "세부 일정은 추후 공개한다고 밝혔다.",
    )


def test_source_spans_are_unique_extractive_and_within_mobile_limit() -> None:
    article = (
        "기관은 매우 긴 설명을 발표했고, 가입자 교육과 자산운용 정보 제공을 "
        "강화하며 세부 일정을 다음 달에 공개할 예정이라고 관계자가 밝혔다. "
        "둘째 문장은 짧지만 의미가 충분하다. 셋째 문장도 충분히 길다."
    )

    spans = source_spans(article)

    assert len(spans) >= 3
    assert len(spans) == len(set(spans))
    assert all(len(span) <= MAX_SUMMARY_LINE_CHARS for span in spans)
    normalized_article = " ".join(article.split())
    assert all(span.rstrip(".!?。") in normalized_article for span in spans)


def test_gemini_36_summary_uses_minimal_thinking() -> None:
    summarizer = NewsSummarizer(
        api_key="test-key",
        model="gemini-3.6-flash",
        prompt_version="test-v1",
    )

    assert summarizer.agent.model_settings["google_thinking_config"] == {
        "thinking_level": "minimal"
    }


def test_summary_rejects_source_unrelated_market_template() -> None:
    summary = NewsSummaryOutput(
        summary_lines=(
            "주요 지수가 하락세를 보이며 시장 거래가 마감됐다.",
            "해당 지수는 전일 대비 2.5% 감소한 수치를 기록했다.",
            "금융 시장과 관련 업종 전반에 불확실성이 증대되고 있다.",
        )
    )
    article = (
        "한국은행은 기준금리를 연 2.5%로 유지했다고 발표했다. "
        "위원회는 물가와 금융안정 상황을 더 확인할 필요가 있다고 설명했다. "
        "향후 결정은 국내외 경제 지표에 따라 달라질 수 있다고 밝혔다."
    )

    with pytest.raises(NewsSummaryError, match="validation_failed"):
        validate_summary_against_source(summary, article)


def test_summary_requires_each_line_to_be_an_extractive_source_span() -> None:
    summary = NewsSummaryOutput(
        summary_lines=(
            "한국은행이 기준금리를 2.5%로 동결했다.",
            "위원회는 물가와 금융안정 상황을 확인했다.",
            "향후 결정은 경제 지표에 따라 달라질 수 있다.",
        )
    )
    article = (
        "한국은행은 기준금리를 연 2.5%로 유지했다고 발표했다. "
        "위원회는 물가와 금융안정 상황을 더 확인할 필요가 있다고 설명했다. "
        "향후 결정은 국내외 경제 지표에 따라 달라질 수 있다고 밝혔다."
    )

    with pytest.raises(NewsSummaryError, match="validation_failed"):
        validate_summary_against_source(summary, article)


def test_summary_worker_isolates_fetch_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        PendingNewsSummary(
            item_id=UUID(int=1),
            title="정상 기사",
            original_url="https://example.test/1",
        ),
        PendingNewsSummary(
            item_id=UUID(int=2),
            title="실패 기사",
            original_url="https://example.test/2",
        ),
    ]

    class Repository:
        def __init__(self) -> None:
            self.claimed = False
            self.saved: list[UUID] = []
            self.failed: list[tuple[UUID, str, str]] = []

        def claim_summary_items(self, **_: object):
            if self.claimed:
                return []
            self.claimed = True
            return items

        def save_summary(self, *, item_id: UUID, **_: object) -> None:
            self.saved.append(item_id)

        def fail_summary(
            self, *, item_id: UUID, status: str, error_code: str
        ) -> None:
            self.failed.append((item_id, status, error_code))

    repository = Repository()
    monkeypatch.setattr(
        naver_summaries,
        "NaverNewsRepository",
        lambda _: repository,
    )

    def fake_fetch(_: httpx.Client, url: str):
        if url.endswith("/2"):
            raise NewsArticleFetchError("publisher_http_error")
        return SimpleNamespace(text="연금 기사 원문", content_sha256="a" * 64)

    class Summarizer:
        def __init__(self, **_: object) -> None:
            pass

        def summarize(self, **_: object) -> NewsSummaryOutput:
            return NewsSummaryOutput(
                summary_lines=("첫 문장", "둘째 문장", "셋째 문장")
            )

    monkeypatch.setattr(naver_summaries, "fetch_news_article", fake_fetch)
    monkeypatch.setattr(naver_summaries, "NewsSummarizer", Summarizer)

    result = naver_summaries.run_summary_worker(
        database_url="postgresql://test",
        api_key="test-key",
        model="test-model",
        prompt_version="test-v1",
        limit=2,
        concurrency=2,
    )

    assert result == {
        "claimed": 2,
        "succeeded": 1,
        "fetch_failed": 1,
        "model_failed": 0,
        "validation_failed": 0,
        "outcome": "partial",
    }
    assert repository.saved == [UUID(int=1)]
    assert repository.failed == [
        (UUID(int=2), "fetch_failed", "publisher_http_error")
    ]


def test_summarizer_requires_all_configuration_values() -> None:
    with pytest.raises(ValueError, match="required"):
        NewsSummarizer(api_key="", model="model", prompt_version="v1")
