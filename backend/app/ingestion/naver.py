import argparse
import json
from typing import Any
from uuid import UUID

import httpx
import psycopg

from backend.app.settings import get_settings
from backend.app.text_normalization import normalize_search_text

from .naver_news import (
    NaverNewsAllItemsRejectedError,
    NaverNewsApiError,
    fetch_naver_news,
)
from .naver_news_repository import NaverNewsRepository, NaverNewsRepositoryError

_EXPECTED_INGESTION_ERRORS = (
    NaverNewsApiError,
    NaverNewsRepositoryError,
    psycopg.Error,
)


def _record_failure(
    repository: NaverNewsRepository | None,
    run_id: UUID | None,
    error: Exception,
) -> bool:
    if repository is None or run_id is None:
        return False
    try:
        return repository.fail_run(run_id, error)
    except psycopg.Error:
        return False


def run_live_ingestion(
    *,
    client_id: str,
    client_secret: str,
    database_url: str | None,
    fetch_only: bool,
    query: str,
    display: int,
    start: int,
    sort: str,
) -> dict[str, Any]:
    canonical_query = normalize_search_text(query)
    if not canonical_query:
        raise ValueError("query must not be empty")
    if not 1 <= display <= 100:
        raise ValueError("display must be between 1 and 100")
    if not 1 <= start <= 1000:
        raise ValueError("start must be between 1 and 1000")
    if sort not in {"date", "sim"}:
        raise ValueError("sort must be date or sim")

    repository = None if fetch_only else NaverNewsRepository(database_url or "")
    run_id = None
    source_id = None
    try:
        if repository:
            run_id, source_id = repository.start_run(
                query=canonical_query,
                display=display,
                start=start,
                sort=sort,
            )
        with httpx.Client(timeout=30.0) as client:
            response = fetch_naver_news(
                client,
                client_id=client_id,
                client_secret=client_secret,
                query=canonical_query,
                display=display,
                start=start,
                sort=sort,
            )
        if repository and run_id is not None and source_id is not None:
            repository.complete_run(
                run_id=run_id,
                source_id=source_id,
                query=canonical_query,
                response=response,
            )
    except _EXPECTED_INGESTION_ERRORS as exc:
        message = (
            "database operation failed" if isinstance(exc, psycopg.Error) else str(exc)
        )
        result = {
            "database": "not_requested" if fetch_only else "failed",
            "query": canonical_query,
            "sort": sort,
            "outcome": "failed",
            "error_type": type(exc).__name__,
            "error": message,
            "failure_recorded": _record_failure(repository, run_id, exc),
        }
        if isinstance(exc, NaverNewsAllItemsRejectedError):
            result.update(
                {
                    "total": exc.total,
                    "raw_received": exc.raw_item_count,
                    "received": 0,
                    "rejected": exc.rejected_count,
                    "rejection_reasons": list(exc.rejected_reasons),
                }
            )
        return result

    return {
        "database": "not_requested" if fetch_only else "loaded",
        "query": canonical_query,
        "total": response.total,
        "raw_received": response.raw_item_count,
        "received": len(response.items),
        "rejected": response.rejected_count,
        "rejection_reasons": list(response.rejected_reasons),
        "sort": sort,
        "outcome": response.outcome,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call NAVER API HUB news search and optionally upsert metadata."
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--display", type=int, default=10)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--sort", choices=("date", "sim"), default="date")
    parser.add_argument("--fetch-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if (
        settings.naver_api_hub_client_id is None
        or settings.naver_api_hub_client_secret is None
    ):
        raise SystemExit("NAVER API HUB credentials are required")
    client_id = settings.naver_api_hub_client_id.get_secret_value().strip()
    client_secret = settings.naver_api_hub_client_secret.get_secret_value().strip()
    if not client_id or not client_secret:
        raise SystemExit("NAVER API HUB credentials are required")

    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else None
    )
    if not args.fetch_only and not database_url:
        raise SystemExit("DATABASE_URL is required unless --fetch-only is used")

    result = run_live_ingestion(
        client_id=client_id,
        client_secret=client_secret,
        database_url=database_url,
        fetch_only=args.fetch_only,
        query=args.query,
        display=args.display,
        start=args.start,
        sort=args.sort,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
