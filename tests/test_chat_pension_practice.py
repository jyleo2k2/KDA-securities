"""Everyday-wording coverage for pension account practice questions."""

import pytest

from backend.app.chat.handlers._shared import _knowledge_topic
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import BlockedReason, plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService

_DECLINE_ANSWER_MARKERS = ("정해드리지는 않아요", "낫다고 말씀드리지는 않아요")


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


@pytest.mark.parametrize(
    "message",
    [
        "계좌 여러 개 만들어도 돼?",
        "계좌 만들 때 뭐 준비해?",
        "돈 없을 때 한 달 걸러도 돼?",
        "1년에 한 번 몰아서 넣어도 돼?",
        "한도 넘게 넣으면 어떻게 돼?",
        "계좌 옮기면 상품 다 팔아야 해?",
        "연금 중간에 돈 필요하면 뺄 수 있어?",
        "급하게 돈 필요하면 담보대출도 돼?",
        "연금 상품 바꿀 수 있어?",
        "상품 바꾸면 수수료 들어?",
        "연말정산이랑 연금이 무슨 상관이야?",
        "한 번에 다 받아도 돼?",
    ],
)
def test_everyday_wording_reaches_account_rule(message: str) -> None:
    # 타깃 사용자는 제도 용어 대신 일상어로 묻는다. 차단되면 안 된다.
    plan = plan_question(message)

    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    ("message", "expected_topic"),
    [
        ("계좌 여러 개 만들어도 돼?", "account_opening"),
        ("계좌 만들 때 뭐 준비해?", "account_opening"),
        ("연금저축계좌 어디서 만들어?", "account_opening"),
        ("돈 없을 때 한 달 걸러도 돼?", "tax_limit"),
        ("1년에 한 번 몰아서 넣어도 돼?", "tax_limit"),
        ("한도 넘게 넣으면 어떻게 돼?", "tax_limit"),
        ("IRP랑 연금저축 합쳐서 한도가 얼마야?", "tax_limit"),
        ("연말정산이랑 연금이 무슨 상관이야?", "tax_limit"),
        ("연금 중간에 돈 필요하면 뺄 수 있어?", "withdrawal_requirements"),
        ("급하게 돈 필요하면 담보대출도 돼?", "withdrawal_requirements"),
        ("연금 상품 바꿀 수 있어?", "investable_assets"),
        ("상품 바꾸면 수수료 들어?", "investable_assets"),
        ("연금계좌 만들면 바로 투자할 수 있어?", "investable_assets"),
        ("한 번에 다 받아도 돼?", "receipt_tax"),
        ("회사 옮기면 퇴직연금 어떻게 돼?", "retirement_benefit_transfer"),
        ("DC형에서 IRP로 옮기려면 어떻게 해?", "in_kind_transfer"),
        ("다른 증권사로 연금계좌 옮길 수 있어?", "in_kind_transfer"),
        ("계좌 옮기면 상품 다 팔아야 해?", "in_kind_transfer"),
    ],
)
def test_practice_questions_pin_the_right_document(
    message: str, expected_topic: str
) -> None:
    # 주제를 못 박지 않으면 검색 점수만으로 엉뚱한 문서가 뽑힌다.
    plan = plan_question(message)

    assert _knowledge_topic(message, plan)[0] == expected_topic


@pytest.mark.parametrize(
    ("message", "must_contain"),
    [
        ("회사 옮기면 퇴직연금 어떻게 돼?", "IRP 계정"),
        ("다른 증권사로 연금계좌 옮길 수 있어?", "이전 대상"),
        ("연금 중간에 돈 필요하면 뺄 수 있어?", "법령상 사유"),
        ("연금계좌 만들면 바로 투자할 수 있어?", "개별 주식"),
    ],
)
def test_practice_answers_use_the_matching_evidence(
    message: str, must_contain: str
) -> None:
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.ACCOUNT_RULE
    assert response.sources
    body = response.answer + "\n".join(
        section.content for section in response.sections
    )

    assert must_contain in body


@pytest.mark.parametrize(
    ("message", "expected_reason"),
    [
        (
            "한 달에 얼마씩 넣는 게 좋아?",
            BlockedReason.CONTRIBUTION_AMOUNT_ADVICE,
        ),
        ("얼마나 넣어야 좋을까?", BlockedReason.CONTRIBUTION_AMOUNT_ADVICE),
        (
            "증권사랑 은행 중에 어디가 나아?",
            BlockedReason.PROVIDER_CHOICE_ADVICE,
        ),
    ],
)
def test_advice_questions_return_criteria_instead_of_a_pick(
    message: str, expected_reason: BlockedReason
) -> None:
    # 정답이 사람마다 다른 질문은 금액·회사를 고르지 않고 기준을 준다.
    plan = plan_question(message)

    assert plan.blocked_reason is expected_reason

    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.OUT_OF_SCOPE
    assert any(marker in response.answer for marker in _DECLINE_ANSWER_MARKERS)
    assert response.suggested_follow_ups
    assert response.limitations
    assert "추천" not in response.answer


@pytest.mark.parametrize(
    "message",
    [
        "연금계좌 세액공제 납입 한도를 알려줘",
        "연금저축 납입을 한 달 쉬어도 되나요?",
        "연금계좌에 어떤 상품을 담을 수 있어?",
        "DC형, IRP, 연금저축은 뭐가 달라?",
    ],
)
def test_advice_follow_up_cards_stay_answerable(message: str) -> None:
    # 되묻기 카드가 다시 막히면 대화가 끊긴다.
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is not ChatIntent.OUT_OF_SCOPE


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # 기존 라우팅 범위를 넓히지 않는다.
        (
            "IRP와 연금저축의 위험자산 한도 차이를 알려줘",
            ChatIntent.ACCOUNT_RULE,
        ),
        (
            "올해 연금저축에 600만원 넣으면 세액공제 얼마야?",
            ChatIntent.PENSION_TAX,
        ),
        ("요즘 반도체 ETF 뭐가 있어?", ChatIntent.ETF_THEME),
        ("채권이 뭐야?", ChatIntent.GLOSSARY),
        ("오늘 증시 뉴스 알려줘.", ChatIntent.NEWS),
        ("뭐부터 해야 할지 모르겠어", ChatIntent.GETTING_STARTED),
    ],
)
def test_existing_routes_keep_priority(
    message: str, expected: ChatIntent
) -> None:
    plan = plan_question(message)

    assert plan.intent is expected
