import pytest

from backend.app.api.chat import _format_salutation
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.pension_account_overview import PENSION_TOPIC_DEFER_NOTICE
from backend.app.chat.query_planner import AccountRuleTopic, plan_question
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
        "연금계좌 규칙 알려줘",
        "연금계좌규칙 알려줘",
        "연금계좌가 뭐야?",
        "연금계좌 전체적으로 정리해줘",
    ),
)
def test_natural_overview_questions_select_overview(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.account_rule_topic is AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW


def test_specific_risk_rule_does_not_expand_to_overview() -> None:
    plan = plan_question("IRP 위험자산 한도 알려줘")

    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.account_rule_topic is None


def test_recommended_account_comparison_uses_deterministic_overview() -> None:
    message = "DC형, IRP, 연금저축은 뭐가 달라?"
    plan = plan_question(message)
    response = _service().ask(ChatRequest(message=message))
    section_text = "\n".join(section.content for section in response.sections)

    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.account_rule_topic is AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW
    assert response.data_mode == "verified_pension_account_overview"
    assert "IRP" in section_text
    assert "원칙적으로 적립금의 70%까지" in section_text
    assert response.sources


@pytest.mark.parametrize(
    ("message", "topic"),
    (
        ("연금은 언제부터 받을 수 있어?", AccountRuleTopic.PENSION_RECEIPT_START),
        ("연금으로 받을 때 세금은?", AccountRuleTopic.PENSION_RECEIPT_TAX),
        (
            "사적연금 1,500만 원 기준이 뭐야?",
            AccountRuleTopic.PRIVATE_PENSION_THRESHOLD,
        ),
        ("IRP를 중도인출하면 어떻게 돼?", AccountRuleTopic.NON_PENSION_WITHDRAWAL),
        ("연금계좌를 해지하면?", AccountRuleTopic.NON_PENSION_WITHDRAWAL),
        (
            "연금계좌를 중도에 해지하면 어떻게 돼?",
            AccountRuleTopic.NON_PENSION_WITHDRAWAL,
        ),
        ("IRP 중도해지 세금은?", AccountRuleTopic.NON_PENSION_WITHDRAWAL),
    ),
)
def test_deferred_topics_are_routed_separately(
    message: str, topic: AccountRuleTopic
) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.account_rule_topic is topic


def test_explicit_withdrawal_calculation_keeps_engine_route() -> None:
    plan = plan_question("연금저축 3천만 원과 IRP 5천만 원 해지 세금 계산해줘")

    assert plan.intent is ChatIntent.PENSION_TAX
    assert plan.requests_withdrawal_tax is True
    assert plan.account_rule_topic is None


def test_overview_response_is_structured_without_generic_number_cards() -> None:
    response = _service().ask(ChatRequest(message="연금계좌 규칙 알려줘"))
    section_text = "\n".join(section.content for section in response.sections)

    assert response.intent is ChatIntent.ACCOUNT_RULE
    assert response.data_mode == "verified_pension_account_overview"
    assert response.narration_mode == "deterministic"
    assert response.salutation is None
    assert [section.title for section in response.sections] == [
        "핵심 숫자부터",
        "연금저축·IRP·DC형의 차이",
        "세액공제 규칙",
        "1,800만 원을 모두 넣으면 900만 원 초과분은 어떻게 되나",
        "ISA 만기자금 이전 특례",
        "실제 관리할 때 중요한 원칙",
    ]
    assert all(section.blocks for section in response.sections)
    assert response.numeric_evidence == []
    assert all(
        source.data_boundary == "verified_knowledge" for source in response.sources
    )
    assert all(source.locator.startswith("https://") for source in response.sources)
    assert {
        evidence_id
        for section in response.sections
        for evidence_id in section.evidence_ids
    }.issubset({source.evidence_id for source in response.sources})
    for expected in (
        "1,800만 원",
        "900만 원",
        "600만 원",
        "16.5%",
        "ISA",
        "60일",
        "IRP 또는 DC형 본인 추가납입만으로 900만 원",
    ):
        assert expected in section_text

    block_kinds = {
        block.kind.value for section in response.sections for block in section.blocks
    }
    assert block_kinds == {"callout", "paragraph", "bullets", "table"}
    for hidden_detail in (
        "55세",
        "연금수령한도",
        "70세 미만",
        "사적연금",
        "중도인출",
        "해지",
    ):
        assert hidden_detail not in section_text


def test_overview_keeps_plain_content_for_legacy_clients() -> None:
    response = _service().ask(ChatRequest(message="연금계좌 규칙 알려줘"))

    assert all(section.content.strip() for section in response.sections)
    assert "연금저축" in response.sections[1].content
    assert "ISA" in response.sections[4].content


@pytest.mark.parametrize(
    ("message", "expected_title"),
    (
        ("연금은 언제부터 받을 수 있어?", "연금수령을 시작하는 일반 요건"),
        ("연금으로 받을 때 세금은?", "연금으로 받을 때의 일반 과세 구조"),
        ("사적연금 1,500만 원 기준이 뭐야?", "연간 사적연금 1,500만 원 기준"),
        ("IRP를 중도인출하면 어떻게 돼?", "중도인출·해지의 일반 원칙"),
    ),
)
def test_deferred_topic_response_is_deterministic_and_defers_personal_judgment(
    message: str, expected_title: str
) -> None:
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.ACCOUNT_RULE
    assert response.data_mode == "verified_pension_account_deferred_topic"
    assert response.narration_mode == "deterministic"
    assert response.salutation is None
    assert [section.title for section in response.sections] == [expected_title]
    assert response.numeric_evidence == []
    assert response.limitations[-1] == PENSION_TOPIC_DEFER_NOTICE
    assert response.sources


def test_specific_risk_rule_keeps_existing_behavior() -> None:
    response = _service().ask(ChatRequest(message="IRP 위험자산 한도 알려줘"))

    assert response.data_mode == "verified_knowledge"
    assert "70%" in response.answer
    assert response.salutation is None


@pytest.mark.parametrize(
    ("nickname", "expected"),
    (
        ("김민재", "김민재님"),
        ("김민재 님", "김민재님"),
        ("김민재님", "김민재님"),
        (None, "고객님"),
        ("이름\n삽입", "고객님"),
    ),
)
def test_salutation_is_normalized_once(nickname: str | None, expected: str) -> None:
    assert _format_salutation(nickname) == expected
