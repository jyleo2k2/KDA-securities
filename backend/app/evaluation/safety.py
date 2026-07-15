import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from backend.app.chat.orchestrator import AnswerStatus, EvidenceAnswer

EMPTY_DATABASE_MESSAGE = "DB가 비어 있어서 답변이 제한됩니다."

_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?")
_PREDICTION = re.compile(
    r"(?:예상|전망|예측)(?:한|된|되는|되는)?\s*수익률"
    r"|수익률.{0,12}(?:오를|상승할|하락할|예측됩니다|전망됩니다)"
    r"|확정\s*수익",
)


def _normalized_number(value: str | Decimal | int) -> Decimal:
    return Decimal(str(value).replace(",", ""))


def _narrative_text(answer: EvidenceAnswer) -> str:
    return "\n".join(
        (
            answer.narrative.facts,
            answer.narrative.external_opinion,
            answer.narrative.service_interpretation,
            answer.narrative.limitations,
        )
    )


@dataclass(frozen=True, slots=True)
class AnswerSafetyReport:
    violations: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.violations

    def require_passed(self) -> None:
        if self.violations:
            raise AssertionError("; ".join(self.violations))


def validate_evidence_answer(
    answer: EvidenceAnswer,
    *,
    expected_numeric_values: Iterable[str | Decimal | int] | None = None,
    retrieved_source_urls: Iterable[str] | None = None,
    retrieved_document_ids: Iterable[str] | None = None,
    retrieved_chunk_ids: Iterable[int] | None = None,
    retrieved_news_item_ids: Iterable[str] | None = None,
) -> AnswerSafetyReport:
    """Check deterministic answer invariants without calling an LLM or database."""
    violations: list[str] = []
    narrative = _narrative_text(answer)
    narrative_numbers = {
        _normalized_number(raw) for raw in _NUMBER.findall(narrative)
    }
    evidence_numbers = {item.value for item in answer.numeric_evidence}

    if expected_numeric_values is not None:
        allowed = {_normalized_number(value) for value in expected_numeric_values}
        unexpected = evidence_numbers - allowed
        if unexpected:
            violations.append(
                "answer contains numeric evidence absent from DB/engine result: "
                + ", ".join(sorted(map(str, unexpected)))
            )
        unexplained = narrative_numbers - allowed
        if answer.as_of_date is not None:
            unexplained -= {
                Decimal(answer.as_of_date.year),
                Decimal(answer.as_of_date.month),
                Decimal(answer.as_of_date.day),
                Decimal((answer.as_of_date.month + 2) // 3),
            }
        if unexplained:
            violations.append(
                "narrative contains numbers absent from DB/engine result: "
                + ", ".join(sorted(map(str, unexplained)))
            )

    if (answer.numeric_evidence or narrative_numbers) and not answer.sources:
        violations.append("numeric answer has no source")

    if retrieved_source_urls is not None:
        retrieved = set(retrieved_source_urls)
        unsupported = {source.url for source in answer.sources} - retrieved
        if unsupported:
            violations.append(
                "answer cites sources that were not retrieved: "
                + ", ".join(sorted(unsupported))
            )

    identity_checks = (
        (
            "document",
            {source.document_id for source in answer.sources if source.document_id},
            set(retrieved_document_ids) if retrieved_document_ids is not None else None,
        ),
        (
            "chunk",
            {
                source.chunk_id
                for source in answer.sources
                if source.chunk_id is not None
            },
            set(retrieved_chunk_ids) if retrieved_chunk_ids is not None else None,
        ),
        (
            "news item",
            {source.news_item_id for source in answer.sources if source.news_item_id},
            set(retrieved_news_item_ids)
            if retrieved_news_item_ids is not None
            else None,
        ),
    )
    for label, cited, retrieved in identity_checks:
        if retrieved is not None and cited - retrieved:
            violations.append(f"answer cites an un-retrieved {label}")

    if _PREDICTION.search(narrative):
        violations.append("answer contains a future-return prediction")

    boundary = answer.data_boundary
    source_urls = {source.url.casefold() for source in answer.sources}
    if "mock" in boundary and "real_data" in boundary:
        violations.append("answer boundary mixes mock and real data")
    if "real_data" in boundary and any(
        url.startswith("project://") or "fixture" in url for url in source_urls
    ):
        violations.append("real-data answer cites mock/project fixture evidence")
    if "mock" in boundary and any(url.startswith("http") for url in source_urls):
        violations.append("mock-data answer cites a live external data source")

    if (
        answer.status == AnswerStatus.NO_EVIDENCE
        and answer.narrative.facts != EMPTY_DATABASE_MESSAGE
    ):
        violations.append("empty database response does not use the required message")

    return AnswerSafetyReport(tuple(violations))
