"""Measure Hit@5 and MRR@5 against the approved Korean RAG benchmark."""

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.embeddings import get_query_embedder
from backend.app.retrieval.quality import (
    QualityBenchmarkError,
    load_quality_cases,
    measure_search_quality,
)
from backend.app.retrieval.repository import RetrievalRepository
from backend.app.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = ROOT / "data" / "search_quality" / "knowledge_v1.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="한국어 RAG 검색 품질을 측정합니다.")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-hit-at-k", type=float, default=1.0)
    parser.add_argument("--min-mrr-at-k", type=float, default=0.8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = load_quality_cases(args.benchmark.resolve())
    except QualityBenchmarkError as error:
        print(f"benchmark 검증 실패: {error}", file=sys.stderr)
        return 1
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        print("DATABASE_URL이 비어 있습니다 (.env 확인)", file=sys.stderr)
        return 1
    repository = RetrievalRepository(database_url, embedder=get_query_embedder())
    try:
        report = measure_search_quality(repository, cases, limit=args.limit)
    except psycopg.Error as error:
        print(f"검색 품질 측정 실패: {type(error).__name__}", file=sys.stderr)
        return 1
    print(
        f"Hit@{args.limit}={report.hit_at_k:.3f}, "
        f"MRR@{args.limit}={report.mrr_at_k:.3f} "
        f"({report.hit_count}/{report.case_count})"
    )
    if report.failed_case_ids:
        print(
            f"실패 케이스: {', '.join(report.failed_case_ids)}",
            file=sys.stderr,
        )
    return int(
        report.hit_at_k < args.min_hit_at_k or report.mrr_at_k < args.min_mrr_at_k
    )


if __name__ == "__main__":
    raise SystemExit(main())
