"""Strategy glossary regressions for the ten strategies shown in the app."""

import pytest

from backend.app.chat.handlers.strategy_glossary import (
    INVESTING_STRATEGIES,
    find_investing_strategy,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService

_FORBIDDEN_IMPLEMENTATION_WORDS = (
    "교육용",
    "목데이터",
    "목 데이터",
    "Mock",
    "mock",
    "가상",
    "샘플 데이터",
    "테스트용",
    "데모용",
    "시연용",
)


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    ("message", "expected_strategy_id"),
    [
        # 사용자가 실제로 친 문장. "머야"는 정규화가 "뭐야"로 되돌린다.
        ("탑다운 전략이 머야?", "topdown"),
        ("톱다운 전략이 뭐야?", "topdown"),
        ("바텀업 전략이 뭐야?", "bottomup"),
        ("팩터 전략 설명해줘", "factor"),
        ("바벨 전략이 뭐야", "barbell"),
        ("시장 베타 전략이 뭐야", "market-beta"),
        ("롱숏 전략이 뭐야", "longshort"),
        ("시장중립 전략이 뭐야", "longshort"),
        ("변동성 관리 전략이 뭐야", "volatility"),
        ("추세추종 전략 알려줘", "trend"),
        ("글로벌 매크로 전략이 뭐야", "trend"),
        ("테마 전략이 뭐야", "theme"),
    ],
)
def test_strategy_questions_route_to_strategy_glossary(
    message: str, expected_strategy_id: str
) -> None:
    # 화면에는 전략 설명이 있는데 챗봇만 몰라서 엉뚱한 답을 주던 회귀다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.STRATEGY_GLOSSARY
    assert plan.strategy_id == expected_strategy_id
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # 성향별 포트폴리오 전략 이름은 엔진이 계산한 안내가 답이다.
        ("코어 위성 전략이 뭐야?", ChatIntent.EDUCATIONAL_PORTFOLIO),
        (
            "성장 코어·위성 전략이 왜 나한테 맞아?",
            ChatIntent.EDUCATIONAL_PORTFOLIO,
        ),
        # 특정 테마를 지목하면 상품 카탈로그가 답이다.
        ("반도체 테마 ETF 추천해줘", ChatIntent.ETF_THEME),
        ("반도체 테마 전략이 뭐야?", ChatIntent.ETF_THEME),
        # "이벤트 드리븐"은 실시간 뉴스 기반 운용전략 안내가 이미 소유한
        # 어휘다. 개념 설명으로 가로채면 그 기능이 사라진다.
        ("이벤트드리븐 전략이 뭐야", ChatIntent.NEWS),
        # 기존 용어·원리 경로는 그대로 유지돼야 한다.
        ("ETF가 뭐야?", ChatIntent.GLOSSARY),
        ("리밸런싱을 왜 해?", ChatIntent.INVESTING_PRINCIPLE),
    ],
)
def test_strategy_glossary_does_not_capture_existing_intents(
    message: str, expected: ChatIntent
) -> None:
    plan = plan_question(message)

    assert plan.intent is expected
    assert plan.strategy_id is None


def test_bare_strategy_question_stays_unsupported() -> None:
    # 어떤 전략인지 특정할 수 없으면 아무 전략이나 골라 답하지 않는다.
    plan = plan_question("전략이 뭐야?")

    assert plan.strategy_id is None
    assert plan.intent is ChatIntent.OUT_OF_SCOPE


def test_strategy_answer_explains_account_application() -> None:
    response = _service().ask(ChatRequest(message="탑다운 전략이 머야?"))

    assert response.intent is ChatIntent.STRATEGY_GLOSSARY
    assert "탑다운 전략" in response.answer
    # 전략만 설명하고 끝내면 연금계좌에서 뭘 해야 할지 알 수 없다.
    assert "위험자산 한도" in response.answer
    assert response.limitations
    assert response.suggested_follow_ups


def test_every_strategy_is_answerable_and_bounded() -> None:
    for strategy in INVESTING_STRATEGIES:
        assert find_investing_strategy(strategy.strategy_id) is strategy
        text = " ".join(
            (
                strategy.summary,
                strategy.bucket,
                strategy.account_application,
                strategy.how_it_works,
            )
        )
        # 미래 수익 예측·확정 표현과 구현 표식은 사용자 문구에 들어가면 안 된다.
        assert "보장" not in text
        for word in _FORBIDDEN_IMPLEMENTATION_WORDS:
            assert word not in text


def test_related_terms_point_at_real_glossary_entries() -> None:
    from backend.app.chat.handlers.glossary import GLOSSARY_TERMS

    labels = {term.label for term in GLOSSARY_TERMS}
    for strategy in INVESTING_STRATEGIES:
        for label in strategy.related_terms:
            assert label in labels, f"{strategy.strategy_id}: {label}"
