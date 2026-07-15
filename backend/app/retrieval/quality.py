"""Offline relevance metrics for the approved knowledge benchmark."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .repository import KnowledgeMatch
from .search_ranking import search_tokens, text_matches_all


class KnowledgeSearch(Protocol):
    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]: ...


class QualityBenchmarkError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QualityCase:
    case_id: str
    query: str
    expected_source_url: str
    required_content_terms: tuple[str, ...]
    critical_top1: bool = False


@dataclass(frozen=True, slots=True)
class QualityReport:
    k: int
    case_count: int
    hit_count: int
    hit_at_k: float
    hit_at_1: float
    mrr_at_k: float
    failed_case_ids: tuple[str, ...]
    critical_top1_failed_case_ids: tuple[str, ...]


def _required_text(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise QualityBenchmarkError(f"benchmark field {key!r} is required")
    return value.strip()


def load_quality_cases(path: Path) -> tuple[QualityCase, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualityBenchmarkError("failed to read quality benchmark") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise QualityBenchmarkError("quality benchmark schema_version must be 1")
    entries = payload.get("cases")
    if not isinstance(entries, list) or len(entries) < 10:
        raise QualityBenchmarkError("quality benchmark requires at least 10 cases")
    cases: list[QualityCase] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise QualityBenchmarkError("quality benchmark cases must be objects")
        terms = entry.get("required_content_terms")
        if (
            not isinstance(terms, list)
            or not terms
            or not all(isinstance(term, str) and term.strip() for term in terms)
        ):
            raise QualityBenchmarkError("required_content_terms must be non-empty")
        critical_top1 = entry.get("critical_top1", False)
        if not isinstance(critical_top1, bool):
            raise QualityBenchmarkError("critical_top1 must be boolean")
        cases.append(
            QualityCase(
                case_id=_required_text(entry, "id"),
                query=_required_text(entry, "query"),
                expected_source_url=_required_text(entry, "expected_source_url"),
                required_content_terms=tuple(term.strip() for term in terms),
                critical_top1=critical_top1,
            )
        )
    if len({case.case_id for case in cases}) != len(cases):
        raise QualityBenchmarkError("quality benchmark case ids must be unique")
    normalized_queries = {" ".join(case.query.lower().split()) for case in cases}
    if len(normalized_queries) != len(cases):
        raise QualityBenchmarkError("quality benchmark queries must be unique")
    if not any(case.critical_top1 for case in cases):
        raise QualityBenchmarkError("quality benchmark requires a critical top-1 case")
    return tuple(cases)


def _canonical_source_url(url: str) -> str:
    return url.partition("#")[0].rstrip("/")


def _is_relevant(match: KnowledgeMatch, case: QualityCase) -> bool:
    if _canonical_source_url(match.source_url) != _canonical_source_url(
        case.expected_source_url
    ):
        return False
    text = f"{match.title}\n{match.content}"
    return all(
        text_matches_all(search_tokens(term), text)
        for term in case.required_content_terms
    )


def measure_search_quality(
    repository: KnowledgeSearch,
    cases: tuple[QualityCase, ...],
    *,
    limit: int = 5,
) -> QualityReport:
    if not cases:
        raise ValueError("quality cases are required")
    bounded_limit = max(1, min(limit, 20))
    reciprocal_rank_sum = 0.0
    hits = 0
    hits_at_1 = 0
    failed: list[str] = []
    critical_top1_failed: list[str] = []
    for case in cases:
        results = repository.search_knowledge(case.query, limit=bounded_limit)
        rank = next(
            (
                index
                for index, result in enumerate(results, start=1)
                if _is_relevant(result, case)
            ),
            None,
        )
        if rank is None:
            failed.append(case.case_id)
        else:
            hits += 1
            reciprocal_rank_sum += 1 / rank
            if rank == 1:
                hits_at_1 += 1
        if case.critical_top1 and rank != 1:
            critical_top1_failed.append(case.case_id)
    case_count = len(cases)
    return QualityReport(
        k=bounded_limit,
        case_count=case_count,
        hit_count=hits,
        hit_at_k=hits / case_count,
        hit_at_1=hits_at_1 / case_count,
        mrr_at_k=reciprocal_rank_sum / case_count,
        failed_case_ids=tuple(failed),
        critical_top1_failed_case_ids=tuple(critical_top1_failed),
    )
