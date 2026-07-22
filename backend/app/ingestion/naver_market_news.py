from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import psycopg

from backend.app.settings import get_settings

from .embeddings import EMBEDDING_MODEL, get_query_embedder
from .market_news_policy import (
    MARKET_QUERIES,
    MAX_DAILY_ARTICLES,
    SELECTION_POLICY_VERSION,
    MarketNewsCandidate,
    build_candidate,
    embed_candidates,
    select_market_candidates,
)
from .naver_news import NaverNewsApiError, fetch_naver_news
from .naver_news_repository import (
    NaverNewsRepository,
    NaverNewsRepositoryError,
    ReadyMarketNews,
)
from .news_article import NewsArticleFetchError, fetch_news_article
from .news_summarizer import NewsSummarizer, NewsSummaryError


class MarketNewsIngestionError(RuntimeError):
    """Sanitized market-news pipeline failure."""


def _unique_candidates(
    candidates: list[MarketNewsCandidate],
) -> list[MarketNewsCandidate]:
    unique: dict[tuple[str, str], MarketNewsCandidate] = {}
    for candidate in candidates:
        key = (candidate.canonical_url, candidate.normalized_title_hash)
        previous = unique.get(key)
        if previous is None or (candidate.score, candidate.item.published_at) > (
            previous.score,
            previous.item.published_at,
        ):
            unique[key] = candidate
    return list(unique.values())


def _record_failure(
    repository: NaverNewsRepository,
    run_id: UUID | None,
    error: Exception,
) -> bool:
    if run_id is None:
        return False
    try:
        return repository.fail_run(run_id, error)
    except psycopg.Error:
        return False


def run_market_news_ingestion(
    *,
    client_id: str,
    client_secret: str,
    database_url: str,
    api_key: str,
    model: str,
    prompt_version: str,
    now: datetime | None = None,
    display: int = 50,
    max_pages: int = 1,
    window_start: datetime | None = None,
) -> dict[str, Any]:
    if not all(
        value.strip()
        for value in (
            client_id,
            client_secret,
            database_url,
            api_key,
            model,
            prompt_version,
        )
    ):
        raise ValueError("all market-news configuration values are required")
    if not 1 <= display <= 100:
        raise ValueError("display must be between 1 and 100")
    if not 1 <= max_pages <= 10:
        raise ValueError("max_pages must be between 1 and 10")
    reference_time = now or datetime.now(UTC)
    if reference_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if window_start is not None:
        if window_start.tzinfo is None:
            raise ValueError("window_start must be timezone-aware")
        if not window_start < reference_time:
            raise ValueError("window_start must be before now")
        if reference_time - window_start > timedelta(hours=24):
            raise ValueError("market-news windows cannot exceed 24 hours")

    repository = NaverNewsRepository(database_url)
    run_id: UUID | None = None
    try:
        run_id, source_id = repository.start_market_run(
            queries=tuple(query.query for query in MARKET_QUERIES),
            max_age_hours=24,
            max_pages=max_pages,
            window_end=reference_time if window_start is not None else None,
        )
        raw_record_count = 0
        api_rejections = 0
        candidates: list[MarketNewsCandidate] = []
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            for query in MARKET_QUERIES:
                current_start = 1
                for _ in range(max_pages):
                    response = fetch_naver_news(
                        client,
                        client_id=client_id,
                        client_secret=client_secret,
                        query=query.query,
                        display=display,
                        start=current_start,
                        sort="date",
                    )
                    raw_record_count += response.raw_item_count
                    api_rejections += response.rejected_count
                    for item in response.items:
                        if window_start is None:
                            in_window = item.published_at >= reference_time - timedelta(
                                hours=24
                            )
                        else:
                            in_window = (
                                window_start
                                <= item.published_at
                                < reference_time
                            )
                        if not in_window:
                            continue
                        candidate = build_candidate(item, query, now=reference_time)
                        if candidate is not None:
                            candidates.append(candidate)

                    next_start = current_start + display
                    reached_window_start = window_start is not None and any(
                        item.published_at < window_start for item in response.items
                    )
                    if (
                        reached_window_start
                        or response.raw_item_count < display
                        or next_start > 1000
                        or next_start > response.total
                    ):
                        break
                    current_start = next_start

            candidates = _unique_candidates(candidates)
            identities = repository.load_market_identities()
            embedder = get_query_embedder()
            if embedder is None:
                raise MarketNewsIngestionError(
                    "BGE-M3 dependencies are required for duplicate detection"
                )
            try:
                embedded = embed_candidates(candidates, embedder)
            except Exception as exc:
                raise MarketNewsIngestionError(
                    "BGE-M3 duplicate detection failed"
                ) from exc
            candidate_pool = select_market_candidates(
                embedded,
                existing_urls={
                    identity.canonical_url
                    for identity in identities
                    if identity.canonical_url
                },
                existing_title_hashes={
                    identity.normalized_title_hash
                    for identity in identities
                    if identity.normalized_title_hash
                },
                existing_event_fingerprints={
                    identity.event_fingerprint
                    for identity in identities
                    if identity.event_fingerprint
                },
                existing_embeddings=[
                    identity.selection_embedding
                    for identity in identities
                    if identity.selection_embedding
                ],
                limit=None,
            )

            summarizer = NewsSummarizer(
                api_key=api_key,
                model=model,
                prompt_version=prompt_version,
            )
            content_hashes = {
                identity.source_content_sha256
                for identity in identities
                if identity.source_content_sha256
            }
            failures: Counter[str] = Counter()
            ready: list[ReadyMarketNews] = []
            for candidate in candidate_pool:
                if len(ready) == MAX_DAILY_ARTICLES:
                    break
                try:
                    article = fetch_news_article(client, candidate.item.original_url)
                except NewsArticleFetchError as exc:
                    failures[exc.code] += 1
                    continue
                if article.content_sha256 in content_hashes:
                    failures["duplicate_content"] += 1
                    continue
                summary = None
                correction = None
                for attempt in range(3):
                    try:
                        summary = summarizer.summarize(
                            title=candidate.item.title,
                            article_text=article.text,
                            correction=correction,
                        )
                        break
                    except NewsSummaryError as exc:
                        if exc.draft is not None:
                            correction = (
                                "아래 초안의 사실은 원문 범위에서만 유지하세요. "
                                "각 문장을 "
                                "60자 이하로 고치세요. 전망에는 발언 주체를 넣으세요.\n"
                                f"<draft>{chr(10).join(exc.draft.summary_lines)}</draft>"
                            )
                        else:
                            correction = (
                                "각 문장을 60자 이하로 줄이세요. "
                                "전망에는 발언 주체를 넣으세요."
                            )
                        if attempt:
                            failures[exc.code] += 1
                if summary is None:
                    continue
                content_hashes.add(article.content_sha256)
                ready.append(
                    ReadyMarketNews(
                        search_query=candidate.search_query,
                        title=candidate.item.title,
                        description=candidate.item.description,
                        publisher=candidate.publisher,
                        original_url=candidate.item.original_url,
                        portal_url=candidate.item.portal_url or "",
                        published_at=candidate.item.published_at,
                        raw_metadata=dict(candidate.item.raw_metadata),
                        market_region=candidate.region,
                        market_topics=candidate.topics,
                        canonical_url=candidate.canonical_url,
                        normalized_title_hash=candidate.normalized_title_hash,
                        event_fingerprint=candidate.event_fingerprint,
                        selection_score=candidate.score,
                        selection_reasons=candidate.reasons,
                        selection_policy_version=SELECTION_POLICY_VERSION,
                        selection_embedding=candidate.embedding,
                        selection_embedding_model=EMBEDDING_MODEL,
                        summary_lines=summary.summary_lines,
                        summary_model=model,
                        summary_prompt_version=prompt_version,
                        source_content_sha256=article.content_sha256,
                    )
                )

        rejected_record_count = raw_record_count - len(candidates)
        rotation = repository.complete_market_run(
            run_id=run_id,
            source_id=source_id,
            articles=ready,
            raw_record_count=raw_record_count,
            candidate_count=len(candidates),
            selected_count=min(len(candidate_pool), MAX_DAILY_ARTICLES),
            rejected_record_count=max(rejected_record_count, api_rejections),
            processing_failures=dict(failures),
        )
    except (
        NaverNewsApiError,
        NaverNewsRepositoryError,
        MarketNewsIngestionError,
    ) as exc:
        return {
            "outcome": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "failure_recorded": _record_failure(repository, run_id, exc),
        }
    except psycopg.Error as exc:
        return {
            "outcome": "failed",
            "error_type": type(exc).__name__,
            "error": "database operation failed",
            "failure_recorded": _record_failure(repository, run_id, exc),
        }

    return {
        "outcome": "succeeded",
        "policy_version": SELECTION_POLICY_VERSION,
        "raw_received": raw_record_count,
        "eligible_candidates": len(candidates),
        "selected": min(len(candidate_pool), MAX_DAILY_ARTICLES),
        "summarized": len(ready),
        "inserted": rotation.inserted_count,
        "expired": rotation.expired_count,
        "stored_total": rotation.final_count,
        "held_for_full_batch": rotation.held_for_full_batch,
        "processing_failures": dict(failures),
    }


def main() -> int:
    settings = get_settings()
    required = {
        "NAVER_API_HUB_CLIENT_ID": settings.naver_api_hub_client_id,
        "NAVER_API_HUB_CLIENT_SECRET": settings.naver_api_hub_client_secret,
        "DATABASE_URL": settings.database_url,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit(f"missing required configuration: {', '.join(missing)}")
    result = run_market_news_ingestion(
        client_id=required["NAVER_API_HUB_CLIENT_ID"].get_secret_value(),
        client_secret=required["NAVER_API_HUB_CLIENT_SECRET"].get_secret_value(),
        database_url=required["DATABASE_URL"].get_secret_value(),
        api_key=required["ANTHROPIC_API_KEY"].get_secret_value(),
        model=settings.news_summary_model,
        prompt_version=settings.news_summary_prompt_version,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
