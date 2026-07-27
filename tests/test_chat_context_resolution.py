import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.chat.context_resolution import (
    ContextAction,
    ContextReferent,
    ContextReferentKind,
    ContextResolutionDecision,
    ContextResolutionPayload,
    ContextResolutionStatus,
    build_context_resolution_payload,
    is_context_resolution_candidate,
    validate_context_resolution_decision,
)
from backend.app.chat.models import (
    ChatIntent,
    ChatRequest,
    ConversationContext,
    EtfThemeConversationContext,
    NewsConversationContext,
    ReferentItem,
    ReferentList,
)
from backend.app.chat.query_planner import BlockedReason, QueryPlan
from backend.app.engine import AccountType

CORPUS_PATH = Path(__file__).parent / "fixtures" / "chat_context_resolution_cases.json"


def _plan(
    message: str,
    blocked_reason: BlockedReason | None = BlockedReason.UNSUPPORTED,
) -> QueryPlan:
    return QueryPlan(
        normalized_message=message,
        intent=(
            ChatIntent.OUT_OF_SCOPE
            if blocked_reason is not None
            else ChatIntent.ACCOUNT_RULE
        ),
        blocked_reason=blocked_reason,
    )


def _account_request(message: str = "두 번째 거 수수료는?") -> ChatRequest:
    return ChatRequest(
        message=message,
        conversation_context=ConversationContext(
            last_intent=ChatIntent.ACCOUNT_RULE,
            scenario_code="dc_dormant",
            referents=ReferentList(
                intent=ChatIntent.ACCOUNT_RULE,
                items=[
                    ReferentItem(label="DC형", ref="dc"),
                    ReferentItem(label="IRP", ref="irp"),
                    ReferentItem(label="연금저축펀드", ref="pension_savings"),
                ],
            ),
        ),
    )


def _payload(*referents: ContextReferent) -> ContextResolutionPayload:
    return ContextResolutionPayload(
        raw_message="그거 자세히 알려줘",
        normalized_message="그거 자세히 알려줘",
        last_intent=ChatIntent.ACCOUNT_RULE,
        referents=referents,
    )


def test_resolved_decision_requires_action_and_referents() -> None:
    with pytest.raises(ValidationError):
        ContextResolutionDecision(status=ContextResolutionStatus.RESOLVED)

    with pytest.raises(ValidationError):
        ContextResolutionDecision(
            status=ContextResolutionStatus.RESOLVED,
            action=ContextAction.DETAIL,
            referent_ids=("irp", "irp"),
        )


@pytest.mark.parametrize(
    "status",
    [ContextResolutionStatus.CLARIFY, ContextResolutionStatus.NOT_APPLICABLE],
)
def test_unresolved_decision_cannot_select_targets(
    status: ContextResolutionStatus,
) -> None:
    with pytest.raises(ValidationError):
        ContextResolutionDecision(
            status=status,
            action=ContextAction.DETAIL,
            referent_ids=("irp",),
        )


def test_payload_contains_only_whitelisted_context() -> None:
    request = ChatRequest(
        message="두 번째 거 수수료는?",
        conversation_context=ConversationContext(
            account_type=AccountType.IRP,
            scenario_code="dc_dormant",
            last_intent=ChatIntent.ACCOUNT_RULE,
            referents=_account_request().conversation_context.referents,
            news=NewsConversationContext(news_item_ids=["news-1", "news-2"]),
            etf_theme=EtfThemeConversationContext(
                theme_id="bond",
                candidate_isu_codes=["123456"],
                candidate_names=["채권 ETF"],
            ),
        ),
    )

    payload = build_context_resolution_payload(request, _plan(request.message))

    assert set(payload.model_dump()) == {
        "raw_message",
        "normalized_message",
        "last_intent",
        "referents",
    }
    assert "scenario_code" not in payload.model_dump_json()
    assert [(item.ref, item.kind) for item in payload.referents] == [
        ("dc", ContextReferentKind.ACCOUNT),
        ("irp", ContextReferentKind.ACCOUNT),
        ("pension_savings", ContextReferentKind.ACCOUNT),
        ("news-1", ContextReferentKind.NEWS),
        ("news-2", ContextReferentKind.NEWS),
        ("123456", ContextReferentKind.ETF),
    ]


@pytest.mark.parametrize(
    ("message", "blocked_reason"),
    [
        ("두 번째 거 수수료는?", BlockedReason.FEE_TARGET_REQUIRED),
        ("둘 중 뭐가 더 나아?", BlockedReason.UNSUPPORTED),
        ("아니 그거 말고 첫 번째", BlockedReason.ACCOUNT_SELECTION_REQUIRED),
    ],
)
def test_candidate_gate_accepts_only_soft_blocked_context_questions(
    message: str,
    blocked_reason: BlockedReason,
) -> None:
    request = _account_request(message)

    assert is_context_resolution_candidate(
        request,
        _plan(message, blocked_reason),
    )


@pytest.mark.parametrize(
    ("message", "blocked_reason"),
    [
        ("내년 수익률 예측해줘", BlockedReason.FUTURE_PREDICTION),
        ("두 번째 거 대신 매수해줘", BlockedReason.ORDER_REQUEST),
        ("연금이 머야", BlockedReason.UNSUPPORTED),
        ("IRP 수수료 알려줘", None),
    ],
)
def test_candidate_gate_does_not_bypass_safety_or_single_turn_routing(
    message: str,
    blocked_reason: BlockedReason | None,
) -> None:
    request = _account_request(message)

    assert not is_context_resolution_candidate(
        request,
        _plan(message, blocked_reason),
    )


def test_candidate_gate_requires_server_owned_referents() -> None:
    request = ChatRequest(message="그거 자세히 알려줘")

    assert not is_context_resolution_candidate(request, _plan(request.message))


def test_decision_validation_accepts_supplied_account_comparison() -> None:
    payload = _payload(
        ContextReferent(ref="dc", label="DC형", kind=ContextReferentKind.ACCOUNT),
        ContextReferent(ref="irp", label="IRP", kind=ContextReferentKind.ACCOUNT),
    )
    decision = ContextResolutionDecision(
        status=ContextResolutionStatus.RESOLVED,
        action=ContextAction.COMPARE,
        referent_ids=("dc", "irp"),
    )

    assert validate_context_resolution_decision(decision, payload) is decision


@pytest.mark.parametrize(
    "decision",
    [
        ContextResolutionDecision(
            status=ContextResolutionStatus.RESOLVED,
            action=ContextAction.DETAIL,
            referent_ids=("invented",),
        ),
        ContextResolutionDecision(
            status=ContextResolutionStatus.RESOLVED,
            action=ContextAction.COMPARE,
            referent_ids=("irp",),
        ),
        ContextResolutionDecision(
            status=ContextResolutionStatus.RESOLVED,
            action=ContextAction.SOURCE,
            referent_ids=("irp",),
        ),
        ContextResolutionDecision(
            status=ContextResolutionStatus.RESOLVED,
            action=ContextAction.COMPARE,
            referent_ids=("irp", "news-1"),
        ),
    ],
)
def test_decision_validation_rejects_invalid_account_targets(
    decision: ContextResolutionDecision,
) -> None:
    payload = _payload(
        ContextReferent(ref="irp", label="IRP", kind=ContextReferentKind.ACCOUNT),
        ContextReferent(
            ref="news-1",
            label="금리 기사",
            kind=ContextReferentKind.NEWS,
        ),
    )

    with pytest.raises(ValueError):
        validate_context_resolution_decision(decision, payload)


@pytest.mark.parametrize(
    ("action", "kind", "is_valid"),
    [
        (ContextAction.SOURCE, ContextReferentKind.NEWS, True),
        (ContextAction.WITHDRAWAL, ContextReferentKind.NEWS, False),
        (ContextAction.FEE, ContextReferentKind.NEWS, False),
        (ContextAction.FEE, ContextReferentKind.ETF, True),
    ],
)
def test_decision_validation_checks_action_target_compatibility(
    action: ContextAction,
    kind: ContextReferentKind,
    is_valid: bool,
) -> None:
    payload = _payload(ContextReferent(ref="target", label="대상", kind=kind))
    decision = ContextResolutionDecision(
        status=ContextResolutionStatus.RESOLVED,
        action=action,
        referent_ids=("target",),
    )

    if is_valid:
        assert validate_context_resolution_decision(decision, payload) is decision
    else:
        with pytest.raises(ValueError):
            validate_context_resolution_decision(decision, payload)


def test_context_resolution_corpus_contract() -> None:
    cases = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    categories = Counter(case["category"] for case in cases)
    case_ids = [case["case_id"] for case in cases]

    assert len(cases) >= 36
    assert len(case_ids) == len(set(case_ids))
    for category in (
        "pronoun",
        "ordinal",
        "comparison",
        "correction",
        "ambiguous",
        "safety",
        "excluded_single_turn",
    ):
        assert categories[category] >= 4

    for case in cases:
        assert set(case) == {
            "case_id",
            "category",
            "history",
            "context",
            "current_message",
            "expected_status",
            "expected_action",
            "expected_referent_ids",
            "expected_blocked_reason",
        }
        assert all(set(turn) == {"role", "content"} for turn in case["history"])
        assert all(turn["role"] in {"user", "assistant"} for turn in case["history"])
        context = case["context"]
        assert set(context) == {"account_type", "last_intent", "referents"}
        if context["last_intent"] is not None:
            ChatIntent(context["last_intent"])
        if context["account_type"] is not None:
            AccountType(context["account_type"])
        supplied_refs = {item["ref"] for item in context["referents"]}
        assert set(case["expected_referent_ids"]) <= supplied_refs | {
            context["account_type"]
        }

        if case["expected_status"] == "resolved":
            ContextAction(case["expected_action"])
            assert case["expected_referent_ids"]
            assert case["expected_blocked_reason"] is None
        else:
            ContextResolutionStatus(case["expected_status"])
            assert case["expected_action"] is None
            assert case["expected_referent_ids"] == []

        if case["expected_blocked_reason"] is not None:
            BlockedReason(case["expected_blocked_reason"])

        if case["category"] == "safety":
            assert case["expected_status"] == "not_applicable"
            assert case["expected_blocked_reason"] is not None
