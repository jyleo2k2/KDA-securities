"""Coverage for "why do we do this?" investing principle answers.

타깃 사용자는 용어 뜻을 알아도 그렇게 하는 이유를 모른다. 용어 사전이 "무엇"을
맡고 이 인텐트가 "왜"를 맡으므로, 둘의 경계가 흐트러지지 않는지도 함께 고정한다.
"""

import pytest

from backend.app.chat.handlers.account_rules import blocked_response
from backend.app.chat.handlers.investing_principle import (
    INVESTING_PRINCIPLES,
    InvestingPrinciple,
    investing_principle_by_id,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import BlockedReason, plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    ("message", "expected_principle"),
    [
        ("장기투자를 왜 해야 해?", "long_term_investing"),
        ("분산투자를 왜 해야 해?", "why_diversify"),
        ("한 곳에 몰아넣으면 왜 위험해?", "concentration_risk"),
        ("위험을 줄이면 수익도 줄어?", "risk_return_tradeoff"),
        ("수수료가 왜 중요해?", "fee_impact"),
        ("복리가 왜 좋아?", "compounding_time"),
        ("적립식으로 왜 나눠 사?", "installment_effect"),
        ("젊을 때 주식 비중을 왜 높게 해?", "young_risk_weight"),
        ("나이 들면 왜 안전자산을 늘려?", "age_safe_asset"),
        ("리밸런싱을 왜 해야 해?", "why_rebalance"),
        ("환헤지를 왜 해?", "why_currency_hedge"),
    ],
)
def test_why_questions_route_to_investing_principle(
    message: str, expected_principle: str
) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.INVESTING_PRINCIPLE
    assert plan.investing_principle_id == expected_principle
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    "principle", INVESTING_PRINCIPLES, ids=lambda item: item.principle_id
)
def test_every_principle_carries_a_caveat(principle: InvestingPrinciple) -> None:
    # 원리 설명이 낙관적으로만 읽히면 안 된다. 한계 문장을 항상 요구한다.
    stored = investing_principle_by_id(principle.principle_id)

    assert stored is not None
    assert stored.caveat


def test_principle_answer_states_reason_then_limit() -> None:
    response = _service().ask(ChatRequest(message="분산투자를 왜 해야 해?"))

    assert response.intent is ChatIntent.INVESTING_PRINCIPLE
    assert "자산마다 오르내리는 시점이 다르기 때문이에요" in response.answer
    assert "다만" in response.answer
    assert response.sources


@pytest.mark.parametrize(
    "message",
    [
        "장기투자를 왜 해야 해?",
        "수수료가 왜 중요해?",
        "리밸런싱을 왜 해야 해?",
        "환헤지를 왜 해?",
    ],
)
def test_principle_answers_cite_approved_evidence(message: str) -> None:
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.INVESTING_PRINCIPLE
    assert response.sources
    assert response.suggested_follow_ups


@pytest.mark.parametrize(
    ("message", "expected_intent", "expected_term", "expected_principle"),
    [
        ("리밸런싱이 뭐야?", ChatIntent.GLOSSARY, "rebalancing", None),
        (
            "리밸런싱을 왜 해야 해?",
            ChatIntent.INVESTING_PRINCIPLE,
            None,
            "why_rebalance",
        ),
        ("복리가 뭐야?", ChatIntent.GLOSSARY, "compound_interest", None),
        (
            "복리가 왜 좋아?",
            ChatIntent.INVESTING_PRINCIPLE,
            None,
            "compounding_time",
        ),
        ("분산투자가 뭐야?", ChatIntent.GLOSSARY, "diversification", None),
        (
            "분산투자를 왜 해야 해?",
            ChatIntent.INVESTING_PRINCIPLE,
            None,
            "why_diversify",
        ),
    ],
)
def test_definition_and_reason_questions_stay_separate(
    message: str,
    expected_intent: ChatIntent,
    expected_term: str | None,
    expected_principle: str | None,
) -> None:
    # "뭐야"는 용어, "왜"는 원리다. 한쪽이 다른 쪽을 삼키면 답이 어긋난다.
    plan = plan_question(message)

    assert plan.intent is expected_intent
    assert plan.glossary_term_id == expected_term
    assert plan.investing_principle_id == expected_principle


def test_rebalancing_timing_question_keeps_existing_route() -> None:
    # 시점 질문은 기존 포트폴리오 안내가 맡는다. 원리 인텐트가 가로채면 회귀다.
    plan = plan_question("리밸런싱 언제 해?")

    assert plan.intent is ChatIntent.EDUCATIONAL_PORTFOLIO
    assert plan.investing_principle_id is None


@pytest.mark.parametrize(
    ("message", "expected_reason"),
    [
        ("어떤 ETF가 제일 좋아?", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("나 어떻게 투자해야 해?", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("뭐 사야 돼?", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("지금 사도 될까?", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("지금 팔아야 해?", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("내 나이엔 뭐가 맞아?", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("수익률 높은 거 알려줘", BlockedReason.PERSONAL_ALLOCATION_ADVICE),
        ("원금 보장돼?", BlockedReason.PRINCIPAL_GUARANTEE_QUESTION),
        ("손해 안 보는 방법 있어?", BlockedReason.PRINCIPAL_GUARANTEE_QUESTION),
        ("얼마나 벌 수 있어?", BlockedReason.PRINCIPAL_GUARANTEE_QUESTION),
        ("이거 사면 돈 벌어?", BlockedReason.PRINCIPAL_GUARANTEE_QUESTION),
    ],
)
def test_personal_advice_questions_get_a_route_not_a_dead_end(
    message: str, expected_reason: BlockedReason
) -> None:
    # 답을 정해주지는 않되, 막다른 길 대신 다음 단계를 준다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is expected_reason

    response = blocked_response(expected_reason, user_message=plan.normalized_message)

    assert response.suggested_follow_ups
    assert response.limitations


def test_personal_allocation_reply_asks_for_conditions() -> None:
    plan = plan_question("나 어떻게 투자해야 해?")
    response = blocked_response(
        BlockedReason.PERSONAL_ALLOCATION_ADVICE,
        user_message=plan.normalized_message,
    )

    assert "나이와 투자성향" in response.answer
    assert [item.follow_up_id for item in response.suggested_follow_ups] == [
        "advice_profile_guide",
        "advice_age_allocation",
        "advice_why_diversify",
    ]


def test_principal_guarantee_reply_refuses_to_promise_safety() -> None:
    plan = plan_question("원금 보장돼?")
    response = blocked_response(
        BlockedReason.PRINCIPAL_GUARANTEE_QUESTION,
        user_message=plan.normalized_message,
    )

    assert "손실이 나지 않는 방법을 알려드릴 수는 없어요" in response.answer
    assert "원금 보장이나 손실 회피를 약속하지 않아요." in response.limitations


@pytest.mark.parametrize(
    "message",
    [
        "비트코인 지금 사도 돼?",
        "청약 통장 어떻게 만들어?",
        "코인 지금 사도 될까?",
    ],
)
def test_non_pension_assets_keep_the_safe_fallback(message: str) -> None:
    # 연금 밖 자산을 콕 집어 물으면 조언형 응답으로 넘기지 않는다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is BlockedReason.UNSUPPORTED
