from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from backend.app.settings import get_settings

from ._secrets import require_secret
from .naver_news_repository import NaverNewsRepository, PendingNewsSummary
from .news_article import NewsArticleFetchError, fetch_news_article
from .news_summarizer import NewsSummarizer, NewsSummaryError


def run_summary_worker(
    *,
    database_url: str,
    api_key: str,
    model: str,
    prompt_version: str,
    limit: int = 1000,
    concurrency: int = 5,
    lookback_days: int = 7,
    max_attempts: int = 3,
    retry_after_minutes: int = 30,
) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not 1 <= concurrency <= 10:
        raise ValueError("concurrency must be between 1 and 10")

    repository = NaverNewsRepository(database_url)
    thread_state = threading.local()

    def summarizer() -> NewsSummarizer:
        current = getattr(thread_state, "summarizer", None)
        if current is None:
            current = NewsSummarizer(
                api_key=api_key,
                model=model,
                prompt_version=prompt_version,
            )
            thread_state.summarizer = current
        return current

    def process(item: PendingNewsSummary) -> str:
        try:
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                article = fetch_news_article(client, item.original_url)
        except NewsArticleFetchError as exc:
            repository.fail_summary(
                item_id=item.item_id,
                status="fetch_failed",
                error_code=exc.code,
            )
            return "fetch_failed"

        try:
            summary = summarizer().summarize(
                title=item.title,
                article_text=article.text,
            )
        except NewsSummaryError as exc:
            status = (
                "validation_failed"
                if exc.code == "validation_failed"
                else "model_failed"
            )
            repository.fail_summary(
                item_id=item.item_id,
                status=status,
                error_code=exc.code,
            )
            return status

        repository.save_summary(
            item_id=item.item_id,
            summary_lines=summary.summary_lines,
            model=model,
            prompt_version=prompt_version,
            content_sha256=article.content_sha256,
        )
        return "succeeded"

    counts = {
        "claimed": 0,
        "succeeded": 0,
        "fetch_failed": 0,
        "model_failed": 0,
        "validation_failed": 0,
    }
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while counts["claimed"] < limit:
            batch_size = min(concurrency * 2, limit - counts["claimed"])
            items = repository.claim_summary_items(
                limit=batch_size,
                lookback_days=lookback_days,
                max_attempts=max_attempts,
                retry_after_minutes=retry_after_minutes,
            )
            if not items:
                break
            counts["claimed"] += len(items)
            futures = [executor.submit(process, item) for item in items]
            for future in as_completed(futures):
                counts[future.result()] += 1

    failed = (
        counts["fetch_failed"]
        + counts["model_failed"]
        + counts["validation_failed"]
    )
    return {
        **counts,
        "outcome": "partial" if failed else "succeeded",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch original NAVER news pages and store three-line summaries."
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-after-minutes", type=int, default=30)
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    database_url = require_secret(settings.database_url, "DATABASE_URL")
    api_key = require_secret(settings.anthropic_api_key, "ANTHROPIC_API_KEY")

    result = run_summary_worker(
        database_url=database_url,
        api_key=api_key,
        model=settings.news_summary_model,
        prompt_version=settings.news_summary_prompt_version,
        limit=args.limit,
        concurrency=args.concurrency,
        lookback_days=args.lookback_days,
        max_attempts=args.max_attempts,
        retry_after_minutes=args.retry_after_minutes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
