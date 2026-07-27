"""Regression coverage for ambiguous pension fee amount questions."""

import pytest

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
    "message",
    (
        "수수료는 얼마나 떼?",
        "비용이 얼마나 나가?",
        "보수는 몇 퍼센트야?",
    ),
)
def test_ambiguous_fee_amount_question_requests_a_target(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is BlockedReason.FEE_TARGET_REQUIRED


def test_fee_clarification_offers_answerable_follow_ups() -> None:
    response = _service().ask(ChatRequest(message="수수료는 얼마나 떼?"))

    assert response.intent is ChatIntent.OUT_OF_SCOPE
    assert "금융회사 수수료" in response.answer
    assert "상품의 총보수" in response.answer
    assert [item.label for item in response.suggested_follow_ups] == [
        "ETF 총보수 알아보기",
        "연금계좌 수수료 비교 기준",
        "수수료의 장기 영향",
    ]
    assert response.limitations

    for follow_up in response.suggested_follow_ups:
        follow_up_plan = plan_question(follow_up.message)
        assert follow_up_plan.intent is not ChatIntent.OUT_OF_SCOPE
        assert follow_up_plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    (
        ("수수료가 왜 중요해?", ChatIntent.INVESTING_PRINCIPLE),
        ("상품 바꾸면 수수료 들어?", ChatIntent.ACCOUNT_RULE),
        ("총보수가 뭐야?", ChatIntent.GLOSSARY),
        ("IRP 사업자 과거 수익률 공시를 알려줘", ChatIntent.PROVIDER_DISCLOSURE),
    ),
)
def test_specific_fee_questions_keep_existing_routes(
    message: str,
    expected_intent: ChatIntent,
) -> None:
    plan = plan_question(message)

    assert plan.intent is expected_intent
    assert plan.blocked_reason is None
