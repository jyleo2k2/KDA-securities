from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.chat.cards import CHAT_CARDS, build_suggested_follow_ups
from backend.app.chat.models import (
    ChatIntent,
    ChatNewsItem,
    ChatResponse,
    ConversationContext,
    MarketRegion,
    NewsConversationContext,
    SourceEvidence,
)
from backend.app.chat.query_planner import plan_question
from backend.app.chat.suggested_prompts import SUGGESTED_CHAT_PROMPTS
from backend.app.main import app


def test_catalog_cards_route_to_their_declared_intent() -> None:
    for card in CHAT_CARDS:
        plan = plan_question(card.message)
        assert plan.intent == card.intent, card.card_id
        assert plan.blocked_reason is None, card.card_id


def test_prewarming_prompts_are_catalog_messages() -> None:
    catalog_messages = {card.message for card in CHAT_CARDS}
    assert set(SUGGESTED_CHAT_PROMPTS) <= catalog_messages


def test_cards_endpoint_returns_static_catalog() -> None:
    with TestClient(app) as client:
        response = client.get("/chat/cards")

    assert response.status_code == 200
    payload = response.json()
    assert [card["card_id"] for card in payload["cards"]] == [
        card.card_id for card in CHAT_CARDS
    ]
    assert all(card["preview"] is None for card in payload["cards"])
    assert all(isinstance(card["conditions"], list) for card in payload["cards"])
    assert any(
        card["card_id"] == "macro_evidence"
        and card["message"] == "BOK·KOSIS·FRED 거시환경 근거를 보여줘."
        for card in payload["cards"]
    )


def test_follow_up_cards_are_bounded_and_route_safely() -> None:
    news = ChatResponse(
        intent=ChatIntent.NEWS,
        answer="최근 증시 뉴스예요.",
        data_mode="news_summary",
        sources=[
            SourceEvidence(
                evidence_id="news:1",
                label="뉴스",
                locator="https://example.test/news",
                data_boundary="news_summary",
            )
        ],
        news_items=[
            ChatNewsItem(
                evidence_id="news:1",
                title="첫 번째 뉴스",
                original_url="https://example.test/news",
            )
        ],
        conversation_context=ConversationContext(
            news=NewsConversationContext(
                news_item_ids=["1"],
                market_region=MarketRegion.KR,
            )
        ),
    )
    pension_tax = ChatResponse(
        intent=ChatIntent.PENSION_TAX,
        answer="세액공제 결과예요.",
        data_mode="engine",
    ).model_copy(
        update={"pension_tax_result": SimpleNamespace(tax_credit=object())}
    )
    responses = (
        news,
        ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer="진단 결과예요.",
            data_mode="mock",
        ),
        pension_tax,
        ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer="포트폴리오 예시예요.",
            data_mode="engine",
        ),
    )

    expected = {
        "news_detail_1": ChatIntent.NEWS,
        "news_region_us": ChatIntent.NEWS,
        "news_refresh": ChatIntent.NEWS,
        "mock_risk_cap": ChatIntent.ACCOUNT_RULE,
        "mock_tax": ChatIntent.PENSION_TAX,
        "tax_withdrawal": ChatIntent.PENSION_TAX,
        "education_risk_cap": ChatIntent.ACCOUNT_RULE,
    }
    follow_ups = [
        follow_up
        for response in responses
        for follow_up in build_suggested_follow_ups(response)
    ]

    assert all(len(build_suggested_follow_ups(response)) <= 3 for response in responses)
    assert {follow_up.follow_up_id for follow_up in follow_ups} == set(expected)
    for follow_up in follow_ups:
        plan = plan_question(follow_up.message)
        assert plan.intent == expected[follow_up.follow_up_id]
        assert plan.blocked_reason is None


def test_new_response_fields_serialize_as_empty_arrays() -> None:
    payload = ChatResponse(
        intent=ChatIntent.OUT_OF_SCOPE,
        answer="지원하지 않는 요청이에요.",
        data_mode="unavailable",
    ).model_dump(mode="json")

    assert payload["suggested_follow_ups"] == []
    assert payload["visualizations"] == []
