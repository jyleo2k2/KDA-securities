"""구어 표기 질문이 엉뚱한 인텐트로 새지 않는지 고정한다.
"연금이 머야"가 미분류로 떨어지고, 직전 전략 대화 문맥이 그것을 전략 요청으로
승격시켜 리밸런싱 답변이 나가던 회귀를 막는다.
"""

import pytest

from backend.app.chat.models import ChatIntent, ChatRequest, ConversationContext
from backend.app.chat.query_planner import (
    AccountRuleTopic,
    BlockedReason,
    plan_question,
)
from backend.app.chat.routing import IntentRouter

# 표기만 다를 뿐 모두 "연금 제도가 무엇인가"를 묻는 질문이다.
PENSION_DEFINITION_SPELLINGS = (
    "연금이 뭐야",
    "연금이 머야",
    "연금이 모야",
    "연금이 머임",
    "연금이 머냐",
)


@pytest.mark.parametrize("message", PENSION_DEFINITION_SPELLINGS)
def test_colloquial_pension_question_reaches_account_rule(message: str) -> None:
    plan = plan_question(message)

    assert plan.blocked_reason is None
    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.account_rule_topic is AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW


@pytest.mark.parametrize("term", ("ETF", "리밸런싱", "TDF"))
def test_colloquial_glossary_question_is_not_blocked(term: str) -> None:
    plan = plan_question(f"{term}가 머야")

    assert plan.blocked_reason is not BlockedReason.UNSUPPORTED


def test_strategy_context_does_not_capture_plain_question() -> None:
    """후속 지시어가 없으면 직전 전략 대화가 질문을 가로채지 않는다."""

    request = ChatRequest(
        message="연금이 머야",
        conversation_context=ConversationContext(
            last_intent=ChatIntent.EDUCATIONAL_PORTFOLIO
        ),
    )

    assert IntentRouter.contextual_message(request) == "연금이 머야"


def test_strategy_context_still_applies_to_follow_up() -> None:
    """"그럼"처럼 이어 묻는 신호가 있으면 기존 문맥 보정을 유지한다."""

    request = ChatRequest(
        message="그럼 어떻게 나눠 담아",
        conversation_context=ConversationContext(
            last_intent=ChatIntent.EDUCATIONAL_PORTFOLIO
        ),
    )

    assert IntentRouter.contextual_message(request) == (
        "연금 운용 전략 그럼 어떻게 나눠 담아"
    )


def test_ordinary_word_starting_with_meo_is_not_rewritten() -> None:
    """"머리"처럼 정상 단어는 정규화가 건드리지 않는다."""

    plan = plan_question("머리가 아픈데 연금 얘기 좀 해줘")

    assert "머리" in plan.normalized_message
