"""Ingest only documents listed in the approved knowledge manifest."""

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.knowledge import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_MANIFEST,
    load_approved_documents,
)
from backend.app.retrieval.knowledge_repository import KnowledgeWriteRepository
from backend.app.settings import get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="허가 manifest의 검증 지식만 Supabase에 적재합니다."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        documents = load_approved_documents(
            args.manifest.resolve(), max_chars=args.max_chars
        )
    except ValueError as error:
        print(f"manifest 검증 실패: {error}", file=sys.stderr)
        return 1
    chunk_count = sum(len(document.chunks) for document in documents)
    print(f"manifest 검증 완료: 문서 {len(documents)}개, 청크 {chunk_count}개")
    nearest_review = min(
        documents,
        key=lambda document: str(document.metadata["review_due_date"]),
    )
    print(
        "다음 검토: "
        f"{nearest_review.metadata['document_id']} "
        f"({nearest_review.metadata['review_due_date']})"
    )
    if args.validate_only:
        return 0

    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        print("DATABASE_URL이 비어 있습니다 (.env 확인)", file=sys.stderr)
        return 1
    repository = KnowledgeWriteRepository(database_url)
    failures = 0
    for document in documents:
        try:
            result = repository.ingest_document(document)
        except (psycopg.Error, RuntimeError, ValueError, OSError) as error:
            failures += 1
            print(
                f"적재 실패: {document.title} ({type(error).__name__})",
                file=sys.stderr,
            )
        else:
            print(f"적재 완료: {document.title} ({result.chunk_count}개 청크)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
