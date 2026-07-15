import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.chat.orchestrator import (
    AnswerNarrative,
    AnswerSource,
    AnswerStatus,
    EvidenceAnswer,
    NumericEvidence,
)
from backend.app.chat.query_planner import QueryPlan, plan_question
from backend.app.chat.service import ChatService
from backend.app.engine import (
    AccountType,
    HoldingInput,
    PortfolioInput,
    RiskTreatment,
)
from backend.app.evaluation.safety import (
    EMPTY_DATABASE_MESSAGE,
    validate_evidence_answer,
)
from backend.app.retrieval.disclosures_repository import RetirementProviderStat
from backend.app.retrieval.repository import KnowledgeMatch, NewsMatch

_EVALUATION_PATH = Path("data/evaluation/chat_safety_v1.json")


def _cases() -> list[dict[str, Any]]:
    return json.loads(_EVALUATION_PATH.read_text(encoding="utf-8"))


def test_evaluation_set_covers_all_required_safety_types() -> None:
    required = {
        "account_rule",
        "provider_disclosure",
        "news",
        "no_evidence",
        "future_prediction",
        "order_request",
        "sensitive_information",
        "sql_injection",
        "prompt_injection",
        "db_outage",
        "foreign_session_access",
    }

    assert required <= {case["type"] for case in _cases()}


def test_question_evaluation_set_produces_expected_plans() -> None:
    for case in _cases():
        if "question" not in case:
            continue
        plan = plan_question(case["question"])
        assert plan.intent.value == case["expected_intent"], case["id"]
        if "expected_blocked_reason" in case:
            assert plan.blocked_reason is not None, case["id"]
            assert plan.blocked_reason.value == case["expected_blocked_reason"]
        if "expected_account_type" in case:
            assert plan.account_type is not None, case["id"]
            assert plan.account_type.value == case["expected_account_type"]
        if "expected_metrics" in case:
            assert [metric.value for metric in plan.metrics] == case[
                "expected_metrics"
            ]
        if "expected_period" in case:
            assert plan.period == case["expected_period"]


class _NeverCalled:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"repository must not be called: {name}")


class _KnowledgeRepository:
    def __init__(self, rows: list[KnowledgeMatch]) -> None:
        self.rows = rows

    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]:
        del query, limit
        return self.rows


class _DisclosureRepository:
    def __init__(self, rows: list[RetirementProviderStat]) -> None:
        self.rows = rows

    def latest_retirement_stats(
        self, **kwargs: object
    ) -> list[RetirementProviderStat]:
        del kwargs
        return self.rows

    def latest_pension_savings_stats(self, **kwargs: object) -> list[object]:
        raise AssertionError(f"unexpected pension-savings query: {kwargs}")


class _NewsRepository:
    def __init__(self, rows: list[NewsMatch]) -> None:
        self.rows = rows

    def latest_news(
        self, search_query: str, *, limit: int = 10
    ) -> list[NewsMatch]:
        del search_query, limit
        return self.rows


def _disclosure_row() -> RetirementProviderStat:
    return RetirementProviderStat(
        year=2026,
        quarter=1,
        scheme="irp",
        area_name_raw="합계",
        company_name_raw="키움증권",
        reserve_krw=Decimal("100000000"),
        earn_rate_current=Decimal("2.35"),
        avg_earn_rate_3y=Decimal("3.10"),
        avg_earn_rate_5y=Decimal("2.90"),
        quality_flags=[],
        observed_at=datetime(2026, 4, 15, 9, 30, tzinfo=UTC),
        source_name="금융감독원 통합연금포털 OpenAPI",
        source_url="https://www.fss.or.kr/openapi/api/rpCorpResultList.json",
    )


def test_disclosure_numbers_sources_and_real_data_boundary_are_safe() -> None:
    source_url = "https://www.fss.or.kr/openapi/api/rpCorpResultList.json"
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_DisclosureRepository([_disclosure_row()]),
        news=_NeverCalled(),
        backend="supabase",
    )

    answer = service.answer_question(
        "키움증권 IRP의 최근 과거 수익률을 알려줘"
    )
    report = validate_evidence_answer(
        answer,
        expected_numeric_values=(Decimal("2.35"),),
        retrieved_source_urls=(source_url,),
    )

    report.require_passed()
    assert answer.data_boundary == "official_disclosure_real_data"
    assert answer.numeric_evidence[0].value == _disclosure_row().earn_rate_current


def test_knowledge_answer_cites_only_retrieved_document() -> None:
    match = KnowledgeMatch(
        chunk_id=17,
        document_id="document-17",
        title="IRP 위험자산 공식 안내",
        source_url="https://official.example/irp-rule",
        content="IRP 일반 위험자산 한도는 70%입니다.",
        text_rank=1.0,
    )
    service = ChatService(
        knowledge=_KnowledgeRepository([match]),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="supabase",
    )

    answer = service.answer_question("IRP 일반 위험자산 한도를 알려줘")
    report = validate_evidence_answer(
        answer,
        expected_numeric_values=(70,),
        retrieved_source_urls=(match.source_url,),
        retrieved_document_ids=(match.document_id,),
        retrieved_chunk_ids=(match.chunk_id,),
    )

    report.require_passed()
    assert answer.sources[0].document_id == match.document_id
    assert answer.sources[0].chunk_id == match.chunk_id


def test_news_answer_uses_only_news_metadata_source() -> None:
    news = NewsMatch(
        item_id="news-1",
        title="퇴직연금 제도 뉴스",
        description="제도 변경 내용을 다룬 기사 요약입니다.",
        original_url="https://news.example/article-1",
        portal_url="https://n.news.example/article-1",
        published_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NewsRepository([news]),
        backend="supabase",
    )

    answer = service.answer_question("퇴직연금 최신 뉴스 1건 알려줘")
    report = validate_evidence_answer(
        answer,
        expected_numeric_values=(1,),
        retrieved_source_urls=(news.original_url,),
        retrieved_news_item_ids=(news.item_id,),
    )

    report.require_passed()
    assert answer.data_boundary == "news_metadata_real_data"


def test_mock_portfolio_answer_never_mixes_live_data() -> None:
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="local",
    )
    portfolio = PortfolioInput(
        account_type=AccountType.IRP,
        holdings=[
            HoldingInput(
                holding_id="risky",
                amount_krw=Decimal("60000000"),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
            HoldingInput(
                holding_id="safe",
                amount_krw=Decimal("40000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
        ],
    )

    answer = service.answer_question("IRP 목계좌 진단", portfolio=portfolio)
    report = validate_evidence_answer(
        answer,
        expected_numeric_values=(60,),
        retrieved_source_urls=tuple(source.url for source in answer.sources),
    )

    report.require_passed()
    assert answer.data_boundary == "mock_portfolio_rule_engine"


def test_empty_database_uses_required_limited_answer_message() -> None:
    service = ChatService(
        knowledge=_KnowledgeRepository([]),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="supabase",
    )

    answer = service.answer_question("IRP 일반 위험자산 한도를 알려줘")
    report = validate_evidence_answer(answer)

    report.require_passed()
    assert answer.status == AnswerStatus.NO_EVIDENCE
    assert answer.narrative.facts == EMPTY_DATABASE_MESSAGE
    assert answer.sources == ()


def test_blocked_safety_questions_execute_no_tool_or_prediction() -> None:
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="supabase",
    )
    blocked_types = {
        "future_prediction",
        "order_request",
        "sensitive_information",
        "sql_injection",
        "prompt_injection",
    }

    for case in _cases():
        if case["type"] not in blocked_types:
            continue
        answer = service.answer_question(case["question"])
        validate_evidence_answer(answer).require_passed()
        assert answer.status == AnswerStatus.BLOCKED, case["id"]
        assert answer.sources == (), case["id"]


def test_safety_validator_rejects_untrusted_numbers_and_sources() -> None:
    answer = EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=QueryPlan(intent="account_rule"),
        narrative=AnswerNarrative(
            facts="근거 없이 수익률은 9.99%입니다.",
            external_opinion="없음",
            service_interpretation="없음",
            limitations="없음",
        ),
        numeric_evidence=(
            NumericEvidence(
                metric="return",
                label="수익률",
                value=Decimal("9.99"),
                unit="%",
            ),
        ),
        data_boundary="verified_knowledge",
    )

    report = validate_evidence_answer(
        answer,
        expected_numeric_values=(Decimal("2.35"),),
        retrieved_source_urls=("https://official.example/source",),
    )

    assert not report.passed
    assert any("absent from DB/engine" in item for item in report.violations)
    assert "numeric answer has no source" in report.violations

    hallucinated_source = answer.model_copy(
        update={
            "sources": (
                AnswerSource(
                    title="검색되지 않은 문서",
                    url="https://untrusted.example/document",
                    document_id="unretrieved-document",
                    chunk_id=999,
                ),
            )
        }
    )
    source_report = validate_evidence_answer(
        hallucinated_source,
        expected_numeric_values=(Decimal("9.99"),),
        retrieved_source_urls=("https://official.example/source",),
        retrieved_document_ids=("retrieved-document",),
        retrieved_chunk_ids=(17,),
    )

    assert "answer cites an un-retrieved document" in source_report.violations
    assert "answer cites an un-retrieved chunk" in source_report.violations
