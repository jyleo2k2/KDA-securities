"""화면에 한 번에 쏟아지는 분량을 묶어 두는 회귀 테스트.

계좌 소개 답변이 규칙 전문으로 되돌아가거나, 카드 본문이 다시 문단으로
길어지면 여기서 걸린다.
"""

import pytest

from backend.app.chat.cards import build_suggested_follow_ups
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest, ChatResponse
from backend.app.chat.narrator import NARRATION_MAX_CHARS
from backend.app.chat.query_planner import plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService

# 사용자가 한 화면에서 읽는 분량은 본문과 카드를 합친 값이다. 규칙 전문
# 응답은 3,300자를 넘었고, 그 회귀를 막는 것이 이 상한의 목적이다.
_MAX_VISIBLE_CHARS = 900


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


def _visible_length(response: ChatResponse) -> int:
    return len(response.answer) + sum(
        len(section.plain_text()) for section in response.sections
    )


@pytest.mark.parametrize(
    "message",
    (
        "연금이 뭐야",
        "연금이 뭔지 알려줘",
        "연금이란 무엇인가요",
        "IRP랑 연금저축계좌 차이를 알려줘",
        "DC형, IRP, 연금저축은 뭐가 달라?",
        "IRP가 뭐야",
    ),
)
def test_account_brief_stays_within_one_screen(message: str) -> None:
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.ACCOUNT_RULE
    assert response.data_mode == "verified_pension_account_brief"
    assert _visible_length(response) <= _MAX_VISIBLE_CHARS


@pytest.mark.parametrize(
    "message",
    ("연금이 뭐야", "연금이 뭔지 알려줘", "연금이란 무엇인가요"),
)
def test_definition_question_answers_what_pension_is(message: str) -> None:
    response = _service().ask(ChatRequest(message=message))
    section_text = "\n".join(section.plain_text() for section in response.sections)

    # 규칙 나열이 아니라 제도의 뜻으로 답하고, 우리가 다루는 세 계좌로 잇는다.
    assert "나눠 받는 돈" in response.answer
    assert "연금저축·IRP·DC형" in response.answer
    assert "연금저축펀드" in section_text
    assert "IRP" in section_text
    assert "DC형" in section_text


def test_named_account_question_keeps_rule_answer() -> None:
    """계좌를 지목한 물음까지 정의로 바뀌면 안 된다."""

    response = _service().ask(ChatRequest(message="IRP가 뭐야"))

    assert "나눠 받는 돈" not in response.answer


def test_account_brief_offers_details_as_follow_ups() -> None:
    response = _service().ask(ChatRequest(message="연금이 뭐야"))
    follow_ups = build_suggested_follow_ups(response)

    assert [item.follow_up_id for item in follow_ups] == [
        "brief_to_tax",
        "brief_to_risk_cap",
        "brief_to_edu",
    ]
    # 후속 질문이 같은 소개 답변으로 되돌아오면 사용자는 제자리를 돈다.
    for follow_up in follow_ups:
        plan = plan_question(follow_up.message)
        assert plan.blocked_reason is None
        assert plan.intent is not ChatIntent.OUT_OF_SCOPE


def test_narration_limit_is_shared_by_prompt_and_schema() -> None:
    from backend.app.chat.narrator import SYSTEM_PROMPT, NarrationOutput

    assert f"{NARRATION_MAX_CHARS}자 이내" in SYSTEM_PROMPT
    assert (
        NarrationOutput.model_fields["narration"].metadata[0].max_length
        == NARRATION_MAX_CHARS
    )
