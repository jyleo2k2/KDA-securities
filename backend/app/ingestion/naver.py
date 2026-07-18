import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import psycopg

from backend.app.settings import get_settings
from backend.app.text_normalization import normalize_search_text

from ._secrets import optional_secret, require_secret
from .naver_news import (
    NaverNewsAllItemsRejectedError,
    NaverNewsApiError,
    NaverNewsResponse,
    fetch_naver_news,
)
from .naver_news_repository import (
    NaverNewsLoadResult,
    NaverNewsRepository,
    NaverNewsRepositoryError,
)

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
    max_pages: int = 1,
    max_age_days: int | None = None,
    now: datetime | None = None,
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
    if not 1 <= max_pages <= 10:
        raise ValueError("max_pages must be between 1 and 10")
    if max_age_days is not None and not 1 <= max_age_days <= 365:
        raise ValueError("max_age_days must be between 1 and 365")
    if max_age_days is not None and sort != "date":
        raise ValueError("max_age_days requires date sorting")

    repository = None if fetch_only else NaverNewsRepository(database_url or "")
    run_id = None
    source_id = None
    load_result = NaverNewsLoadResult(inserted_count=0, duplicate_count=0)
    try:
        if repository:
            run_id, source_id = repository.start_run(
                query=canonical_query,
                display=display,
                start=start,
                sort=sort,
                max_pages=max_pages,
                max_age_days=max_age_days,
            )
        with httpx.Client(timeout=30.0) as client:
            current_start = start
            cutoff = (
                (now or datetime.now(UTC)) - timedelta(days=max_age_days)
                if max_age_days is not None
                else None
            )
            items = []
            rejected_reasons: list[str] = []
            raw_item_count = 0
            total = 0
            pages_fetched = 0
            for _ in range(max_pages):
                page = fetch_naver_news(
                    client,
                    client_id=client_id,
                    client_secret=client_secret,
                    query=canonical_query,
                    display=display,
                    start=current_start,
                    sort=sort,
                )
                pages_fetched += 1
                total = max(total, page.total)
                raw_item_count += page.raw_item_count
                rejected_reasons.extend(page.rejected_reasons)
                reached_cutoff = cutoff is not None and any(
                    item.published_at < cutoff for item in page.items
                )
                items.extend(
                    item
                    for item in page.items
                    if cutoff is None or item.published_at >= cutoff
                )
                next_start = current_start + display
                if (
                    reached_cutoff
                    or page.raw_item_count < display
                    or next_start > 1000
                    or next_start > page.total
                ):
                    break
                current_start = next_start
            response = NaverNewsResponse(
                total=total,
                start=start,
                display=raw_item_count,
                raw_item_count=raw_item_count,
                items=items,
                rejected_reasons=tuple(rejected_reasons),
                pages_fetched=pages_fetched,
            )
        if repository and run_id is not None and source_id is not None:
            load_result = repository.complete_run(
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
        "inserted": load_result.inserted_count,
        "duplicates": load_result.duplicate_count,
        "rejected": response.rejected_count,
        "rejection_reasons": list(response.rejected_reasons),
        "pages_fetched": response.pages_fetched,
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
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--max-age-days", type=int)
    parser.add_argument("--fetch-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    client_id = require_secret(
        settings.naver_api_hub_client_id, "NAVER API HUB credentials"
    )
    client_secret = require_secret(
        settings.naver_api_hub_client_secret, "NAVER API HUB credentials"
    )

    database_url = optional_secret(settings.database_url)
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
        max_pages=args.max_pages,
        max_age_days=args.max_age_days,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
