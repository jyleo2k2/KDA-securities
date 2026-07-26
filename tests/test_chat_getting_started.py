"""Getting-started intent regressions for users who do not know what to ask."""

import pytest

from backend.app.chat.handlers.getting_started import (
    GETTING_STARTED_DATA_MODE,
    getting_started_response,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService

_PLANNER_FOLLOW_UP_ID = "open_pension_planner"


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    "message",
    [
        "뭐부터 해야 할지 모르겠어",
        "뭐부터 시작해야 해?",
        "어디서부터 시작하지?",
        "처음인데 뭘 해야 해?",
        "어떻게 시작해야 하는지 모르겠어",
        "무엇부터 봐야 할까?",
        "연금 처음인데 어떻게 해?",
        "감이 안 와",
    ],
)
def test_opening_questions_route_to_getting_started(message: str) -> None:
    # 타깃은 무엇을 물어야 할지도 모르는 입문자다. 시작점 질문은 차단되면 안 된다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.GETTING_STARTED
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ETF가 뭐야?", ChatIntent.GLOSSARY),
        ("디폴트옵션이 뭔지 모르겠어", ChatIntent.GLOSSARY),
        ("TDF가 무슨 말이야?", ChatIntent.GLOSSARY),
        ("IRP에서 위험자산 몇 퍼센트까지 돼?", ChatIntent.ACCOUNT_RULE),
        ("DC형, IRP, 연금저축은 뭐가 달라?", ChatIntent.ACCOUNT_RULE),
        ("연금 처음 시작하는데 뭐부터 봐야 해?", ChatIntent.ACCOUNT_RULE),
        ("올해 받을 수 있는 연금세액공제가 궁금해.", ChatIntent.PENSION_TAX),
        ("연금저축 처음인데 세액공제 얼마야?", ChatIntent.PENSION_TAX),
        ("요즘 증시 뉴스 알려줘", ChatIntent.NEWS),
        ("내 상황에 맞는 연금저축전략을 알려줘.", ChatIntent.EDUCATIONAL_PORTFOLIO),
    ],
)
def test_getting_started_does_not_capture_existing_intents(
    message: str, expected: ChatIntent
) -> None:
    # 시작점 판정은 기존 인텐트와 용어 판정이 모두 받지 않은 뒤에만 적용한다.
    plan = plan_question(message)

    assert plan.intent is expected


def test_answer_offers_planner_and_question_cards_together() -> None:
    response = _service().ask(ChatRequest(message="뭐부터 해야 할지 모르겠어"))

    assert response.intent is ChatIntent.GETTING_STARTED
    assert response.data_mode == GETTING_STARTED_DATA_MODE
    # 튜토리얼과 추천 질문 중 하나를 고르게 한다. 한쪽만 주면 선택지가 없다.
    follow_up_ids = [item.follow_up_id for item in response.suggested_follow_ups]
    assert _PLANNER_FOLLOW_UP_ID in follow_up_ids
    others = [item for item in follow_up_ids if item != _PLANNER_FOLLOW_UP_ID]
    assert len(others) >= 2


def test_getting_started_avoids_product_recommendation() -> None:
    response = getting_started_response()

    assert response.limitations
    assert "권유" not in response.answer
    assert "추천" not in response.answer


def test_follow_up_messages_stay_answerable() -> None:
    # 카드를 누르면 다시 답이 나와야 한다. 계산기 카드는 프론트가 화면을 연다.
    answerable = {
        ChatIntent.GLOSSARY,
        ChatIntent.ACCOUNT_RULE,
        ChatIntent.PENSION_TAX,
        ChatIntent.EDUCATIONAL_PORTFOLIO,
    }
    for item in getting_started_response().suggested_follow_ups:
        if item.follow_up_id == _PLANNER_FOLLOW_UP_ID:
            continue
        plan = plan_question(item.message)

        assert plan.intent in answerable, f"{item.follow_up_id} 후속 질문이 막힘"
        assert plan.blocked_reason is None
