from __future__ import annotations

import argparse
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from backend.app.settings import get_settings

from ._secrets import require_model_api_key, require_secret
from .naver_news_repository import (
    NaverNewsRepository,
    PreparedMarketNewsSummary,
)
from .news_article import NewsArticleFetchError, fetch_news_article
from .news_summarizer import NewsSummarizer, NewsSummaryError


def _summarize_with_retry(
    summarizer: NewsSummarizer,
    *,
    title: str,
    article_text: str,
):
    correction = None
    for attempt in range(3):
        try:
            return summarizer.summarize(
                title=title,
                article_text=article_text,
                correction=correction,
            )
        except NewsSummaryError as exc:
            if attempt == 2:
                raise
            if exc.draft is not None:
                correction = (
                    "아래 초안의 사실은 원문 범위에서만 유지하고, 각 문장을 60자 "
                    "이하로 고치세요. 전망에는 발언 주체를 넣으세요.\n"
                    f"<draft>{chr(10).join(exc.draft.summary_lines)}</draft>"
                )
            else:
                correction = (
                    "각 문장을 60자 이하로 줄이세요. 전망에는 발언 주체를 넣으세요."
                )
    raise AssertionError("summary retry loop must return or raise")


def run_market_news_resummary(
    *,
    database_url: str,
    api_key: str,
    model: str,
    prompt_version: str,
    expected_count: int = 89,
    dry_run: bool = False,
    concurrency: int = 5,
    delete_failed: bool = False,
) -> dict[str, Any]:
    if not 1 <= concurrency <= 10:
        raise ValueError("concurrency must be between 1 and 10")
    repository = NaverNewsRepository(database_url)
    items = repository.load_active_market_news_summaries()
    if len(items) != expected_count:
        return {
            "outcome": "failed",
            "error": "active_market_news_count_changed",
            "expected_count": expected_count,
            "active_count": len(items),
            "updated": 0,
        }

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

    def prepare(item):
        try:
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                article = fetch_news_article(client, item.original_url)
            summary = _summarize_with_retry(
                summarizer(),
                title=item.title,
                article_text=article.text,
            )
        except NewsArticleFetchError as exc:
            return None, exc.code
        except NewsSummaryError as exc:
            return None, exc.code
        return (
            PreparedMarketNewsSummary(
                item_id=item.item_id,
                summary_lines=summary.summary_lines,
                source_content_sha256=article.content_sha256,
            ),
            None,
        )

    failures: Counter[str] = Counter()
    prepared: list[PreparedMarketNewsSummary] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(prepare, item) for item in items]
        for future in as_completed(futures):
            summary, error = future.result()
            if error:
                failures[error] += 1
            elif summary is not None:
                prepared.append(summary)

    result: dict[str, Any] = {
        "expected_count": expected_count,
        "prepared": len(prepared),
        "failures": dict(failures),
        "prompt_version": prompt_version,
    }
    if not prepared:
        return {"outcome": "failed", "updated": 0, **result}
    if dry_run:
        return {"outcome": "ready", "updated": 0, **result}
    if delete_failed:
        updated, deleted = (
            repository.replace_prepared_market_news_summaries_and_delete_failed(
                summaries=prepared,
                expected_count=expected_count,
                model=model,
                prompt_version=prompt_version,
            )
        )
        return {
            "outcome": "succeeded",
            "updated": updated,
            "deleted": deleted,
            **result,
        }
    if len(prepared) != expected_count:
        return {"outcome": "failed", "updated": 0, **result}
    updated = repository.replace_active_market_news_summaries(
        summaries=prepared,
        expected_count=expected_count,
        model=model,
        prompt_version=prompt_version,
    )
    return {"outcome": "succeeded", "updated": updated, **result}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Atomically re-summarize every active market-news item."
    )
    parser.add_argument("--expected-count", type=int, default=89)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--delete-failed", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    result = run_market_news_resummary(
        database_url=require_secret(settings.database_url, "DATABASE_URL"),
        api_key=require_model_api_key(settings.news_summary_model, settings),
        model=settings.news_summary_model,
        prompt_version=settings.news_summary_prompt_version,
        expected_count=args.expected_count,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
        delete_failed=args.delete_failed,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] in {"ready", "succeeded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
