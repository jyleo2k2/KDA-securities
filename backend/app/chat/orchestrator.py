import calendar
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.app.engine import PortfolioInput, RiskCapEvaluation
from backend.app.retrieval.disclosures_repository import (
    PensionSavingsProviderStat,
    RetirementProviderStat,
)
from backend.app.retrieval.repository import KnowledgeMatch, NewsMatch

from .query_planner import DisclosureMetric, QueryIntent, QueryPlan


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    NO_EVIDENCE = "no_evidence"
    BLOCKED = "blocked"


class AnswerNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: str
    external_opinion: str
    service_interpretation: str
    limitations: str


class NumericEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    label: str
    value: Decimal
    unit: str


class AnswerSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    url: str = Field(min_length=1)
    document_id: str | None = None
    chunk_id: int | None = None
    news_item_id: str | None = None


class EvidenceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AnswerStatus
    plan: QueryPlan
    narrative: AnswerNarrative
    numeric_evidence: tuple[NumericEvidence, ...] = ()
    sources: tuple[AnswerSource, ...] = ()
    data_boundary: str
    as_of_date: date | None = None
    collected_at: datetime | None = None
    used_llm_rewrite: bool = False
    rewrite_discarded: bool = False


class AnswerRestyler(Protocol):
    def rewrite(
        self,
        narrative: AnswerNarrative,
        *,
        numeric_evidence: tuple[NumericEvidence, ...],
        sources: tuple[AnswerSource, ...],
    ) -> AnswerNarrative | dict[str, Any]: ...


class AnswerToolService(Protocol):
    def plan_question(self, question: str) -> QueryPlan: ...

    def execute_query_plan(
        self,
        plan: QueryPlan,
        *,
        original_question: str,
        portfolio: PortfolioInput | None = None,
    ) -> object: ...


_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?")
_METRIC_LABELS = {
    DisclosureMetric.RESERVE_KRW: ("적립금", "원"),
    DisclosureMetric.EARN_RATE_CURRENT: ("현재 과거 수익률", "%"),
    DisclosureMetric.EARN_RATE_1Y: ("1년 과거 수익률", "%"),
    DisclosureMetric.AVG_EARN_RATE_3Y: ("3년 평균 과거 수익률", "%"),
    DisclosureMetric.AVG_EARN_RATE_5Y: ("5년 평균 과거 수익률", "%"),
    DisclosureMetric.AVG_EARN_RATE_7Y: ("7년 평균 과거 수익률", "%"),
    DisclosureMetric.AVG_EARN_RATE_10Y: ("10년 평균 과거 수익률", "%"),
    DisclosureMetric.FEE_RATE_1Y: ("1년 수수료율", "%"),
}


def _number_signature(narrative: AnswerNarrative) -> Counter[str]:
    text = "\n".join(
        (
            narrative.facts,
            narrative.external_opinion,
            narrative.service_interpretation,
            narrative.limitations,
        )
    )
    signature: Counter[str] = Counter()
    for raw in _NUMBER.findall(text):
        number = Decimal(raw.replace(",", ""))
        normalized = "0" if number == 0 else format(number.normalize(), "f")
        signature[normalized] += 1
    return signature


def _format_value(value: Decimal) -> str:
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    return date(year, month, calendar.monthrange(year, month)[1])


def _no_evidence(plan: QueryPlan, boundary: str) -> EvidenceAnswer:
    return EvidenceAnswer(
        status=AnswerStatus.NO_EVIDENCE,
        plan=plan,
        narrative=AnswerNarrative(
            facts="DB가 비어 있어서 답변이 제한됩니다.",
            external_opinion="확인된 외부 의견이 없습니다.",
            service_interpretation="근거가 없으므로 별도 해석을 제공하지 않습니다.",
            limitations="일반 지식이나 추정으로 답변을 보완하지 않았습니다.",
        ),
        data_boundary=boundary,
    )


def _disclosure_answer(
    plan: QueryPlan,
    rows: list[PensionSavingsProviderStat | RetirementProviderStat],
) -> EvidenceAnswer:
    if not rows:
        return _no_evidence(plan, "official_disclosure")
    row = rows[0]
    evidence: list[NumericEvidence] = []
    statements: list[str] = []
    for metric in plan.metrics:
        value = getattr(row, metric.value, None)
        if value is None:
            continue
        decimal_value = Decimal(value)
        label, unit = _METRIC_LABELS[metric]
        evidence.append(
            NumericEvidence(
                metric=metric.value,
                label=label,
                value=decimal_value,
                unit=unit,
            )
        )
        statements.append(f"{label}은 {_format_value(decimal_value)}{unit}")
    if not evidence:
        return _no_evidence(plan, "official_disclosure")
    period_text = f"{row.year}년 {row.quarter}분기"
    facts = (
        f"{row.company_name_raw}의 {period_text} "
        f"{row.scheme.upper() if hasattr(row, 'scheme') else '연금저축'} 공시에서 "
        f"{', '.join(statements)}입니다."
    )
    return EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=plan,
        narrative=AnswerNarrative(
            facts=facts,
            external_opinion="FSS 공시에는 별도의 외부 의견이 포함되지 않습니다.",
            service_interpretation=(
                "공시 원본의 과거 수치를 그대로 정리했으며 "
                "미래 성과로 해석하지 않습니다."
            ),
            limitations=(
                "과거 공시 수치는 현재 조건이나 미래 수익률을 보장하지 않습니다."
            ),
        ),
        numeric_evidence=tuple(evidence),
        sources=(
            AnswerSource(title=row.source_name, url=row.source_url),
        ),
        data_boundary="official_disclosure_real_data",
        as_of_date=_quarter_end(row.year, row.quarter),
        collected_at=row.observed_at,
    )


def _knowledge_answer(plan: QueryPlan, rows: list[KnowledgeMatch]) -> EvidenceAnswer:
    if not rows:
        return _no_evidence(plan, "verified_knowledge")
    top = rows[0]
    return EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=plan,
        narrative=AnswerNarrative(
            facts=top.content,
            external_opinion="검색된 공식 지식에는 별도 외부 의견 구분이 없습니다.",
            service_interpretation="검증 문서에서 검색된 내용을 우선 제시했습니다.",
            limitations="검색된 청크 범위 밖의 내용은 포함하지 않았습니다.",
        ),
        sources=tuple(
            AnswerSource(
                title=row.title,
                url=row.source_url,
                document_id=row.document_id,
                chunk_id=row.chunk_id,
            )
            for row in rows
        ),
        data_boundary="verified_knowledge",
    )


def _news_answer(plan: QueryPlan, rows: list[NewsMatch]) -> EvidenceAnswer:
    if not rows:
        return _no_evidence(plan, "news_metadata")
    summaries = [row.description for row in rows if row.description]
    latest = max(
        (row.published_at for row in rows if row.published_at is not None),
        default=None,
    )
    return EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=plan,
        narrative=AnswerNarrative(
            facts=f"뉴스 메타데이터 {len(rows)}건을 찾았습니다.",
            external_opinion=" ".join(summaries) or "기사 요약이 제공되지 않았습니다.",
            service_interpretation=(
                "기사 전문이 아닌 제목과 제공된 요약만 정리했습니다."
            ),
            limitations="기사 전문을 저장하거나 근거로 사용하지 않았습니다.",
        ),
        sources=tuple(
            AnswerSource(
                title=row.title,
                url=row.original_url,
                news_item_id=row.item_id,
            )
            for row in rows
        ),
        data_boundary="news_metadata_real_data",
        as_of_date=latest.date() if latest else None,
    )


def _portfolio_answer(plan: QueryPlan, result: RiskCapEvaluation) -> EvidenceAnswer:
    numeric = (
        NumericEvidence(
            metric="general_risky_ratio_percent",
            label="일반 위험자산 비율",
            value=result.general_risky_ratio_percent,
            unit="%",
        ),
    )
    evidence = result.evidence[0]
    return EvidenceAnswer(
        status=AnswerStatus.ANSWERED,
        plan=plan,
        narrative=AnswerNarrative(
            facts=(
                "규칙 엔진 계산 결과 일반 위험자산 비율은 "
                f"{_format_value(result.general_risky_ratio_percent)}%입니다."
            ),
            external_opinion="외부 의견을 사용하지 않았습니다.",
            service_interpretation=f"규칙 엔진 상태는 {result.status.value}입니다.",
            limitations="입력된 목계좌 데이터에 한정된 규칙 기반 결과입니다.",
        ),
        numeric_evidence=numeric,
        sources=(
            AnswerSource(
                title=evidence.source.label,
                url=f"project://{evidence.source.reference}",
            ),
        ),
        data_boundary="mock_portfolio_rule_engine",
        as_of_date=evidence.source.as_of,
    )


def _apply_rewrite(
    answer: EvidenceAnswer,
    restyler: AnswerRestyler | None,
) -> EvidenceAnswer:
    if restyler is None or answer.status != AnswerStatus.ANSWERED:
        return answer
    try:
        raw = restyler.rewrite(
            answer.narrative,
            numeric_evidence=answer.numeric_evidence,
            sources=answer.sources,
        )
        rewritten = (
            raw
            if isinstance(raw, AnswerNarrative)
            else AnswerNarrative.model_validate(raw)
        )
    except Exception:
        return answer.model_copy(update={"rewrite_discarded": True})
    if _number_signature(rewritten) != _number_signature(answer.narrative):
        return answer.model_copy(update={"rewrite_discarded": True})
    return answer.model_copy(
        update={"narrative": rewritten, "used_llm_rewrite": True}
    )


def orchestrate_answer(
    service: AnswerToolService,
    question: str,
    *,
    portfolio: PortfolioInput | None = None,
    restyler: AnswerRestyler | None = None,
) -> EvidenceAnswer:
    plan = service.plan_question(question)
    if plan.intent == QueryIntent.OUT_OF_SCOPE:
        return EvidenceAnswer(
            status=AnswerStatus.BLOCKED,
            plan=plan,
            narrative=AnswerNarrative(
                facts="요청을 처리할 수 없습니다.",
                external_opinion="외부 의견을 조회하지 않았습니다.",
                service_interpretation=(
                    "안전 규칙에 따라 조회 도구를 실행하지 않았습니다."
                ),
                limitations=f"차단 사유: {plan.blocked_reason}",
            ),
            data_boundary="blocked_before_retrieval",
        )

    result = service.execute_query_plan(
        plan,
        original_question=question,
        portfolio=portfolio,
    )
    if plan.intent == QueryIntent.PROVIDER_DISCLOSURE:
        answer = _disclosure_answer(plan, result)  # type: ignore[arg-type]
    elif plan.intent == QueryIntent.ACCOUNT_RULE:
        answer = _knowledge_answer(plan, result)  # type: ignore[arg-type]
    elif plan.intent == QueryIntent.NEWS:
        answer = _news_answer(plan, result)  # type: ignore[arg-type]
    else:
        answer = _portfolio_answer(plan, result)  # type: ignore[arg-type]
    return _apply_rewrite(answer, restyler)
