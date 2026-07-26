"""Glossary coverage for general economy terms beginners hit first."""

import pytest

from backend.app.chat.handlers.glossary import (
    GLOSSARY_TERMS,
    build_glossary_response,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService

_ECONOMY_TERM_IDS = (
    "compound_interest",
    "simple_interest",
    "stock",
    "bond",
    "fund",
    "diversification",
    "asset_allocation",
    "installment_investing",
    "volatility",
    "annualized_return",
    "interest_rate",
    "inflation",
    "exchange_rate",
    "currency_hedge",
    "dividend",
    "market_cap",
    "index",
    "kospi",
    "kosdaq",
    "sp500",
    "nasdaq",
)


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    ("message", "expected_term_id"),
    [
        ("복리가 뭐야?", "compound_interest"),
        ("단리가 뭐야?", "simple_interest"),
        ("주식이 뭐야?", "stock"),
        ("채권이 뭐야?", "bond"),
        ("펀드가 뭐야?", "fund"),
        ("분산투자가 뭐야?", "diversification"),
        ("자산배분이 뭐야?", "asset_allocation"),
        ("적립식이 뭐야?", "installment_investing"),
        ("변동성이 뭐야?", "volatility"),
        ("연평균 수익률이 뭐야?", "annualized_return"),
        ("금리가 뭐야?", "interest_rate"),
        ("인플레이션이 뭐야?", "inflation"),
        ("환율이 뭐야?", "exchange_rate"),
        ("환헤지가 뭐야?", "currency_hedge"),
        ("배당이 뭐야?", "dividend"),
        ("시가총액이 뭐야?", "market_cap"),
        ("지수가 뭐야?", "index"),
        ("코스피가 뭐야?", "kospi"),
        ("코스닥이 뭐야?", "kosdaq"),
        ("S&P500이 뭐야?", "sp500"),
        ("나스닥이 뭐야?", "nasdaq"),
    ],
)
def test_economy_terms_route_to_glossary(
    message: str, expected_term_id: str
) -> None:
    # 연금 용어보다 앞서 막히던 일반 경제 용어를 결정론으로 받는다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.GLOSSARY
    assert plan.glossary_term_id == expected_term_id
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected_term_id"),
    [
        ("주식이랑 채권이 뭐가 달라?", "bond"),
        ("펀드랑 ETF는 뭐가 달라?", "fund"),
        ("단리랑 복리가 뭐가 달라?", "compound_interest"),
    ],
)
def test_comparison_questions_reach_glossary(
    message: str, expected_term_id: str
) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.GLOSSARY
    assert plan.glossary_term_id == expected_term_id


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # 계좌·세액은 제도 설명이 더 정확하므로 뜻풀이에 넘기지 않는다.
        ("연금저축이 뭐야?", ChatIntent.ACCOUNT_RULE),
        ("IRP가 뭔지 쉽게 알려줘", ChatIntent.ACCOUNT_RULE),
        ("DC형, IRP, 연금저축은 뭐가 달라?", ChatIntent.ACCOUNT_RULE),
        (
            "올해 연금저축에 600만원 넣으면 세액공제 얼마야?",
            ChatIntent.PENSION_TAX,
        ),
        ("IRP에 900만원 넣으면 얼마 돌려받아?", ChatIntent.PENSION_TAX),
        ("35살인데 어떻게 배분해?", ChatIntent.EDUCATIONAL_PORTFOLIO),
        ("뭐부터 해야 할지 모르겠어", ChatIntent.GETTING_STARTED),
        ("오늘 증시 뉴스 알려줘.", ChatIntent.NEWS),
    ],
)
def test_existing_intents_keep_priority(
    message: str, expected: ChatIntent
) -> None:
    plan = plan_question(message)

    assert plan.intent is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # 상품 목록을 묻는 질문은 정의가 아니므로 조회 인텐트가 유지된다.
        ("요즘 반도체 ETF 뭐가 있어?", ChatIntent.ETF_THEME),
        ("채권 ETF 어떤 거 있어?", ChatIntent.ETF_THEME),
        ("ETF 분배금은 어떻게 받아?", ChatIntent.ETF_DISTRIBUTION),
        ("분배금 재투자하는 게 나아?", ChatIntent.ETF_DISTRIBUTION),
        ("안정형이면 어떻게 굴려?", ChatIntent.EDUCATIONAL_PORTFOLIO),
        ("공격투자형 포트폴리오 알려줘", ChatIntent.EDUCATIONAL_PORTFOLIO),
    ],
)
def test_lookup_questions_are_not_hijacked(
    message: str, expected: ChatIntent
) -> None:
    plan = plan_question(message)

    assert plan.intent is expected
    assert plan.glossary_term_id is None


@pytest.mark.parametrize(
    "message",
    [
        "리밸런싱은 언제 해?",
        "리밸런싱은 얼마나 자주 해?",
        "리밸런싱 몇 개월마다 해?",
    ],
)
def test_rebalancing_cadence_questions_reach_guide(message: str) -> None:
    # 점검 주기는 엔진이 성향별로 계산한다. 정의만 주고 끝내면 안 된다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.EDUCATIONAL_PORTFOLIO
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    "message",
    ["리밸런싱이 뭐야?", "리밸런싱이 무슨 말이야?"],
)
def test_rebalancing_definition_stays_glossary(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.GLOSSARY
    assert plan.glossary_term_id == "rebalancing"


def test_economy_terms_are_defined_and_cited() -> None:
    knowledge = LocalMarkdownKnowledgeRepository()
    by_id = {term.term_id: term for term in GLOSSARY_TERMS}
    for term_id in _ECONOMY_TERM_IDS:
        term = by_id.get(term_id)

        assert term is not None, f"{term_id} 용어 미정의"
        response = build_glossary_response(term, knowledge)

        assert response.sources, f"{term.label} 답변에 출처 칩이 없음"
        assert response.limitations
        assert "권유" not in response.answer
        assert "추천" not in response.answer


def test_related_terms_all_exist() -> None:
    labels = {term.label for term in GLOSSARY_TERMS}
    for term in GLOSSARY_TERMS:
        for related in term.related:
            assert related in labels, f"{term.label}의 연관 용어 {related} 미정의"


def test_economy_answer_uses_verified_knowledge() -> None:
    response = _service().ask(ChatRequest(message="채권이 뭐야?"))

    assert response.intent is ChatIntent.GLOSSARY
    assert response.data_mode == "verified_knowledge"
    assert response.sources
    assert "함께 알아두면 좋은 말이에요" in response.answer
