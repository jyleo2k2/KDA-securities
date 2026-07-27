"""Report the current planner baseline on the multi-turn Korean corpus."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.chat.context_resolution import (  # noqa: E402
    is_context_resolution_candidate,
)
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository  # noqa: E402
from backend.app.chat.models import (  # noqa: E402
    ChatIntent,
    ChatRequest,
    ConversationContext,
    ReferentItem,
    ReferentList,
)
from backend.app.chat.scenarios import LocalScenarioRepository  # noqa: E402
from backend.app.chat.service import ChatService  # noqa: E402
from backend.app.engine import AccountType  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "chat_context_resolution_cases.json"


def _conversation_context(payload: dict[str, Any]) -> ConversationContext | None:
    referent_items = payload["referents"]
    account_type = (
        AccountType(payload["account_type"])
        if payload["account_type"] is not None
        else None
    )
    last_intent = (
        ChatIntent(payload["last_intent"])
        if payload["last_intent"] is not None
        else None
    )
    if account_type is None and last_intent is None and not referent_items:
        return None
    return ConversationContext(
        account_type=account_type,
        last_intent=last_intent,
        referents=(
            ReferentList(
                intent=last_intent or ChatIntent.ACCOUNT_RULE,
                items=[ReferentItem.model_validate(item) for item in referent_items],
            )
            if referent_items
            else None
        ),
    )


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )
    categories: Counter[str] = Counter()
    intents: Counter[str] = Counter()
    blocked_reasons: Counter[str] = Counter()
    candidate_case_ids: list[str] = []
    expected_context_case_ids: list[str] = []
    baseline_unblocked_context_case_ids: list[str] = []
    missed_candidate_case_ids: list[str] = []
    blocked_reason_mismatches: list[dict[str, str | None]] = []

    for case in cases:
        categories[case["category"]] += 1
        request = ChatRequest(
            message=case["current_message"],
            conversation_context=_conversation_context(case["context"]),
        )
        plan = service.plan(request)
        intents[plan.intent.value] += 1
        if plan.blocked_reason is not None:
            blocked_reasons[plan.blocked_reason.value] += 1

        is_candidate = is_context_resolution_candidate(request, plan)
        if is_candidate:
            candidate_case_ids.append(case["case_id"])
        if case["expected_status"] in {"resolved", "clarify"}:
            expected_context_case_ids.append(case["case_id"])
            if plan.blocked_reason is None:
                baseline_unblocked_context_case_ids.append(case["case_id"])
            elif not is_candidate:
                missed_candidate_case_ids.append(case["case_id"])
        expected_blocked_reason = case["expected_blocked_reason"]
        actual_blocked_reason = (
            plan.blocked_reason.value if plan.blocked_reason is not None else None
        )
        if expected_blocked_reason is not None and (
            actual_blocked_reason != expected_blocked_reason
        ):
            blocked_reason_mismatches.append(
                {
                    "case_id": case["case_id"],
                    "expected": expected_blocked_reason,
                    "actual": actual_blocked_reason,
                }
            )

    return {
        "total_cases": len(cases),
        "categories": dict(sorted(categories.items())),
        "baseline_intents": dict(sorted(intents.items())),
        "baseline_blocked_reasons": dict(sorted(blocked_reasons.items())),
        "expected_context_cases": len(expected_context_case_ids),
        "baseline_unblocked_context_cases": len(
            baseline_unblocked_context_case_ids
        ),
        "baseline_unblocked_context_case_ids": baseline_unblocked_context_case_ids,
        "candidate_cases": len(candidate_case_ids),
        "candidate_case_ids": candidate_case_ids,
        "missed_candidate_case_ids": missed_candidate_case_ids,
        "blocked_reason_mismatches": blocked_reason_mismatches,
    }


def main() -> None:
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    print(json.dumps(evaluate(cases), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
