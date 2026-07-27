from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from backend.app.chat.disclosures import ProviderDisclosure
from backend.app.chat.knowledge import FallbackKnowledgeRepository
from backend.app.chat.models import (
    ChatIntent,
    ChatRequest,
    ConversationContext,
    ReferentItem,
    ReferentList,
)
from backend.app.chat.routing import IntentRouter
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import AccountType
from backend.app.retrieval.repository import KnowledgeMatch


class EmptyKnowledgeRepository:
    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        return []


class FailingKnowledgeRepository:
    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        raise psycopg.OperationalError("remote index unavailable")


class LocalKnowledgeFallback:
    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        return [
            KnowledgeMatch(
                chunk_id=9,
                document_id=uuid4(),
                title="local fallback",
                source_url="project://knowledge.md",
                content="verified local content",
                text_rank=1.0,
            )
        ]


class DisclosureRepository:
    def search(self, question: str, *, account_type: AccountType, limit: int):
        assert question.startswith("IRP ")
        assert account_type is AccountType.IRP
        return [
            ProviderDisclosure(
                company_name="Example Securities",
                account_type=AccountType.IRP,
                year=2026,
                quarter=1,
                reserve_krw=Decimal("100000000"),
                earn_rate_current_pct=Decimal("4.25"),
                avg_earn_rate_3y_pct=Decimal("3.10"),
                avg_earn_rate_5y_pct=None,
                avg_earn_rate_7y_pct=None,
                avg_earn_rate_10y_pct=None,
                observed_at=datetime(2026, 7, 14, tzinfo=UTC),
                source_locator="https://example.test/fss",
            )
        ][:limit]


def _service(*, disclosures=None) -> ChatService:
    return ChatService(
        knowledge=LocalKnowledgeFallback(),
        scenarios=LocalScenarioRepository(),
        disclosures=disclosures,
    )


def test_selected_scenario_does_not_hijack_account_rule_question() -> None:
    response = _service().ask(
        ChatRequest(message="IRP 위험자산 한도 알려줘", scenario_code="dc_dormant")
    )

    assert response.intent is ChatIntent.ACCOUNT_RULE
    assert response.conversation_context is not None
    assert response.conversation_context.scenario_code == "dc_dormant"


@pytest.mark.parametrize(
    "message",
    (
        "내 연금은 어떻게 관리하면 좋을까?",
        "내 계좌 상태 알려줘",
        "지금 뭘 먼저 확인해야 해?",
    ),
)
def test_selected_scenario_routes_natural_management_questions_to_diagnosis(
    message: str,
) -> None:
    response = _service().ask(
        ChatRequest(message=message, scenario_code="dc_dormant")
    )

    assert response.intent is ChatIntent.MOCK_PORTFOLIO
    assert response.data_mode == "mock_scenario"
    assert response.scenario_evaluation is not None


def test_selected_scenario_routes_holding_strategy_to_diagnosis() -> None:
    response = _service().ask(
        ChatRequest(
            message="현재 보유 ETF 기준으로 운용 전략을 설명해줘",
            scenario_code="overlap_risk_concentration",
        )
    )

    assert response.intent is ChatIntent.MOCK_PORTFOLIO
    assert response.data_mode == "mock_scenario"
    assert any(section.title == "보유 항목과 비중" for section in response.sections)


def test_remote_knowledge_empty_or_failed_falls_back_to_local_documents() -> None:
    fallback = LocalKnowledgeFallback()

    assert FallbackKnowledgeRepository(
        EmptyKnowledgeRepository(), fallback
    ).search_knowledge("IRP")
    assert FallbackKnowledgeRepository(
        FailingKnowledgeRepository(), fallback
    ).search_knowledge("IRP")


def test_follow_up_disclosure_question_uses_prior_account_context() -> None:
    response = _service(disclosures=DisclosureRepository()).ask(
        ChatRequest(
            message="그럼 수익률 알려줘",
            conversation_context=ConversationContext(account_type=AccountType.IRP),
        )
    )

    assert response.intent is ChatIntent.PROVIDER_DISCLOSURE
    assert response.conversation_context is not None
    assert response.conversation_context.account_type is AccountType.IRP


def _account_referent_context(*account_types: AccountType) -> ConversationContext:
    return ConversationContext(
        referents=ReferentList(
            intent=ChatIntent.ACCOUNT_RULE,
            topic="pension_account_overview",
            items=[
                ReferentItem(
                    label={
                        AccountType.DC: "DC형",
                        AccountType.IRP: "IRP",
                        AccountType.PENSION_SAVINGS: "연금저축펀드",
                    }[account_type],
                    ref=account_type.value,
                )
                for account_type in account_types
            ],
        )
    )


def test_ordinal_account_referent_selects_irp() -> None:
    request = ChatRequest(
        message="두 번째 계좌 자세히 설명해줘",
        conversation_context=_account_referent_context(
            AccountType.DC,
            AccountType.IRP,
            AccountType.PENSION_SAVINGS,
        ),
    )

    referent = IntentRouter.resolve_referent(request)

    assert referent is not None
    assert referent.ref == "irp"
    assert IntentRouter.contextual_message(request).startswith("IRP ")


@pytest.mark.parametrize(
    "message",
    (
        "그거 좀 더 알려줘",
        "이건 좀 더 알려줘",
        "그건 좀 더 알려줘",
        "저건 좀 더 알려줘",
        "그 상품은 어때?",
        "아까 말한 계좌 알려줘",
    ),
)
def test_single_referent_pronouns_resolve_without_guessing(message: str) -> None:
    request = ChatRequest(
        message=message,
        conversation_context=_account_referent_context(AccountType.IRP),
    )

    referent = IntentRouter.resolve_referent(request)

    assert referent is not None
    assert referent.ref == "irp"


def test_last_referent_selects_the_last_account() -> None:
    request = ChatRequest(
        message="마지막 거 수수료 얼마야",
        conversation_context=_account_referent_context(
            AccountType.DC,
            AccountType.IRP,
            AccountType.PENSION_SAVINGS,
        ),
    )

    referent = IntentRouter.resolve_referent(request)

    assert referent is not None
    assert referent.ref == "pension_savings"


@pytest.mark.parametrize(
    "message",
    (
        "그거 좀 더 알려줘",
        "이건 수수료가 얼마야?",
        "그 상품은 어때?",
        "뭐가 더 나아?",
        "둘 중에는?",
        "아까 말한 계좌 알려줘",
        "네 번째 거 알려줘",
    ),
)
def test_multiple_referents_request_clarification(message: str) -> None:
    request = ChatRequest(
        message=message,
        conversation_context=_account_referent_context(
            AccountType.DC,
            AccountType.IRP,
            AccountType.PENSION_SAVINGS,
        ),
    )

    assert IntentRouter.resolve_referent(request) is None
    assert IntentRouter.needs_referent_clarification(request)


def test_explicit_referent_does_not_request_clarification() -> None:
    request = ChatRequest(
        message="DC와 IRP 차이를 비교해줘",
        conversation_context=_account_referent_context(
            AccountType.DC,
            AccountType.IRP,
            AccountType.PENSION_SAVINGS,
        ),
    )

    assert not IntentRouter.needs_referent_clarification(request)


def test_account_overview_response_carries_referents_into_irp_follow_up() -> None:
    initial = _service().ask(ChatRequest(message="연금 계좌 유형 뭐 있어?"))

    assert initial.conversation_context is not None
    assert initial.conversation_context.referents is not None
    assert [item.ref for item in initial.conversation_context.referents.items] == [
        "dc",
        "irp",
        "pension_savings",
    ]

    follow_up = _service().ask(
        ChatRequest(
            message="두 번째 계좌 자세히 설명해줘",
            conversation_context=initial.conversation_context,
        )
    )

    assert follow_up.intent is ChatIntent.ACCOUNT_RULE
    assert follow_up.conversation_context is not None
    assert follow_up.conversation_context.account_type is AccountType.IRP


def test_pronoun_and_out_of_range_referents_do_not_guess() -> None:
    single = ChatRequest(
        message="그 계좌 자세히 설명해줘",
        conversation_context=_account_referent_context(AccountType.IRP),
    )
    multiple = ChatRequest(
        message="그 계좌 자세히 설명해줘",
        conversation_context=_account_referent_context(
            AccountType.DC, AccountType.IRP
        ),
    )
    out_of_range = ChatRequest(
        message="네 번째 계좌 자세히 설명해줘",
        conversation_context=_account_referent_context(
            AccountType.DC, AccountType.IRP, AccountType.PENSION_SAVINGS
        ),
    )

    assert IntentRouter.resolve_referent(single) is not None
    assert IntentRouter.resolve_referent(multiple) is None
    assert IntentRouter.resolve_referent(out_of_range) is None
    assert IntentRouter.contextual_message(multiple) == multiple.message
    assert IntentRouter.contextual_message(out_of_range) == out_of_range.message


@pytest.mark.parametrize(
    "message",
    ("두 번째 계좌 내년 수익률 예측해줘", "두 번째 계좌 대신 매수해줘"),
)
def test_referents_do_not_bypass_safety_blocks(message: str) -> None:
    plan = _service().plan(
        ChatRequest(
            message=message,
            conversation_context=_account_referent_context(
                AccountType.DC, AccountType.IRP, AccountType.PENSION_SAVINGS
            ),
        )
    )

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is not None


def test_direct_identifiers_are_blocked_before_chat_processing() -> None:
    response = _service().ask(ChatRequest(
        message="메일 user@example.com, 전화 010-1234-5678, 카드 1234-5678-1234-5678"
    ))

    assert response.intent is ChatIntent.OUT_OF_SCOPE
    assert response.data_mode == "blocked"
    assert response.suggested_follow_ups == []


def test_foreign_market_and_individual_stock_requests_offer_alternatives() -> None:
    response = _service().ask(ChatRequest(message="삼성전자 주식을 직접 편입해도 돼?"))

    assert response.intent is ChatIntent.OUT_OF_SCOPE
    assert "개별주식을 직접 담을 수 없고" in response.answer
    assert [item.follow_up_id for item in response.suggested_follow_ups] == [
        "decline_market_etf_theme",
        "decline_account_rules",
        "decline_profile_portfolio",
    ]


@pytest.mark.parametrize(
    "message",
    ("내년 수익률을 예측해줘", "이 상품을 대신 매수해줘"),
)
def test_prediction_and_order_requests_offer_fact_based_alternatives(
    message: str,
) -> None:
    response = _service().ask(ChatRequest(message=message))

    assert response.intent is ChatIntent.OUT_OF_SCOPE
    assert (
        "미래 수익 예측이나 매수·매도 추천은 규정상 해드릴 수 없어요"
        in response.answer
    )
    assert [item.follow_up_id for item in response.suggested_follow_ups] == [
        "decline_historical_disclosure",
        "decline_educational_portfolio",
        "decline_etf_total_return",
    ]
