from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from backend.app.chat.disclosures import ProviderDisclosure
from backend.app.chat.knowledge import FallbackKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest, ConversationContext
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


def test_direct_identifiers_are_blocked_before_chat_processing() -> None:
    response = _service().ask(ChatRequest(
        message="메일 user@example.com, 전화 010-1234-5678, 카드 1234-5678-1234-5678"
    ))

    assert response.intent is ChatIntent.OUT_OF_SCOPE
    assert response.data_mode == "blocked"
