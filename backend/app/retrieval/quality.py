import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .repository import KnowledgeMatch


class KnowledgeQualityRepository(Protocol):
    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]: ...


@dataclass(frozen=True, slots=True)
class KnowledgeQualityCase:
    query: str
    relevant_source_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeQualityReport:
    case_count: int
    top_k: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_recall: float
    missed_queries: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "top_k": self.top_k,
            "hit_rate": round(self.hit_rate, 4),
            "mean_reciprocal_rank": round(self.mean_reciprocal_rank, 4),
            "mean_recall": round(self.mean_recall, 4),
            "missed_queries": list(self.missed_queries),
        }


def load_quality_cases(path: Path) -> tuple[KnowledgeQualityCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("quality benchmark must be a non-empty JSON array")
    cases: list[KnowledgeQualityCase] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("each quality case must be an object")
        query = raw.get("query")
        relevant = raw.get("relevant_source_urls")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("quality case query is required")
        if (
            not isinstance(relevant, list)
            or not relevant
            or not all(isinstance(item, str) and item for item in relevant)
        ):
            raise ValueError("relevant_source_urls must be a non-empty string list")
        cases.append(
            KnowledgeQualityCase(
                query=query,
                relevant_source_urls=tuple(relevant),
            )
        )
    return tuple(cases)


def evaluate_knowledge_search(
    repository: KnowledgeQualityRepository,
    cases: tuple[KnowledgeQualityCase, ...],
    *,
    top_k: int = 5,
) -> KnowledgeQualityReport:
    if not cases:
        raise ValueError("at least one quality case is required")
    if top_k < 1 or top_k > 50:
        raise ValueError("top_k must be between 1 and 50")

    hits = 0
    reciprocal_rank_total = 0.0
    recall_total = 0.0
    missed: list[str] = []
    for case in cases:
        results = repository.search_knowledge(case.query, limit=top_k)
        relevant = set(case.relevant_source_urls)
        ranked_urls = [match.source_url for match in results]
        relevant_ranks = [
            rank
            for rank, source_url in enumerate(ranked_urls, start=1)
            if source_url in relevant
        ]
        if relevant_ranks:
            hits += 1
            reciprocal_rank_total += 1 / min(relevant_ranks)
        else:
            missed.append(case.query)
        recall_total += len(relevant & set(ranked_urls)) / len(relevant)

    case_count = len(cases)
    return KnowledgeQualityReport(
        case_count=case_count,
        top_k=top_k,
        hit_rate=hits / case_count,
        mean_reciprocal_rank=reciprocal_rank_total / case_count,
        mean_recall=recall_total / case_count,
        missed_queries=tuple(missed),
    )
