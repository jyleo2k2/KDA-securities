from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from backend.app.chat.orchestrator import (
    AnswerNarrative,
    AnswerStatus,
    orchestrate_answer,
)
from backend.app.chat.service import ChatService
from backend.app.retrieval.disclosures_repository import RetirementProviderStat


class _NeverCalled:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unneeded tool was called: {name}")


class _DisclosureRepository:
    def __init__(self, rows: list[RetirementProviderStat]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def latest_retirement_stats(self, **kwargs: object) -> list[RetirementProviderStat]:
        self.calls.append(kwargs)
        return self.rows

    def latest_pension_savings_stats(self, **kwargs: object) -> list[object]:
        raise AssertionError("pension savings tool was not requested")


def _row() -> RetirementProviderStat:
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


def _service(
    rows: list[RetirementProviderStat],
) -> tuple[ChatService, _DisclosureRepository]:
    disclosures = _DisclosureRepository(rows)
    return (
        ChatService(
            knowledge=_NeverCalled(),
            disclosures=disclosures,
            news=_NeverCalled(),
            backend="supabase",
        ),
        disclosures,
    )


def test_provider_answer_uses_only_disclosure_tool_and_returns_evidence() -> None:
    service, disclosures = _service([_row()])

    answer = orchestrate_answer(
        service,
        "키움증권 IRP의 최근 과거 수익률을 알려줘",
    )

    assert answer.status == AnswerStatus.ANSWERED
    assert answer.plan.intent == "provider_disclosure"
    assert answer.numeric_evidence[0].metric == "earn_rate_current"
    assert answer.numeric_evidence[0].value == Decimal("2.35")
    assert answer.sources[0].url.endswith("rpCorpResultList.json")
    assert answer.data_boundary == "official_disclosure_real_data"
    assert answer.as_of_date.isoformat() == "2026-03-31"
    assert answer.collected_at == _row().observed_at
    assert disclosures.calls == [
        {
            "scheme": "irp",
            "year": None,
            "quarter": None,
            "provider_name": "키움증권",
            "limit": 3,
        }
    ]


def test_llm_rewrite_is_used_only_when_all_numbers_match() -> None:
    service, _ = _service([_row()])

    class SafeRestyler:
        def rewrite(
            self, narrative: AnswerNarrative, **kwargs: object
        ) -> dict[str, str]:
            return {
                "facts": (
                    "키움증권의 2026년 1분기 IRP 공시에서 "
                    "현재 과거 수익률은 2.35%로 확인됐습니다."
                ),
                "external_opinion": narrative.external_opinion,
                "service_interpretation": narrative.service_interpretation,
                "limitations": narrative.limitations,
            }

    answer = service.answer_question(
        "키움증권 IRP의 최근 과거 수익률을 알려줘",
        restyler=SafeRestyler(),
    )

    assert answer.used_llm_rewrite is True
    assert answer.rewrite_discarded is False
    assert "확인됐습니다" in answer.narrative.facts
    assert answer.numeric_evidence[0].value == Decimal("2.35")


def test_llm_numeric_mismatch_discards_rewrite() -> None:
    service, _ = _service([_row()])

    class UnsafeRestyler:
        def rewrite(
            self, narrative: AnswerNarrative, **kwargs: object
        ) -> dict[str, str]:
            return {
                "facts": narrative.facts.replace("2.35", "9.99"),
                "external_opinion": narrative.external_opinion,
                "service_interpretation": narrative.service_interpretation,
                "limitations": narrative.limitations,
            }

    answer = service.answer_question(
        "키움증권 IRP의 최근 과거 수익률을 알려줘",
        restyler=UnsafeRestyler(),
    )

    assert answer.used_llm_rewrite is False
    assert answer.rewrite_discarded is True
    assert "2.35%" in answer.narrative.facts
    assert "9.99" not in answer.narrative.facts


def test_no_search_evidence_does_not_call_llm_or_general_knowledge() -> None:
    service, _ = _service([])

    class ExplodingRestyler:
        def rewrite(self, narrative: AnswerNarrative, **kwargs: object) -> object:
            raise AssertionError("LLM must not run without evidence")

    answer = service.answer_question(
        "키움증권 IRP의 최근 과거 수익률을 알려줘",
        restyler=ExplodingRestyler(),
    )

    assert answer.status == AnswerStatus.NO_EVIDENCE
    assert answer.sources == ()
    assert answer.numeric_evidence == ()
    assert answer.narrative.facts == "DB가 비어 있어서 답변이 제한됩니다."
    assert answer.used_llm_rewrite is False


def test_blocked_question_executes_no_retrieval_tool() -> None:
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="supabase",
    )

    answer = service.answer_question("내년 IRP 수익률을 예측해줘")

    assert answer.status == AnswerStatus.BLOCKED
    assert answer.data_boundary == "blocked_before_retrieval"
    assert answer.sources == ()
