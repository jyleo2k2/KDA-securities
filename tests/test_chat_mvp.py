import json
from datetime import UTC, datetime
from decimal import Decimal

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.chat.disclosures import ProviderDisclosure
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest, ChatResponse
from backend.app.chat.narrator import ClaudeNarrator
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import AccountType
from backend.app.main import app, get_chat_narrator, get_chat_service
from backend.app.retrieval.repository import NewsMatch


class FakeDisclosureRepository:
    def search(self, question, *, account_type, limit):
        assert "IRP" in question
        assert account_type == AccountType.IRP
        return [
            ProviderDisclosure(
                company_name="테스트증권",
                account_type=AccountType.IRP,
                year=2026,
                quarter=1,
                reserve_krw=Decimal("100000000"),
                earn_rate_current_pct=Decimal("4.25"),
                avg_earn_rate_3y_pct=Decimal("3.10"),
                avg_earn_rate_5y_pct=Decimal("2.80"),
                avg_earn_rate_7y_pct=None,
                avg_earn_rate_10y_pct=None,
                observed_at=datetime(2026, 7, 14, tzinfo=UTC),
                source_locator="https://example.test/fss",
            )
        ][:limit]


class FakeNewsRepository:
    def latest_news(self, search_query, *, limit=10):
        assert search_query == "연금"
        return [
            NewsMatch(
                item_id="news-1",
                title="연금 제도 관련 공식 발표",
                description="검색 API 메타데이터 요약",
                original_url="https://example.test/news/1",
                portal_url=None,
                published_at=datetime(2026, 7, 14, tzinfo=UTC),
            )
        ][:limit]


def service(
    *,
    disclosures=None,
    news=None,
) -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        disclosures=disclosures,
        news=news,
    )


def test_account_rule_question_returns_rag_source_and_numeric_evidence() -> None:
    response = service().ask(
        ChatRequest(message="IRP와 연금저축의 위험자산 한도 차이를 알려줘")
    )

    assert response.intent == ChatIntent.ACCOUNT_RULE
    assert "70%" in response.answer
    assert response.sources
    assert response.numeric_evidence[0].value == Decimal("70")
    assert all(
        source.data_boundary == "verified_knowledge" for source in response.sources
    )


def test_pension_savings_rule_does_not_apply_dc_irp_cap() -> None:
    response = service().ask(
        ChatRequest(message="연금저축펀드 위험자산 한도는 어떻게 돼?")
    )

    assert response.intent == ChatIntent.ACCOUNT_RULE
    assert "동일한 위험자산 총량 한도" in response.answer
    assert response.numeric_evidence == []


def test_mock_overlap_scenario_runs_engine_and_keeps_mock_boundary() -> None:
    response = service().ask(
        ChatRequest(
            message="중복·위험 편중 목계좌를 진단해줘",
            scenario_code="overlap_risk_concentration",
        )
    )

    assert response.intent == ChatIntent.MOCK_PORTFOLIO
    assert response.scenario_evaluation is not None
    assert response.scenario_evaluation.data_boundary == "mock"
    assert response.scenario_evaluation.total_amount_krw == Decimal("190000000.00")
    assert response.scenario_evaluation.duplicated_asset_classes == ["global_equity"]
    assert len(response.engine_results) == 3
    assert sum(
        item.allocation_percent
        for item in response.scenario_evaluation.asset_allocations
    ) == Decimal("100.00")


def test_individual_product_comparison_is_blocked_until_data_exists() -> None:
    response = service().ask(ChatRequest(message="판매 중인 상품 비교를 해줘"))

    assert response.intent == ChatIntent.OUT_OF_SCOPE
    assert response.data_mode == "unavailable"
    assert "개별 상품" in response.answer


def test_future_return_and_order_requests_are_blocked() -> None:
    future = service().ask(ChatRequest(message="내년 예상수익률을 알려줘"))
    order = service().ask(ChatRequest(message="이 상품을 대신 매수해줘"))

    assert future.intent == ChatIntent.OUT_OF_SCOPE
    assert future.data_mode == "blocked"
    assert order.intent == ChatIntent.OUT_OF_SCOPE
    assert order.data_mode == "blocked"


def test_disclosure_comparison_uses_only_repository_numbers() -> None:
    response = service(disclosures=FakeDisclosureRepository()).ask(
        ChatRequest(message="테스트증권 IRP 과거 수익률을 알려줘")
    )

    assert response.intent == ChatIntent.PROVIDER_DISCLOSURE
    assert "4.25%" in response.answer
    assert response.numeric_evidence[0].value == Decimal("4.25")
    assert response.sources[0].data_boundary == "official_disclosure"
    assert "개별 상품" in response.limitations[0]


def test_unconfigured_disclosure_does_not_fall_back_to_fixture() -> None:
    response = service().ask(ChatRequest(message="IRP 사업자 수익률을 알려줘"))

    assert response.intent == ChatIntent.PROVIDER_DISCLOSURE
    assert response.data_mode == "unavailable"
    assert "fixture" in response.answer
    assert response.sources == []


def test_news_response_exposes_metadata_and_original_link() -> None:
    response = service(news=FakeNewsRepository()).ask(
        ChatRequest(message="연금 뉴스 알려줘")
    )

    assert response.intent == ChatIntent.NEWS
    assert response.sources[0].locator == "https://example.test/news/1"
    assert response.sources[0].data_boundary == "news_metadata"
    assert "기사 본문이 아닌" in response.limitations[0]


def test_response_rejects_numbers_without_sources() -> None:
    with pytest.raises(ValidationError, match="numbers require"):
        ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer="근거 없이 70%라고 답하면 안 됩니다.",
            data_mode="invalid",
        )


def _mock_anthropic_message(
    text: str, review_note: str = "", thinking: str | None = None
) -> dict:
    content: list[dict] = []
    if thinking is not None:
        content.append({"type": "thinking", "thinking": thinking, "signature": ""})
    content.append(
        {
            "type": "text",
            "text": json.dumps(
                {"narration": text, "review_note": review_note}, ensure_ascii=False
            ),
        }
    )
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def _narrator_with_mock_response(
    text: str, review_note: str = "", thinking: str | None = None
) -> ClaudeNarrator:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_mock_anthropic_message(text, review_note, thinking)
        )

    mock_client = anthropic.Anthropic(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return ClaudeNarrator(api_key="test-key", model="test-model", client=mock_client)


def test_claude_narrator_accepts_only_existing_numbers() -> None:
    base = service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))

    narrator = _narrator_with_mock_response(
        "IRP 일반 위험자산 한도는 70%이며 근거를 확인하세요."
    )
    response = narrator.narrate(base)

    assert response.narration_mode == "claude_verified"
    assert response.model_name == "test-model"
    assert response.numeric_evidence == base.numeric_evidence


def test_claude_narrator_rejects_new_numbers() -> None:
    base = service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))

    narrator = _narrator_with_mock_response(
        "IRP 위험자산을 80%까지 운용할 수 있습니다."
    )
    response = narrator.narrate(base)

    assert response.narration_mode == "deterministic"
    assert response.answer == base.answer
    assert "새로운 숫자" in response.limitations[-1]


def test_claude_narrator_prefers_thinking_summary_over_review_note() -> None:
    base = service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))

    narrator = _narrator_with_mock_response(
        "IRP 일반 위험자산 한도는 70%이며 근거를 확인하세요.",
        review_note="검토 노트입니다.",
        thinking="검증 답변의 70% 한도를 쉬운 문장으로 바꾸는 중.",
    )
    response = narrator.narrate(base)

    assert response.narration_mode == "claude_verified"
    assert response.narration_reasoning is not None
    assert "70%" in response.narration_reasoning


def test_claude_narrator_falls_back_to_review_note_without_thinking() -> None:
    base = service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))

    narrator = _narrator_with_mock_response(
        "IRP 일반 위험자산 한도는 70%이며 근거를 확인하세요.",
        review_note="검증 답변의 한도 규칙을 원문 숫자 그대로 풀어썼습니다.",
    )
    response = narrator.narrate(base)

    assert response.narration_mode == "claude_verified"
    assert response.narration_reasoning == (
        "검증 답변의 한도 규칙을 원문 숫자 그대로 풀어썼습니다."
    )


def test_claude_narrator_drops_reasoning_with_new_numbers() -> None:
    base = service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))

    narrator = _narrator_with_mock_response(
        "IRP 일반 위험자산 한도는 70%이며 근거를 확인하세요.",
        thinking="80%라는 새 숫자를 언급하는 검토 과정.",
    )
    response = narrator.narrate(base)

    # 본문은 유지되고 검토 과정만 조용히 생략된다.
    assert response.narration_mode == "claude_verified"
    assert response.narration_reasoning is None


def test_fastapi_exposes_chat_mvp_golden_path() -> None:
    chatbot = service()
    app.dependency_overrides[get_chat_service] = lambda: chatbot
    app.dependency_overrides[get_chat_narrator] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/demo",
                json={"message": "IRP 위험자산 한도를 알려줘"},
            )
            capabilities = client.get("/chat/demo/capabilities")
            scenarios = client.get("/chat/demo/scenarios")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["intent"] == "account_rule"
    assert capabilities.status_code == 200
    assert "dc_dormant" in capabilities.json()["scenario_codes"]
    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 3


def test_root_redirects_browser_to_api_docs() -> None:
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
