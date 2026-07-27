import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest, ConversationContext
from backend.app.chat.query_planner import BlockedReason
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import AccountType

CORPUS_PATH = Path(__file__).parent / "fixtures" / "chat_context_resolution_cases.json"
CASES: list[dict[str, Any]] = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


def _request(case: dict[str, Any]) -> ChatRequest:
    return ChatRequest(
        message=case["current_message"],
        conversation_context=ConversationContext.model_validate(case["context"]),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_context_resolution_corpus(case: dict[str, Any]) -> None:
    request = _request(case)
    service = _service()

    plan = service.plan(request)

    assert plan.intent is ChatIntent(case["expected_intent"])
    assert plan.blocked_reason is (
        BlockedReason(case["expected_blocked_reason"])
        if case["expected_blocked_reason"] is not None
        else None
    )
    assert plan.account_types == tuple(
        AccountType(item) for item in case["expected_account_types"]
    )
    assert plan.theme_id == case["expected_theme_id"]

    response = service.ask(request, plan=plan)
    if case["expected_clarification"]:
        if plan.blocked_reason is BlockedReason.REFERENT_SELECTION_REQUIRED:
            assert response.data_mode == "context_clarification"
            assert response.suggested_follow_ups
        else:
            assert plan.intent is ChatIntent.NEWS
            assert response.data_mode == "news_follow_up"
            assert any(
                "임의로 선택하지 않아요" in item
                for item in response.limitations
            )
    else:
        assert response.data_mode != "context_clarification"


def test_context_resolution_corpus_shape_and_coverage() -> None:
    assert len(CASES) == 30
    assert len({case["case_id"] for case in CASES}) == len(CASES)
    categories = Counter(case["category"] for case in CASES)
    assert categories["ordinal"] == 4
    assert categories["safety"] >= 5
    assert categories["ambiguous"] >= 5
    assert categories["etf_number_guard"] >= 3

    expected_keys = {
        "case_id",
        "category",
        "current_message",
        "context",
        "expected_intent",
        "expected_blocked_reason",
        "expected_account_types",
        "expected_clarification",
        "expected_theme_id",
    }
    for case in CASES:
        assert set(case) == expected_keys
        ConversationContext.model_validate(case["context"])


def test_clarification_preserves_server_context_and_never_guesses() -> None:
    case = next(
        item
        for item in CASES
        if item["case_id"] == "ambiguous_single_pronoun_multiple_accounts"
    )
    request = _request(case)

    response = _service().ask(request)

    assert response.conversation_context == request.conversation_context
    assert [item.label for item in response.suggested_follow_ups] == [
        "DC형",
        "IRP",
        "연금저축펀드",
    ]
    assert "IRP" not in response.answer


def test_omitted_comparison_returns_pair_choices_without_an_llm() -> None:
    case = next(
        item
        for item in CASES
        if item["case_id"] == "ambiguous_single_pronoun_multiple_accounts"
    )
    request = _request(case).model_copy(update={"message": "뭐가 더 나아?"})

    response = _service().ask(request)

    assert response.data_mode == "context_clarification"
    assert [item.label for item in response.suggested_follow_ups] == [
        "DC형 · IRP",
        "DC형 · 연금저축펀드",
        "IRP · 연금저축펀드",
    ]
    assert [item.message for item in response.suggested_follow_ups] == [
        "DC형, IRP 비교해줘",
        "DC형, 연금저축펀드 비교해줘",
        "IRP, 연금저축펀드 비교해줘",
    ]


@pytest.mark.parametrize(
    "case_id",
    (
        "safety_order_overrides_etf_context",
        "safety_prediction_overrides_etf_context",
        "safety_sensitive_information_overrides_account_context",
        "safety_individual_stock_overrides_etf_context",
        "safety_order_overrides_ordinal_context",
    ),
)
def test_safety_blocks_run_before_context_resolution(case_id: str) -> None:
    case = next(item for item in CASES if item["case_id"] == case_id)

    plan = _service().plan(_request(case))

    assert plan.intent is ChatIntent.OUT_OF_SCOPE
    assert plan.blocked_reason is not BlockedReason.REFERENT_SELECTION_REQUIRED
