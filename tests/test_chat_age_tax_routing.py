"""Routing regressions for beginner phrasing that omits domain vocabulary."""

import pytest

from backend.app.chat.models import ChatIntent
from backend.app.chat.query_planner import plan_question


@pytest.mark.parametrize(
    "message",
    [
        "35살인데 어떻게 배분해?",
        "35세인데 어떻게 배분해?",
        "35살인데 어떤 전략이 맞아?",
        "40살인데 어떻게 운용해?",
        "28살인데 어떻게 굴려야 해?",
        "52세인데 뭐가 좋아?",
        "45살인데 어떻게 투자해야 해?",
    ],
)
def test_age_based_allocation_questions_reach_portfolio(message: str) -> None:
    # 나이만 밝히고 운용 방법을 물어도 전략 안내로 이어져야 한다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.EDUCATIONAL_PORTFOLIO
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    "message",
    [
        "IRP에 900만원 넣으면 얼마 돌려받아?",
        "연금저축에 600만원 넣으면 얼마 돌려받아?",
        "300만원 납입하면 얼마 환급받아?",
        "한 달에 50만원 넣으면 세금 얼마나 아껴?",
    ],
)
def test_contribution_refund_questions_reach_pension_tax(message: str) -> None:
    # "세액공제"라는 말을 몰라도 납입액과 환급을 물으면 계산으로 가야 한다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("올해 연금저축에 600만원 넣으면 세액공제 얼마야?", ChatIntent.PENSION_TAX),
        ("연금저축을 중도 해지하면 세금 얼마야?", ChatIntent.PENSION_TAX),
        ("세액공제 얼마나 받아?", ChatIntent.PENSION_TAX),
        ("내 상황에 맞는 연금저축전략을 알려줘.", ChatIntent.EDUCATIONAL_PORTFOLIO),
        ("안정형이면 어떻게 굴려?", ChatIntent.EDUCATIONAL_PORTFOLIO),
        ("ETF가 뭐야?", ChatIntent.GLOSSARY),
        ("뭐부터 해야 할지 모르겠어", ChatIntent.GETTING_STARTED),
        ("DC형, IRP, 연금저축은 뭐가 달라?", ChatIntent.ACCOUNT_RULE),
        ("IRP 중도인출 되나요?", ChatIntent.ACCOUNT_RULE),
        ("오늘 증시 뉴스 알려줘.", ChatIntent.NEWS),
    ],
)
def test_existing_intents_are_not_captured(
    message: str, expected: ChatIntent
) -> None:
    plan = plan_question(message)

    assert plan.intent is expected


@pytest.mark.parametrize(
    "message",
    [
        "35살인데 결혼해야 할까?",
        "30살인데 집 사야 해?",
        "1000만원 있는데 뭐 살까?",
        "비트코인 지금 사도 돼?",
        "삼성전자 주가 오를까?",
        "내년 예상수익률을 알려줘",
    ],
)
def test_out_of_scope_questions_stay_blocked(message: str) -> None:
    # 나이·금액이 있어도 연금 밖 주제나 미래 예측은 계속 막아야 한다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.OUT_OF_SCOPE


def test_withdrawal_tax_keeps_priority_over_refund_shortcut() -> None:
    # 해지 맥락에서는 납입·환급 축약 규칙이 세액공제로 가로채면 안 된다.
    plan = plan_question("연금저축 600만원 중도 해지하면 세금 얼마 내?")

    assert plan.intent is ChatIntent.PENSION_TAX
    assert plan.requests_withdrawal_tax
