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
        "OTP는 123456이야",
        "abcd1234가 비밀번호야",
    ):
        response = chatbot.ask(ChatRequest(message=message))
        assert response.data_mode == "blocked"
        assert "개인" in response.answer

    assert knowledge.queries == []


def test_educational_otp_question_is_not_treated_as_a_secret() -> None:
    plan = plan_question("IRP에서 OTP가 뭐야?")

    assert plan.blocked_reason is None
    assert plan.intent == ChatIntent.ACCOUNT_RULE


def test_multiple_accounts_are_preserved_for_rule_comparison() -> None:
    plan = plan_question("DC와 IRP 차이를 알려줘")

    assert plan.intent == ChatIntent.ACCOUNT_RULE
    assert plan.account_types == (AccountType.DC, AccountType.IRP)
    assert plan.blocked_reason is None


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


def test_order_and_future_requests_do_not_reach_retrieval() -> None:
    knowledge = RecordingKnowledgeRepository()
    chatbot = _service(knowledge)

    future = chatbot.ask(ChatRequest(message="내년 IRP 수익률을 예측해줘"))
    order = chatbot.ask(ChatRequest(message="IRP 상품을 대신 매수해줘"))

    assert future.data_mode == "blocked"
    assert order.data_mode == "blocked"
    assert knowledge.queries == []
