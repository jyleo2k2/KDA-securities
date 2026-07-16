import pytest

from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import BlockedReason, plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import AccountType


class RecordingKnowledgeRepository:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_knowledge(self, query: str, *, limit: int = 8):
        self.queries.append(query)
        return []


def _service(knowledge: RecordingKnowledgeRepository) -> ChatService:
    return ChatService(
        knowledge=knowledge,
        scenarios=LocalScenarioRepository(),
    )


def test_sensitive_values_are_blocked_before_retrieval() -> None:
    knowledge = RecordingKnowledgeRepository()
    chatbot = _service(knowledge)

    for message in (
        "주민등록번호 900101-1234567로 IRP를 확인해줘",
        "계좌번호는 123-456-789012야",
        "123-456-789012가 계좌번호야",
        "비밀번호 abc123로 IRP를 확인해줘",
        "abcd1234가 비밀번호야",
        "OTP는 123456이야",
        "654321이 O T P야",
        "보안 카드 번호 1234로 확인해줘",
        "4321이 보안카드 번호야",
    ):
        response = chatbot.ask(ChatRequest(message=message))
        assert response.data_mode == "blocked"
        assert "개인" in response.answer

    assert knowledge.queries == []


@pytest.mark.parametrize(
    "message",
    (
        "제 전화번호 010-1234-5678로 상담 내용을 보내줘",
        "my.name@example.com 계정의 IRP를 확인해줘",
        "카드번호 4111-1111-1111-1111로 결제해줘",
        "api key sk-abcdefghijklmnop123456을 등록해줘",
    ),
)
def test_dlp_extension_blocks_contact_payment_and_secret_values(message: str) -> None:
    knowledge = RecordingKnowledgeRepository()
    response = _service(knowledge).ask(ChatRequest(message=message))

    assert response.data_mode == "blocked"
    assert knowledge.queries == []


@pytest.mark.parametrize(
    "message",
    (
        "IRP에서 OTP가 뭐야?",
        "보안카드 번호는 왜 필요한가요?",
        "계좌번호는 어디서 확인해?",
        "비밀번호를 안전하게 관리하는 원칙을 알려줘",
    ),
)
def test_educational_security_question_is_not_treated_as_a_secret(
    message: str,
) -> None:
    plan = plan_question(message)

    assert plan.blocked_reason != BlockedReason.SENSITIVE_INFORMATION


def test_multiple_accounts_are_preserved_for_rule_comparison() -> None:
    plan = plan_question("DC와 IRP 차이를 알려줘")

    assert plan.intent == ChatIntent.ACCOUNT_RULE
    assert plan.account_types == (AccountType.DC, AccountType.IRP)
    assert plan.blocked_reason is None


def test_personalized_pension_tax_request_selects_both_calculations() -> None:
    plan = plan_question(
        "연금저축과 IRP 세액공제 혜택과 중도해지 세금을 알려줘"
    )

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is True
    assert plan.requests_withdrawal_tax is True


@pytest.mark.parametrize(
    ("message", "tax_credit", "withdrawal"),
    (
        ("연금계좌 세액공제 한도를 계산해줘", True, False),
        ("연금저축 연금외수령 과세액을 알려줘", False, True),
    ),
)
def test_pension_tax_request_selects_only_requested_tool(
    message: str,
    tax_credit: bool,
    withdrawal: bool,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is tax_credit
    assert plan.requests_withdrawal_tax is withdrawal


def test_named_mock_scenario_wins_over_tax_credit_word() -> None:
    plan = plan_question("세액공제 후 미운용 시나리오를 진단해줘")

    assert plan.intent == ChatIntent.MOCK_PORTFOLIO


def test_combined_cap_request_is_marked_for_account_separation() -> None:
    plan = plan_question(
        "DC와 IRP와 연금저축을 합쳐서 위험자산 70%를 적용하면 돼?"
    )

    assert plan.intent == ChatIntent.ACCOUNT_RULE
    assert plan.combines_account_rules is True
    assert plan.account_types == (
        AccountType.DC,
        AccountType.IRP,
        AccountType.PENSION_SAVINGS,
    )


@pytest.mark.parametrize(
    "message",
    (
        "DC와 IRP를 묶어서 위험자산 한도를 계산해줘",
        "DC와 IRP 위험자산 규칙을 전체로 적용하면 돼?",
        "DC와 IRP를 한꺼번에 70% 한도로 보면 돼?",
        "DC와 IRP 둘을 같이 한도 계산해줘",
    ),
)
def test_combined_account_wording_is_detected(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.ACCOUNT_RULE
    assert plan.combines_account_rules is True


def test_multiple_account_disclosures_require_one_account_at_a_time() -> None:
    plan = plan_question("DC와 IRP 사업자 수익률을 비교해줘")

    assert plan.intent == ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason == BlockedReason.ACCOUNT_SELECTION_REQUIRED


def test_news_topic_and_requested_count_are_canonical() -> None:
    samsung = plan_question("삼성전자 가장 최근 뉴스 하나 찾아줘")
    pension = plan_question("퇴직연금 최신 뉴스 3건 알려줘")

    assert samsung.news_query == "삼성전자"
    assert samsung.max_results == 1
    assert pension.news_query == "퇴직연금"
    assert pension.max_results == 3


def test_news_command_removal_keeps_words_that_contain_news_terms() -> None:
    newskin = plan_question("뉴스킨 최신 뉴스")
    revival = plan_question("기사회생 뉴스")

    assert newskin.intent == ChatIntent.NEWS
    assert newskin.news_query == "뉴스킨"
    assert revival.intent == ChatIntent.NEWS
    assert revival.news_query == "기사회생"


def test_order_and_future_requests_do_not_reach_retrieval() -> None:
    knowledge = RecordingKnowledgeRepository()
    chatbot = _service(knowledge)

    future = chatbot.ask(ChatRequest(message="내년 IRP 수익률을 예측해줘"))
    order = chatbot.ask(ChatRequest(message="IRP 상품을 대신 매수해줘"))

    assert future.data_mode == "blocked"
    assert order.data_mode == "blocked"
    assert knowledge.queries == []
