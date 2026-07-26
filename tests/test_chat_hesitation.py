"""Coverage for hesitation questions that used to hit the safe fallback.

타깃 사용자는 제도를 몰라서만 멈추지 않는다. 망설임이 담긴 질문에서도 멈춘다.
이 테스트는 그런 질문이 폴백으로 떨어지지 않는지, 그리고 답이 위로가 아니라
승인된 사실로 이어지는지를 고정한다.
"""

import pytest

from backend.app.chat.handlers.hesitation import (
    HESITATION_ANSWERS,
    OPENERS,
    HesitationAnswer,
    hesitation_answer_by_id,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import BlockedReason, plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService

# 미래를 안심시키거나 감정을 단정하는 표현은 쓰지 않는다.
_FORBIDDEN_PHRASES = (
    "괜찮아질",
    "걱정 마",
    "걱정하지 마",
    "불안하시죠",
    "안심하세요",
    "분명히",
    "반드시 오를",
    "손해 안 봐",
)


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    ("message", "expected_answer"),
    [
        ("손실 나면 어떡하지?", "loss_fear"),
        ("돈 잃을까봐 무서워", "loss_fear"),
        ("투자가 무서워요", "loss_fear"),
        ("원금 까먹으면 어쩌지?", "loss_fear"),
        ("다 잃을 수도 있어?", "loss_fear"),
        ("떨어지면 어떻게 해?", "market_drop_fear"),
        ("폭락하면 어떡해?", "market_drop_fear"),
        ("마이너스 났는데 어떡해?", "market_drop_fear"),
        ("지금 시장 불안한데 괜찮아?", "market_drop_fear"),
        ("지금 넣기엔 비싼 것 같아", "market_drop_fear"),
        ("지금 시작해도 늦지 않았나?", "too_late_to_start"),
        ("40대인데 너무 늦었나?", "too_late_to_start"),
        ("50대인데 지금 해도 돼?", "too_late_to_start"),
        ("나이가 많은데 의미 있나?", "too_late_to_start"),
        ("언제 시작하는 게 좋아?", "too_late_to_start"),
        ("조금 더 기다렸다 할까?", "too_late_to_start"),
        ("돈이 적은데 시작해도 돼?", "small_amount_start"),
        ("월급이 적어도 할 수 있어?", "small_amount_start"),
        ("1만원으로도 되나?", "small_amount_start"),
        ("남들은 얼마나 모았어?", "peer_comparison"),
        ("내 또래는 얼마나 넣어?", "peer_comparison"),
        ("평균이 얼마야?", "peer_comparison"),
        ("나만 늦은 건가?", "peer_comparison"),
        ("다들 어디에 투자해?", "peer_comparison"),
        ("친구는 수익 났다는데", "peer_comparison"),
        ("남들보다 못하면 어떡해?", "peer_comparison"),
        ("내가 잘하고 있는 건가?", "doing_well_check"),
        ("이 정도면 괜찮은 거야?", "doing_well_check"),
        ("내 수익률 낮은 것 같아", "doing_well_check"),
    ],
)
def test_hesitation_questions_are_answered_not_deflected(
    message: str, expected_answer: str
) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.HESITATION_SUPPORT
    assert plan.hesitation_answer_id == expected_answer
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    "answer", HESITATION_ANSWERS, ids=lambda item: item.answer_id
)
def test_every_hesitation_answer_opens_without_assuming_emotion(
    answer: HesitationAnswer,
) -> None:
    # 감정을 단정하는 대신 질문을 정상화하거나 타당성을 인정하며 연다.
    opener = OPENERS[answer.opener_key]

    assert opener in OPENERS.values()
    assert "많이들" in opener or "짚어볼 만한" in opener


@pytest.mark.parametrize(
    "answer", HESITATION_ANSWERS, ids=lambda item: item.answer_id
)
def test_every_hesitation_answer_carries_a_caveat(
    answer: HesitationAnswer,
) -> None:
    stored = hesitation_answer_by_id(answer.answer_id)

    assert stored is not None
    assert stored.caveat
    assert stored.follow_ups


@pytest.mark.parametrize(
    "message",
    [
        "손실 나면 어떡하지?",
        "지금 시작해도 늦지 않았나?",
        "남들은 얼마나 모았어?",
        "내가 잘하고 있는 건가?",
        "1만원으로도 되나?",
        "지금 넣기엔 비싼 것 같아",
    ],
)
def test_hesitation_answers_cite_evidence_and_route_forward(message: str) -> None:
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.HESITATION_SUPPORT
    assert response.sources
    assert response.suggested_follow_ups
    assert response.limitations
    assert "다만" in response.answer


@pytest.mark.parametrize(
    "message",
    [
        "손실 나면 어떡하지?",
        "지금 시작해도 늦지 않았나?",
        "남들은 얼마나 모았어?",
        "지금 넣기엔 비싼 것 같아",
        "투자가 무서워요",
        "이 정도면 괜찮은 거야?",
    ],
)
def test_hesitation_answers_never_promise_comfort(message: str) -> None:
    # 위로로 끝내거나 미래를 안심시키면 규정 위반이다.
    response = _service().ask(ChatRequest(message=message))

    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in response.answer


def test_peer_comparison_uses_group_statistics_with_numeric_evidence() -> None:
    # 수치를 쓰려면 근거가 따라붙어야 한다. 시장 통계를 개인 수익률로
    # 대신 쓰지 않는다는 한계도 함께 말한다.
    response = _service().ask(ChatRequest(message="남들은 얼마나 모았어?"))

    assert "501.4" in response.answer
    assert "19.5" in response.answer
    assert response.numeric_evidence
    assert response.sources
    assert "집단 통계" in response.answer


def test_loss_fear_answer_explains_product_types_instead_of_reassuring() -> None:
    response = _service().ask(ChatRequest(message="손실 나면 어떡하지?"))

    assert "원리금보장" in response.answer
    assert "실적배당" in response.answer
    assert "손실이 나지 않는다고 말씀드릴 수는 없어요" in response.answer


def test_timing_question_declines_to_call_the_market() -> None:
    response = _service().ask(ChatRequest(message="지금 넣기엔 비싼 것 같아"))

    assert "지나고 나서야" in response.answer
    assert "예측하지 않아요" in response.answer


@pytest.mark.parametrize(
    "message",
    [
        "비트코인 지금 떨어지면 어떡해?",
        "부동산 폭락하면 어떡해?",
    ],
)
def test_non_pension_assets_keep_the_safe_fallback(message: str) -> None:
    # 연금 밖 자산을 지목하면 기존 경계를 유지한다.
    plan = plan_question(message)

    assert plan.intent is not ChatIntent.HESITATION_SUPPORT


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("요즘 뉴스 보면 무서운데", ChatIntent.NEWS),
        ("변동성이 뭐야?", ChatIntent.GLOSSARY),
        ("분산투자를 왜 해야 해?", ChatIntent.INVESTING_PRINCIPLE),
        ("뭐 사야 돼?", ChatIntent.OUT_OF_SCOPE),
    ],
)
def test_neighbouring_routes_are_untouched(
    message: str, expected_intent: ChatIntent
) -> None:
    # 망설임 인텐트가 이웃 라우팅을 삼키면 회귀다.
    plan = plan_question(message)

    assert plan.intent is expected_intent
    assert plan.hesitation_answer_id is None


def test_personal_advice_still_blocked_after_hesitation_routing() -> None:
    plan = plan_question("뭐 사야 돼?")

    assert plan.blocked_reason is BlockedReason.PERSONAL_ALLOCATION_ADVICE