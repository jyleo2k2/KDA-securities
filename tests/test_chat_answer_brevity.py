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
    """프롬프트는 표시 상한을 알리고, 스키마는 그보다 넉넉히 받는다.

    두 값을 같게 두면 상한을 조금 넘긴 출력이 구조화 검증에서 먼저 거부돼
    문장 경계 트림에 도달하지 못하고 통째로 폴백된다(실측: 355자 입력이
    재시도 1회 뒤 결정론 원문으로 교체됨).
    """

    from backend.app.chat.narrator import (
        NARRATION_SCHEMA_MAX_CHARS,
        SYSTEM_PROMPT,
        NarrationOutput,
    )

    assert f"{NARRATION_MAX_CHARS}자 이내" in SYSTEM_PROMPT
    assert (
        NarrationOutput.model_fields["narration"].metadata[0].max_length
        == NARRATION_SCHEMA_MAX_CHARS
    )
    assert NARRATION_SCHEMA_MAX_CHARS > NARRATION_MAX_CHARS


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        # 상한 안이면 손대지 않는다.
        ("짧은 문장이에요.", "짧은 문장이에요."),
        # 넘치면 마지막 완결 문장까지만 남긴다.
        ("첫 문장이에요. " + "가" * 350 + "라고 해요.", "첫 문장이에요."),
        # 첫 문장부터 넘치면 남길 것이 없다(호출부가 폴백을 탄다).
        ("가" * 400 + "라고 해요.", ""),
    ),
)
def test_trim_keeps_only_completed_sentences(text: str, expected: str) -> None:
    """상한 초과분은 문장 경계에서만 덜어낸다. 문장 중간을 자르지 않는다."""

    from backend.app.chat.narrator import _trim_to_sentence_boundary

    assert _trim_to_sentence_boundary(text, NARRATION_MAX_CHARS) == expected


def test_long_narration_keeps_polite_sentence_instead_of_falling_back() -> None:
    """상한을 조금 넘긴 답변은 폐기되지 않는다.

    폐기하면 해요체 설명이 '-한다'체 근거 원문으로 교체돼 한 대화 안에서
    말투가 튄다. 완결 문장이 하나라도 있으면 그것을 살린다.
    """

    import json

    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from backend.app.chat.narrator import ClaudeNarrator

    base = _service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))
    narration = "IRP 위험자산 한도는 70%예요. " + "덧붙이면 " * 90 + "그렇답니다."
    assert len(narration) > NARRATION_MAX_CHARS

    narrator = ClaudeNarrator(api_key="test-key", model="test-model")
    calls: list[int] = []

    def respond(messages, info) -> ModelResponse:
        calls.append(1)
        return ModelResponse(
            parts=[
                TextPart(json.dumps({"narration": narration}, ensure_ascii=False))
            ]
        )

    with narrator.agent.override(model=FunctionModel(respond)):
        narrated = narrator.narrate(base)

    assert narrated.narration_mode == "claude_verified"
    assert narrated.answer == "IRP 위험자산 한도는 70%예요."
    assert len(narrated.answer) <= NARRATION_MAX_CHARS
    # 스키마 상한이 표시 상한과 같으면 재시도가 붙는다. 한 번만 호출해야 한다.
    assert len(calls) == 1


def test_length_fallback_uses_its_own_reason_code(caplog) -> None:
    """길이 초과 폴백과 호출 장애 폴백을 로그에서 구분한다."""

    import json
    import logging

    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from backend.app.chat.narrator import ClaudeNarrator

    base = _service().ask(ChatRequest(message="IRP 위험자산 한도를 알려줘"))
    # 종결 부호가 없어 트림할 지점이 없는 초장문.
    narration = "가" * (NARRATION_MAX_CHARS + 50)

    narrator = ClaudeNarrator(api_key="test-key", model="test-model")

    def respond(messages, info) -> ModelResponse:
        return ModelResponse(
            parts=[
                TextPart(json.dumps({"narration": narration}, ensure_ascii=False))
            ]
        )

    with (
        caplog.at_level(logging.WARNING, logger="backend.app.chat.narrator"),
        narrator.agent.override(model=FunctionModel(respond)),
    ):
        narrated = narrator.narrate(base)

    assert narrated.narration_mode == "deterministic"
    assert "narration_too_long" in caplog.text
    assert "agent_error" not in caplog.text


@pytest.mark.parametrize(
    "message",
    (
        "IRP 위험자산 한도를 알려줘",
        "연금저축 세액공제 한도 알려줘",
        "중도인출 가능해?",
        "연금 수령 요건이 어떻게 돼?",
        "회사 옮기면 퇴직연금 어떻게 돼?",
        "다른 증권사로 옮기려면 상품 팔아야 해?",
        "한꺼번에 다 받아도 돼?",
        "연금저축 계좌 어디서 만들어?",
        "연금저축에 어떤 상품 담을 수 있어?",
        "담보대출 받을 수 있어?",
    ),
)
def test_knowledge_answer_leads_with_polite_conclusion(message: str) -> None:
    """근거 원문이 그대로 첫 문장이 되면 말투가 튄다.

    승인 문서 원문은 '-한다'체이고 고쳐 쓰면 출처 칩과 화면 문장이 어긋난다.
    그래서 원문은 보존하고 해요체 결론을 앞에 얹는다(두괄식).
    """

    response = _service().ask(ChatRequest(message=message))

    assert response.data_mode == "verified_knowledge"
    first_line = response.answer.splitlines()[0].rstrip()
    assert first_line.endswith(("요.", "요", "예요.", "에요."))


def test_collateral_loan_does_not_reuse_withdrawal_conclusion() -> None:
    """같은 주제라도 결론이 다르면 다른 문장을 써야 한다."""

    response = _service().ask(ChatRequest(message="담보대출 받을 수 있어?"))

    assert response.answer.startswith("담보대출과 중도인출은 다른 제도")
