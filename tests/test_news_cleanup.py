from datetime import UTC, datetime
from uuid import UUID

from backend.app.ingestion.news_cleanup import (
    CleanupDecision,
    ModelDecision,
    NewsCleanupClassifierError,
    NewsCleanupItem,
    _validate_model_decisions,
    apply_exact_title_deduplication,
    apply_quality_overrides,
    normalized_title,
    requires_article_review,
    rule_decision,
)


def _item(
    value: int,
    *,
    title: str,
    description: str = "",
    evidence_count: int = 0,
) -> NewsCleanupItem:
    return NewsCleanupItem(
        item_id=UUID(int=value),
        search_query="연금",
        title=title,
        description=description,
        original_url=f"https://example.test/{value}",
        published_at=datetime(2026, 7, value, tzinfo=UTC),
        evidence_count=evidence_count,
    )


def test_rule_decision_keeps_target_account_operation_news() -> None:
    item = _item(
        1,
        title="IRP와 연금저축 ETF 운용 전략",
        description="계좌 수수료와 자산배분을 설명한다.",
    )

    decision = rule_decision(item)

    assert decision.decision == "keep"
    assert decision.reason_code == "target_account_operation"
    assert decision.target_accounts == ("pension_savings", "irp")


def test_rule_decision_deletes_word_collision() -> None:
    item = _item(1, title="연금복권 당첨 번호 발표")

    decision = rule_decision(item)

    assert decision.decision == "delete"
    assert decision.reason_code == "word_collision"


def test_rule_decision_reviews_ambiguous_news() -> None:
    item = _item(1, title="은퇴 후 삶을 준비하는 법")

    assert rule_decision(item).decision == "review"


def test_normalized_title_removes_prefix_and_punctuation() -> None:
    assert normalized_title("[ 단독 ] IRP·DC형, 어떻게 운용할까?") == normalized_title(
        "IRP DC형 어떻게 운용할까"
    )


def test_exact_title_deduplication_prefers_evidence_linked_item() -> None:
    first = _item(1, title="IRP 운용 가이드")
    second = _item(2, title="IRP 운용 가이드", evidence_count=1)
    decisions = [
        CleanupDecision(first, "keep", "target_account_operation"),
        CleanupDecision(second, "keep", "target_account_operation"),
    ]

    result = apply_exact_title_deduplication(decisions)

    assert result[0].decision == "delete"
    assert result[0].reason_code == "duplicate_title"
    assert result[0].duplicate_of == second.item_id
    assert result[1].decision == "keep"


def test_model_batch_validation_rejects_missing_item() -> None:
    items = [_item(1, title="one"), _item(2, title="two")]
    decisions = (
        ModelDecision(
            item_id=str(items[0].item_id),
            decision="review",
            reason_code="insufficient_metadata",
        ),
    )

    try:
        _validate_model_decisions(items, decisions)
    except NewsCleanupClassifierError:
        pass
    else:
        raise AssertionError("missing model decision must fail validation")


def test_model_decision_rejects_keep_without_operation_topic() -> None:
    try:
        ModelDecision(
            item_id=str(UUID(int=1)),
            decision="keep",
            reason_code="target_account_operation",
            target_accounts=("irp",),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("keep without operation topic must fail validation")


def test_target_account_delete_still_requires_article_review() -> None:
    item = _item(1, title="병의원 퇴직연금, 방치하면 소송")
    decision = CleanupDecision(item, "delete", "incidental_mention")

    assert requires_article_review(decision) is True


def test_quality_override_deletes_signup_event() -> None:
    item = _item(1, title="IRP 가입 이벤트")
    decision = CleanupDecision(
        item,
        "keep",
        "target_account_operation",
        target_accounts=("irp",),
        operation_topics=("contribution_tax_credit",),
    )

    result = apply_quality_overrides([decision])

    assert result[0].decision == "delete"
    assert result[0].reason_code == "product_promotion_only"
