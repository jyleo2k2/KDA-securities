from datetime import date
from pathlib import Path

import httpx

from scripts.check_knowledge_freshness import (
    build_report,
    check_official_sources,
    evaluate_review_schedule,
    render_markdown,
)


def test_weekly_governance_workflow_preserves_state_and_opens_review_issue() -> None:
    workflow = Path(".github/workflows/rag-governance.yml").read_text(
        encoding="utf-8"
    )

    assert 'cron: "15 0 * * 1"' in workflow
    assert "scripts/check_knowledge_freshness.py" in workflow
    assert "rag-source-fingerprints" in workflow
    assert "issues: write" in workflow
    assert "공식 출처 및 검토기한 점검" in workflow


def test_review_schedule_marks_expired_due_and_current_documents() -> None:
    documents = (
        {"document_id": "expired", "review_due_date": "2026-07-01"},
        {"document_id": "soon", "review_due_date": "2026-08-10"},
        {"document_id": "current", "review_due_date": "2027-01-01"},
    )

    reviews = evaluate_review_schedule(
        documents, today=date(2026, 7, 28), warn_days=30
    )

    assert {item["document_id"]: item["status"] for item in reviews} == {
        "expired": "expired",
        "soon": "due_soon",
        "current": "current",
    }


def test_source_fingerprint_creates_baseline_then_detects_change() -> None:
    url = "https://www.nts.go.kr/nts/example"
    source_documents = {url: ("pension-tax-credit",)}

    def response(text: str) -> httpx.MockTransport:
        return httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/html; charset=utf-8"},
                text=f"<html><body><main>{text}</main></body></html>",
            )
        )

    with httpx.Client(transport=response("세액공제 공식 안내")) as client:
        baseline_checks, state = check_official_sources(
            source_documents, previous_state={}, client=client
        )
    assert baseline_checks[0].status == "baseline_created"

    with httpx.Client(transport=response("변경된 세액공제 공식 안내")) as client:
        changed_checks, next_state = check_official_sources(
            source_documents, previous_state=state, client=client
        )
    assert changed_checks[0].status == "changed"
    assert next_state[url]["sha256"] != state[url]["sha256"]


def test_unavailable_source_requires_human_review() -> None:
    url = "https://www.nts.go.kr/nts/example"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, request=request)
    )
    with httpx.Client(transport=transport) as client:
        checks, _ = check_official_sources(
            {url: ("pension-tax-credit",)},
            previous_state={},
            client=client,
        )

    documents = ({"document_id": "pension-tax-credit"},)
    report = build_report(
        documents,
        (),
        checks,
        today=date(2026, 7, 28),
    )

    assert report["requires_review"] is True
    assert report["summary"]["unavailable_source_count"] == 1
    assert "자동 반영하지 않습니다" in render_markdown(report)
