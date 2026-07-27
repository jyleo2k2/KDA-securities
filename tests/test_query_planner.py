import pytest

from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.query_planner import (
    BlockedReason,
    NewsScopeNotice,
    plan_question,
)
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.chat.suggested_prompts import SUGGESTED_CHAT_PROMPTS
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


def test_distribution_question_extracts_etf_code_without_selecting_a_product() -> None:
    plan = plan_question("069500 ETF 분배금 지급일과 재투자 기준 알려줘")

    assert plan.intent == ChatIntent.ETF_DISTRIBUTION
    assert plan.distribution_isu_code == "069500"


def test_distribution_question_without_code_stays_in_distribution_flow() -> None:
    plan = plan_question("ETF 배당금 지급일 알려줘")

    assert plan.intent == ChatIntent.ETF_DISTRIBUTION
    assert plan.distribution_isu_code is None


def test_distribution_reinvestment_input_is_parsed_only_when_complete() -> None:
    plan = plan_question(
        "069500 재투자 수량=10 기준가=30,000 "
        "기준일=2026-07-01 리밸런싱일=2026-07-31"
    )

    assert plan.intent == ChatIntent.ETF_DISTRIBUTION
    assert plan.distribution_reinvestment is not None
    assert plan.distribution_reinvestment.quantity == 10
    assert plan.distribution_reinvestment.reinvestment_price_krw == 30000


def test_incomplete_reinvestment_input_stays_in_distribution_flow() -> None:
    plan = plan_question("069500 재투자 수량=10")

    assert plan.intent == ChatIntent.ETF_DISTRIBUTION
    assert plan.distribution_reinvestment is None


@pytest.mark.parametrize(
    "message",
    (
        "DC형·IRP·연금저축은 각각 어떤 계좌야? 차이를 비교해줘",
        "연금저축 세액공제 한도를 알려줘",
        "IRP 중도해지 세금 구조를 알려줘",
        "연금계좌 수령 요건을 알려줘",
    ),
)
def test_informational_pension_questions_use_verified_knowledge(
    message: str,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.ACCOUNT_RULE
    assert plan.requests_tax_credit is False
    assert plan.requests_withdrawal_tax is False


def test_unrelated_tax_wording_does_not_enter_pension_rag() -> None:
    plan = plan_question("세금 제도가 뭐야?")

    assert plan.intent == ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason == BlockedReason.UNSUPPORTED


@pytest.mark.parametrize(
    "message",
    (
        "연금이 뭐야?",
        "연금 뭐야",
        "연금 종류 알려줘",
        "퇴직연금이 뭐야?",
        "연금 어떻게 시작해?",
        "연금 가입 어떻게 해?",
    ),
)
def test_explicit_pension_basics_questions_use_account_overview(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.ACCOUNT_RULE
    assert plan.account_rule_topic is not None
    assert plan.account_rule_topic.value == "pension_account_overview"
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    "message",
    (
        "오늘 밥 뭐 먹었어?",
        "비트코인 지금 사도 돼?",
        "청약 통장 어떻게 만들어?",
        "파이썬 for문 어떻게 써?",
        "노후 준비 어떻게 해야 해?",
        "돈 어떻게 모아?",
    ),
)
def test_non_pension_basics_questions_remain_unsupported(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is BlockedReason.UNSUPPORTED


def test_pension_order_request_stays_blocked_before_basics_routing() -> None:
    plan = plan_question("연금 사줘")

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is BlockedReason.ORDER_REQUEST


@pytest.mark.parametrize(
    ("message", "tax_credit", "withdrawal"),
    (
        ("연금저축 600만원 납입 시 세액공제액을 계산해줘", True, False),
        ("IRP 잔액 1,000만원 중도해지 과세액은 얼마야", False, True),
    ),
)
def test_pension_tax_engine_is_reserved_for_calculation_requests(
    message: str,
    tax_credit: bool,
    withdrawal: bool,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is tax_credit
    assert plan.requests_withdrawal_tax is withdrawal


def test_personalized_pension_tax_request_selects_both_calculations() -> None:
    plan = plan_question("연금저축과 IRP 세액공제 혜택과 중도해지 세금을 계산해줘")

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is True
    assert plan.requests_withdrawal_tax is True


def test_missed_tax_credit_follow_up_routes_to_tax_credit_calculation() -> None:
    plan = plan_question("내가 놓치고 있는 세액공제혜택을 알려줘")

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is True
    assert plan.requests_withdrawal_tax is False


def test_structured_tax_input_without_topic_selects_both_calculations() -> None:
    plan = plan_question("결과를 알려줘", structured_pension_tax=True)

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is True
    assert plan.requests_withdrawal_tax is True


@pytest.mark.parametrize(
    "message",
    (
        "연금저축 400만원 IRP 300만원이면 공제 얼마야?",
        "공제 얼마야?",
        "공제액 계산해줘",
    ),
)
def test_abbreviated_credit_wording_requests_only_tax_credit(message: str) -> None:
    # "세액"을 생략한 "공제 얼마야?" 축약은 세액공제 계산만 요청해야 한다.
    # 토픽 미인식 시 tax_credit·withdrawal을 모두 켜는 구조화 입력 폴백으로
    # 넘어가면 내레이터가 인출 슬롯을 재구성하지 못해 폴백한다(실측 확인).
    plan = plan_question(message, structured_pension_tax=True)

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is True
    assert plan.requests_withdrawal_tax is False


@pytest.mark.parametrize(
    "message",
    (
        "연금저축 중도해지하면 공제 못 받아?",
        "소득공제랑 세액공제 차이가 뭐야?",
    ),
)
def test_bare_credit_word_without_calculation_signal_is_not_tax_credit(
    message: str,
) -> None:
    # "공제"가 계산·금액 신호 없이 등장하면 세액공제 계산으로 오분류하지 않는다.
    plan = plan_question(message)

    assert plan.requests_tax_credit is False


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


@pytest.mark.parametrize(
    ("message", "expected_intent", "tax_credit", "withdrawal"),
    (
        ("내 계좌 세액공제 계산해줘", ChatIntent.PENSION_TAX, True, False),
        ("내 계좌 중도해지 세금 얼마야", ChatIntent.PENSION_TAX, False, True),
        ("세액공제 계산해줘", ChatIntent.PENSION_TAX, True, False),
        ("내 계좌 진단해줘", ChatIntent.MOCK_PORTFOLIO, False, False),
    ),
)
def test_explicit_personal_tax_request_overrides_ambiguous_account_wording(
    message: str,
    expected_intent: ChatIntent,
    tax_credit: bool,
    withdrawal: bool,
) -> None:
    plan = plan_question(message)

    assert plan.intent == expected_intent
    assert plan.requests_tax_credit is tax_credit
    assert plan.requests_withdrawal_tax is withdrawal


def test_named_mock_scenario_wins_over_tax_credit_word() -> None:
    plan = plan_question("세액공제 후 미운용 시나리오를 진단해줘")

    assert plan.intent == ChatIntent.MOCK_PORTFOLIO


@pytest.mark.parametrize(
    "message",
    (
        "실시간 뉴스 기반 이벤트 드리븐 운용전략을 알려줘",
        "이벤트 드리븐 전략을 알려줘",
        "국내 실시간 뉴스 기반 운용전략을 보여줘",
    ),
)
def test_news_strategy_question_routes_to_live_event_strategy(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.NEWS
    assert plan.requests_event_strategy is True
    assert plan.requests_live_news is True
    assert plan.news_query is not None


def test_ordinary_pension_strategy_does_not_trigger_live_news() -> None:
    plan = plan_question("내 나이와 투자성향에 맞는 연금 운용전략을 알려줘")

    assert plan.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert plan.requests_event_strategy is False


def test_timely_market_news_routes_to_stored_news() -> None:
    plan = plan_question("실시간 증시 뉴스 보여줘")

    assert plan.intent == ChatIntent.NEWS
    assert plan.requests_live_news is False
    assert plan.requests_event_strategy is False


@pytest.mark.parametrize(
    "message",
    (
        "오늘 증시 뉴스 알려줘",
        "지금 국내 증시 뉴스 보여줘",
        "지금 미국 증시 뉴스 보여줘",
        "최신 증시 뉴스 알려줘",
    ),
)
def test_general_freshness_words_keep_stored_three_line_news(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.NEWS
    assert plan.requests_live_news is False


@pytest.mark.parametrize(
    ("message", "notice"),
    (
        ("삼성전자 뉴스 보여줘", NewsScopeNotice.COMPANY),
        ("중국 증시 뉴스 보여줘", NewsScopeNotice.UNSUPPORTED_MARKET),
        ("연금저축 뉴스 보여줘", NewsScopeNotice.PENSION),
    ),
)
def test_out_of_scope_news_keeps_market_news_intent_with_notice(
    message: str,
    notice: NewsScopeNotice,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.NEWS
    assert plan.news_scope_notice == notice


def test_bare_account_wording_does_not_shadow_tax_credit_intent() -> None:
    plan = plan_question("내 계좌 세액공제 얼마야?")

    assert plan.intent == ChatIntent.PENSION_TAX
    assert plan.requests_tax_credit is True


@pytest.mark.parametrize(
    "message",
    ("현재 나의 포트폴리오 보여줘", "내 연금 포트폴리오를 진단해줘"),
)
def test_my_portfolio_wording_selects_mock_portfolio_intent(message: str) -> None:
    assert plan_question(message).intent == ChatIntent.MOCK_PORTFOLIO


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    zip(
        SUGGESTED_CHAT_PROMPTS,
        (ChatIntent.PENSION_TAX,),
        strict=True,
    ),
)
def test_guide_page_prompts_route_to_supported_intents(
    message: str,
    expected_intent: ChatIntent,
) -> None:
    assert plan_question(message).intent == expected_intent


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    (
        ("세액공제 후 미운용 시나리오 최신 뉴스", ChatIntent.MOCK_PORTFOLIO),
        ("연금저축 세액공제 뉴스를 알려줘", ChatIntent.NEWS),
        ("IRP 사업자 수익률 뉴스를 알려줘", ChatIntent.NEWS),
        ("IRP 사업자 수익률 한도를 알려줘", ChatIntent.PROVIDER_DISCLOSURE),
    ),
)
def test_intent_conflicts_follow_explicit_priority(
    message: str,
    expected_intent: ChatIntent,
) -> None:
    assert plan_question(message).intent == expected_intent


def test_combined_cap_request_is_marked_for_account_separation() -> None:
    plan = plan_question("DC와 IRP와 연금저축을 합쳐서 위험자산 70%를 적용하면 돼?")

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


def test_news_topic_and_requested_count_are_preserved() -> None:
    samsung = plan_question("삼성전자 가장 최근 뉴스 하나 찾아줘")
    pension = plan_question("퇴직연금 최신 뉴스 5건 알려줘")

    assert samsung.news_query == "market"
    assert samsung.max_results == 1
    assert pension.news_query == "market"
    assert pension.max_results == 5


@pytest.mark.parametrize("message", ("IRP 뉴스", "DC형 뉴스", "연금저축 뉴스"))
def test_account_news_uses_market_news_policy(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.NEWS
    assert plan.news_query == "market"
    assert plan.max_results == 3


def test_news_command_removal_keeps_words_that_contain_news_terms() -> None:
    newskin = plan_question("뉴스킨 최신 뉴스")
    revival = plan_question("기사회생 뉴스")

    assert newskin.intent == ChatIntent.NEWS
    assert newskin.news_query == "market"
    assert revival.intent == ChatIntent.NEWS
    assert revival.news_query == "market"


@pytest.mark.parametrize(
    ("message", "query", "max_results"),
    (
        ("미국 증시 뉴스 2건", "market:us", 2),
        ("코스피 뉴스", "market:kr", 3),
        ("증시 뉴스 5건", "market", 5),
    ),
)
def test_market_news_region_filter_and_count(
    message: str, query: str, max_results: int
) -> None:
    plan = plan_question(message)

    assert plan.news_query == query
    assert plan.max_results == max_results


def test_order_and_future_requests_do_not_reach_retrieval() -> None:
    knowledge = RecordingKnowledgeRepository()
    chatbot = _service(knowledge)

    future = chatbot.ask(ChatRequest(message="내년 IRP 수익률을 예측해줘"))
    order = chatbot.ask(ChatRequest(message="IRP 상품을 대신 매수해줘"))

    assert future.data_mode == "blocked"
    assert order.data_mode == "blocked"
    assert knowledge.queries == []


def test_company_name_with_future_word_is_not_blocked_as_prediction() -> None:
    plan = plan_question("미래에셋증권 IRP 수익률 공시를 알려줘")

    assert plan.intent == ChatIntent.PROVIDER_DISCLOSURE
    assert plan.blocked_reason is None


@pytest.mark.parametrize(
    "message",
    (
        "미래 수익률을 알려줘",
        "미래의 IRP 수익률 전망을 알려줘",
    ),
)
def test_future_phrases_remain_blocked(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason == BlockedReason.FUTURE_PREDICTION


@pytest.mark.parametrize(
    "message",
    ("중국 주식에 투자해도 돼?", "삼성전자 주식을 직접 편입해도 돼?"),
)
def test_foreign_market_and_individual_stock_requests_are_distinguished(
    message: str,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason == BlockedReason.FOREIGN_MARKET_OR_INDIVIDUAL_STOCK


@pytest.mark.parametrize(
    "message",
    (
        "IRP 연금 운용 전략을 알려줘",
        "연금 포트폴리오를 구성해줘",
        "퇴직연금 자산배분을 도와줘",
    ),
)
def test_educational_portfolio_questions_reach_input_collection(
    message: str,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert plan.blocked_reason is None


# 화면 버튼과 같은 말을 사용자가 직접 입력해도 LLM 가드 없이 전략 안내로 가야 한다.
@pytest.mark.parametrize(
    "message",
    (
        "리밸런싱 점검해줘",
        "내 계좌 리밸런싱 점검해줘",
        "비중 점검해줘",
        "자산배분 검토해줘",
    ),
)
def test_rebalancing_review_requests_reach_the_portfolio_engine(
    message: str,
) -> None:
    plan = plan_question(message)

    assert plan.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert plan.blocked_reason is None


# 뜻풀이 질문은 그대로 용어 답변이어야 한다.
def test_rebalancing_definition_still_reads_as_a_glossary_question() -> None:
    plan = plan_question("리밸런싱이 뭐야?")

    assert plan.intent == ChatIntent.GLOSSARY


@pytest.mark.parametrize(
    "message",
    (
        "한국 기준금리와 소비자물가를 알려줘",
        "65세 기대수명 공식 통계를 보여줘",
        "미국 10년 국채금리와 기대인플레이션을 알려줘",
    ),
)
def test_macro_questions_route_to_official_evidence(message: str) -> None:
    plan = plan_question(message)

    assert plan.intent is ChatIntent.MACRO_EVIDENCE
    assert plan.blocked_reason is None


def test_explicit_macro_request_takes_priority_over_etf_theme() -> None:
    plan = plan_question("반도체 ETF 테마와 한국 기준금리 거시지표를 같이 보여줘")

    assert plan.intent is ChatIntent.MACRO_EVIDENCE
    assert plan.blocked_reason is None


def test_accumulation_question_redirects_to_pension_planner() -> None:
    response = _service(RecordingKnowledgeRepository()).ask(
        ChatRequest(message="적립하면 얼마 모여요?")
    )

    assert response.data_mode == "pension_planner_redirect"
    assert response.suggested_follow_ups[0].follow_up_id == "open_pension_planner"
    assert "연금계산기" in response.answer


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("연금저축이 뭐야?", ChatIntent.ACCOUNT_RULE),
        ("IRP가 뭔지 쉽게 알려줘", ChatIntent.ACCOUNT_RULE),
        ("DC형이랑 DB형은 뭐가 달라?", ChatIntent.ACCOUNT_RULE),
        ("연금계좌에 돈만 넣어두면 알아서 불어나?", ChatIntent.ACCOUNT_RULE),
        ("연금계좌로 뭘 살 수 있어?", ChatIntent.ACCOUNT_RULE),
        ("연금은 언제부터 받을 수 있어?", ChatIntent.ACCOUNT_RULE),
        ("내 퇴직연금은 어디서 확인해?", ChatIntent.ACCOUNT_RULE),
        ("투자 성향이 뭐야? 왜 물어봐?", ChatIntent.EDUCATIONAL_PORTFOLIO),
    ],
)
def test_beginner_questions_route_without_topic_guard(
    message: str, expected: ChatIntent
) -> None:
    # 타깃은 용어를 모르는 사용자다. 아래 어법은 토픽 가드가 꺼진 환경에서도
    # 결정론 라우팅만으로 답해야 한다(챗봇 테스트 가이드 §2-4-1 A).
    plan = plan_question(message)

    assert plan.intent is expected
    assert plan.blocked_reason is None
