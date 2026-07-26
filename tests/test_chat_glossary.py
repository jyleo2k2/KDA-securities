"""Glossary intent regressions for beginner term questions."""

import pytest

from backend.app.chat.handlers.glossary import (
    GLOSSARY_TERMS,
    _ends_with_consonant,
    build_glossary_response,
    find_glossary_term,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    ("message", "expected_term_id"),
    [
        ("ETF가 뭐야?", "etf"),
        ("TDF가 뭐야?", "tdf"),
        ("리밸런싱이 뭐야?", "rebalancing"),
        ("위험자산 한도가 무슨 말이야?", "risk_asset_cap"),
        ("디폴트옵션이 뭐야?", "default_option"),
        ("총보수가 뭐야?", "total_expense_ratio"),
        ("원리금보장상품만 담으면 안 돼?", "principal_guaranteed"),
    ],
)
def test_term_questions_route_to_glossary(
    message: str, expected_term_id: str
) -> None:
    # 타깃은 용어를 모르는 입문자다. 정의 질문은 차단되지 않아야 한다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.GLOSSARY
    assert plan.glossary_term_id == expected_term_id
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("연금저축이 뭐야?", ChatIntent.ACCOUNT_RULE),
        ("IRP가 뭔지 쉽게 알려줘", ChatIntent.ACCOUNT_RULE),
        ("DC형이랑 DB형은 뭐가 달라?", ChatIntent.ACCOUNT_RULE),
        ("올해 연금저축에 600만원 넣으면 세액공제 얼마야?", ChatIntent.PENSION_TAX),
        ("오늘 증시 뉴스 알려줘.", ChatIntent.NEWS),
        ("내 상황에 맞는 연금저축전략을 알려줘.", ChatIntent.EDUCATIONAL_PORTFOLIO),
    ],
)
def test_glossary_does_not_capture_existing_intents(
    message: str, expected: ChatIntent
) -> None:
    # 용어 판정은 기존 인텐트가 모두 받지 않은 뒤에만 적용해야 한다.
    plan = plan_question(message)

    assert plan.intent is expected
    assert plan.glossary_term_id is None


def test_glossary_answer_cites_approved_source_and_related_terms() -> None:
    response = _service().ask(ChatRequest(message="ETF가 뭐야?"))

    assert response.intent is ChatIntent.GLOSSARY
    assert response.data_mode == "verified_knowledge"
    assert response.sources, "용어 답변에도 출처 칩이 있어야 한다"
    # B안: 물어본 용어만이 아니라 함께 알아야 할 용어를 같이 제시한다.
    assert len(response.suggested_follow_ups) >= 2
    assert "함께 알아두면 좋은 말이에요" in response.answer


def test_every_related_term_is_defined() -> None:
    labels = {term.label for term in GLOSSARY_TERMS}
    for term in GLOSSARY_TERMS:
        for related in term.related:
            assert related in labels, f"{term.label}의 연관 용어 {related} 미정의"


def test_related_follow_up_messages_stay_answerable() -> None:
    # 후속 카드를 누르면 다시 답이 나와야 한다. 계좌 질문으로 넘어가는 경우도
    # 답변 가능한 인텐트여야 하며 차단되면 안 된다.
    answerable = {
        ChatIntent.GLOSSARY,
        ChatIntent.ACCOUNT_RULE,
        ChatIntent.PENSION_TAX,
    }
    for term in GLOSSARY_TERMS:
        for related in term.related:
            particle = "이" if _ends_with_consonant(related) else "가"
            plan = plan_question(f"{related}{particle} 뭐야?")

            assert plan.intent in answerable, f"{related} 후속 질문이 막힘"
            assert plan.blocked_reason is None


def test_unknown_term_id_is_not_answered() -> None:
    assert find_glossary_term("no_such_term") is None


def test_glossary_response_avoids_product_recommendation() -> None:
    knowledge = LocalMarkdownKnowledgeRepository()
    for term in GLOSSARY_TERMS:
        response = build_glossary_response(term, knowledge)

        assert response.limitations
        assert "권유" not in response.answer
        assert "추천" not in response.answer
