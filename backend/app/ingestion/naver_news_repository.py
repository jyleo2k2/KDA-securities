from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from backend.app.text_normalization import normalize_search_text

from .embeddings import vector_literal
from .naver_news import (
    NAVER_NEWS_ENDPOINT,
    NaverNewsAllItemsRejectedError,
    NaverNewsResponse,
)


class NaverNewsRepositoryError(RuntimeError):
    """A repository contract failure safe to expose in ingestion output."""


@dataclass(frozen=True, slots=True)
class NaverNewsLoadResult:
    inserted_count: int
    duplicate_count: int


@dataclass(frozen=True, slots=True)
class PendingNewsSummary:
    item_id: UUID
    title: str
    original_url: str


@dataclass(frozen=True, slots=True)
class StoredMarketNewsIdentity:
    canonical_url: str | None
    normalized_title_hash: str | None
    event_fingerprint: str | None
    source_content_sha256: str | None
    selection_embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ReadyMarketNews:
    search_query: str
    title: str
    description: str | None
    publisher: str
    original_url: str
    portal_url: str
    published_at: datetime
    raw_metadata: dict[str, Any]
    market_region: str
    market_topics: tuple[str, ...]
    canonical_url: str
    normalized_title_hash: str
    event_fingerprint: str
    selection_score: int
    selection_reasons: tuple[str, ...]
    selection_policy_version: str
    selection_embedding: tuple[float, ...]
    selection_embedding_model: str
    summary_lines: tuple[str, str, str]
    summary_model: str
    summary_prompt_version: str
    source_content_sha256: str


@dataclass(frozen=True, slots=True)
class MarketNewsRotationResult:
    inserted_count: int
    expired_count: int
    final_count: int
    held_for_full_batch: bool


def _parse_vector(value: object) -> tuple[float, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text.startswith("[") or not text.endswith("]"):
        raise NaverNewsRepositoryError("stored market-news embedding is invalid")
    body = text[1:-1]
    return tuple(float(part) for part in body.split(",")) if body else ()


class NaverNewsRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def start_run(
        self,
        *,
        query: str,
        display: int,
        start: int,
        sort: str,
        max_pages: int,
        max_age_days: int | None,
    ) -> tuple[UUID, int]:
        query = normalize_search_text(query)
        if not query:
            raise ValueError("query must not be empty")
        requested_params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": sort,
            "max_pages": max_pages,
            "max_age_days": max_age_days,
        }
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                insert into public.data_sources (
                    code, name, source_type, authority, base_url, metadata
                )
                values (
                    'naver_search_news', 'NAVER API HUB 뉴스 검색',
                    'news_api', 'NAVER Cloud', %s,
                    %s
                )
                on conflict (code) do update set
                    name = excluded.name,
                    base_url = excluded.base_url,
                    metadata = data_sources.metadata || excluded.metadata,
                    is_active = true,
                    updated_at = now()
                returning id
                """,
                (
                    NAVER_NEWS_ENDPOINT,
                    Jsonb(
                        {
                            "storage_policy": "metadata_and_derived_summary",
                            "article_body_storage": "transient_only",
                            "data_boundary": "news_metadata_and_summary",
                            "is_mock": False,
                        }
                    ),
                ),
            )
            source_row = cursor.fetchone()
            if source_row is None:
                raise NaverNewsRepositoryError(
                    "failed to resolve NAVER news data source"
                )
            source_id = int(source_row[0])
            cursor.execute(
                """
                insert into public.ingestion_runs (
                    source_id, endpoint, requested_params, status
                )
                values (%s, %s, %s, 'running')
                returning id
                """,
                (source_id, NAVER_NEWS_ENDPOINT, Jsonb(requested_params)),
            )
            run_row = cursor.fetchone()
            if run_row is None:
                raise NaverNewsRepositoryError(
                    "failed to create NAVER news ingestion run"
                )
            return run_row[0], source_id

    def start_market_run(self, *, queries: tuple[str, ...]) -> tuple[UUID, int]:
        if not queries or any(not normalize_search_text(query) for query in queries):
            raise ValueError("queries must contain non-empty values")
        requested_params = {
            "queries": list(queries),
            "sort": "date",
            "max_age_hours": 24,
            "daily_limit": 20,
        }
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                insert into public.data_sources (
                    code, name, source_type, authority, base_url, metadata
                )
                values (
                    'naver_search_news', 'NAVER API HUB 뉴스 검색',
                    'news_api', 'NAVER Cloud', %s, %s
                )
                on conflict (code) do update set
                    name = excluded.name,
                    base_url = excluded.base_url,
                    metadata = data_sources.metadata || excluded.metadata,
                    is_active = true,
                    updated_at = now()
                returning id
                """,
                (
                    NAVER_NEWS_ENDPOINT,
                    Jsonb(
                        {
                            "storage_policy": "selected_metadata_and_summary",
                            "article_body_storage": "transient_only",
                            "selection_policy": "market-news-v1",
                            "data_boundary": "news_metadata_and_summary",
                            "is_mock": False,
                        }
                    ),
                ),
            )
            source_row = cursor.fetchone()
            if source_row is None:
                raise NaverNewsRepositoryError(
                    "failed to resolve NAVER news data source"
                )
            source_id = int(source_row[0])
            cursor.execute(
                """
                insert into public.ingestion_runs (
                    source_id, endpoint, requested_params, status
                )
                values (%s, %s, %s, 'running')
                returning id
                """,
                (source_id, NAVER_NEWS_ENDPOINT, Jsonb(requested_params)),
            )
            run_row = cursor.fetchone()
            if run_row is None:
                raise NaverNewsRepositoryError(
                    "failed to create NAVER market-news ingestion run"
                )
            return run_row[0], source_id

    def complete_run(
        self,
        *,
        run_id: UUID,
        source_id: int,
        query: str,
        response: NaverNewsResponse,
    ) -> NaverNewsLoadResult:
        query = normalize_search_text(query)
        if not query:
            raise ValueError("query must not be empty")
        rows = [
            {
                "source_id": source_id,
                "ingestion_run_id": run_id,
                "search_query": query,
                "title": item.title,
                "description": item.description,
                "original_url": item.original_url,
                "portal_url": item.portal_url,
                "published_at": item.published_at,
                "raw_metadata": Jsonb(item.raw_metadata),
            }
            for item in response.items
        ]
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            if rows:
                cursor.executemany(
                    """
                    insert into public.news_items (
                        source_id, ingestion_run_id, search_query, title, description,
                        original_url, portal_url, published_at, raw_metadata
                    )
                    values (
                        %(source_id)s, %(ingestion_run_id)s, %(search_query)s,
                        %(title)s, %(description)s, %(original_url)s,
                        %(portal_url)s, %(published_at)s, %(raw_metadata)s
                    )
                    on conflict (source_id, original_url) do nothing
                    """,
                    rows,
                )
                inserted_count = max(cursor.rowcount, 0)
            else:
                inserted_count = 0
            duplicate_count = len(rows) - inserted_count
            published_times = [item.published_at for item in response.items]
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'succeeded',
                    completed_at = now(),
                    response_code = '200',
                    response_message = 'OK',
                    source_record_count = %s,
                    normalized_record_count = %s,
                    upserted_record_count = %s,
                    metadata = metadata || %s
                where id = %s and status = 'running'
                """,
                (
                    response.raw_item_count,
                    len(rows),
                    inserted_count,
                    Jsonb(
                        {
                            "total_search_results": response.total,
                            "rejected_record_count": response.rejected_count,
                            "rejection_reasons": list(response.rejected_reasons),
                            "inserted_record_count": inserted_count,
                            "duplicate_record_count": duplicate_count,
                            "pages_fetched": response.pages_fetched,
                            "newest_published_at": (
                                max(published_times).isoformat()
                                if published_times
                                else None
                            ),
                            "oldest_published_at": (
                                min(published_times).isoformat()
                                if published_times
                                else None
                            ),
                            "outcome": response.outcome,
                            "data_boundary": "news_metadata",
                            "is_mock": False,
                        }
                    ),
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise NaverNewsRepositoryError(
                    "NAVER ingestion run was not running during completion"
                )
        return NaverNewsLoadResult(
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
        )

    def claim_summary_items(
        self,
        *,
        limit: int,
        lookback_days: int = 7,
        max_attempts: int = 3,
        retry_after_minutes: int = 30,
    ) -> list[PendingNewsSummary]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if not 1 <= lookback_days <= 30:
            raise ValueError("lookback_days must be between 1 and 30")
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if not 1 <= retry_after_minutes <= 1440:
            raise ValueError("retry_after_minutes must be between 1 and 1440")
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                with candidates as (
                    select id
                    from public.news_items
                    where published_at >= now() - make_interval(days => %s)
                      and summary_attempt_count < %s
                      and (
                          summary_status = 'pending'
                          or (
                              summary_status in (
                                  'fetch_failed', 'model_failed',
                                  'validation_failed'
                              )
                              and summary_claimed_at < now()
                                  - make_interval(mins => %s)
                          )
                          or (
                              summary_status = 'processing'
                              and summary_claimed_at < now()
                                  - make_interval(mins => %s)
                          )
                      )
                    order by published_at desc, id
                    limit %s
                    for update skip locked
                )
                update public.news_items as news
                set summary_status = 'processing',
                    summary_attempt_count = news.summary_attempt_count + 1,
                    summary_claimed_at = now(),
                    summary_error_code = null,
                    summary_lines = array[]::text[]
                from candidates
                where news.id = candidates.id
                returning news.id, news.title, news.original_url
                """,
                (
                    lookback_days,
                    max_attempts,
                    retry_after_minutes,
                    retry_after_minutes,
                    limit,
                ),
            )
            return [PendingNewsSummary(*row) for row in cursor]

    def save_summary(
        self,
        *,
        item_id: UUID,
        summary_lines: tuple[str, str, str],
        model: str,
        prompt_version: str,
        content_sha256: str,
    ) -> None:
        if len(summary_lines) != 3 or any(not line.strip() for line in summary_lines):
            raise ValueError("summary_lines must contain exactly three non-empty lines")
        if not model or not prompt_version:
            raise ValueError("model and prompt_version are required")
        if len(content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in content_sha256
        ):
            raise ValueError("content_sha256 must be a SHA-256 hex digest")
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                update public.news_items
                set summary_lines = %s,
                    summary_status = 'succeeded',
                    summary_source_kind = 'article_body',
                    summary_model = %s,
                    summary_prompt_version = %s,
                    source_content_sha256 = %s,
                    summarized_at = now(),
                    summary_error_code = null,
                    summary_claimed_at = null,
                    license_status = 'review_required'
                where id = %s and summary_status = 'processing'
                """,
                (
                    list(summary_lines),
                    model,
                    prompt_version,
                    content_sha256,
                    item_id,
                ),
            )
            if cursor.rowcount != 1:
                raise NaverNewsRepositoryError(
                    "news summary item was not processing during completion"
                )

    def fail_summary(
        self,
        *,
        item_id: UUID,
        status: str,
        error_code: str,
    ) -> None:
        allowed_statuses = {"fetch_failed", "model_failed", "validation_failed"}
        if status not in allowed_statuses:
            raise ValueError(f"unsupported summary failure status: {status}")
        if not error_code or len(error_code) > 100:
            raise ValueError("error_code must contain between 1 and 100 characters")
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                update public.news_items
                set summary_lines = array[]::text[],
                    summary_status = %s,
                    summary_source_kind = null,
                    summary_model = null,
                    summary_prompt_version = null,
                    source_content_sha256 = null,
                    summarized_at = null,
                    summary_error_code = %s
                where id = %s and summary_status = 'processing'
                """,
                (status, error_code, item_id),
            )
            if cursor.rowcount != 1:
                raise NaverNewsRepositoryError(
                    "news summary item was not processing during failure handling"
                )

    def load_market_identities(self) -> list[StoredMarketNewsIdentity]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    canonical_url,
                    normalized_title_hash,
                    event_fingerprint,
                    source_content_sha256,
                    selection_embedding::text
                from public.news_items
                where selection_policy_version is not null
                order by published_at desc nulls last, fetched_at desc, id
                limit 100
                """
            )
            return [
                StoredMarketNewsIdentity(
                    canonical_url=row[0],
                    normalized_title_hash=row[1],
                    event_fingerprint=row[2],
                    source_content_sha256=row[3],
                    selection_embedding=_parse_vector(row[4]),
                )
                for row in cursor
            ]

    def complete_market_run(
        self,
        *,
        run_id: UUID,
        source_id: int,
        articles: list[ReadyMarketNews],
        raw_record_count: int,
        candidate_count: int,
        selected_count: int,
        rejected_record_count: int,
        processing_failures: dict[str, int],
    ) -> MarketNewsRotationResult:
        if len(articles) > 20:
            raise ValueError("articles must contain at most 20 items")
        if not len(articles) <= selected_count <= 20:
            raise ValueError("selected_count must cover articles and be at most 20")
        rows = [
            {
                "source_id": source_id,
                "ingestion_run_id": run_id,
                "search_query": article.search_query,
                "title": article.title,
                "description": article.description,
                "publisher": article.publisher,
                "original_url": article.original_url,
                "portal_url": article.portal_url,
                "published_at": article.published_at,
                "raw_metadata": Jsonb(article.raw_metadata),
                "market_region": article.market_region,
                "market_topics": list(article.market_topics),
                "canonical_url": article.canonical_url,
                "normalized_title_hash": article.normalized_title_hash,
                "event_fingerprint": article.event_fingerprint,
                "selection_score": article.selection_score,
                "selection_reasons": list(article.selection_reasons),
                "selection_policy_version": article.selection_policy_version,
                "selection_embedding": vector_literal(
                    list(article.selection_embedding)
                ),
                "selection_embedding_model": article.selection_embedding_model,
                "summary_lines": list(article.summary_lines),
                "summary_model": article.summary_model,
                "summary_prompt_version": article.summary_prompt_version,
                "source_content_sha256": article.source_content_sha256,
            }
            for article in articles
        ]
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "select pg_advisory_xact_lock(hashtext(%s))",
                ("naver_market_news_rotation",),
            )
            cursor.execute(
                """
                select count(*)
                from public.news_items
                where selection_policy_version is not null and is_active
                """
            )
            count_row = cursor.fetchone()
            if count_row is None:
                raise NaverNewsRepositoryError("failed to count stored news")
            current_count = int(count_row[0])
            held_for_full_batch = current_count >= 100 and len(rows) < 20
            expired_count = 0
            if current_count >= 100 and len(rows) == 20:
                cursor.execute(
                    """
                    with oldest as (
                        select news.id
                        from public.news_items as news
                        where news.selection_policy_version is not null
                          and news.is_active
                        order by
                            news.published_at asc nulls first,
                            news.fetched_at asc,
                            news.id
                        limit 20
                        for update
                    )
                    update public.news_items as news
                    set is_active = false
                    from oldest
                    where news.id = oldest.id
                    """
                )
                expired_count = max(cursor.rowcount, 0)
                rows_to_insert = rows
            elif current_count < 100:
                rows_to_insert = rows[: 100 - current_count]
            else:
                rows_to_insert = []

            if rows_to_insert:
                cursor.executemany(
                    """
                    insert into public.news_items (
                        source_id, ingestion_run_id, search_query, title,
                        description, publisher, original_url, portal_url,
                        published_at, raw_metadata, market_region, market_topics,
                        canonical_url, normalized_title_hash, event_fingerprint,
                        selection_score, selection_reasons,
                        selection_policy_version, selection_embedding,
                        selection_embedding_model, summary_lines, summary_status,
                        summary_source_kind, summary_model,
                        summary_prompt_version, source_content_sha256,
                        summarized_at, summary_attempt_count, license_status
                    )
                    values (
                        %(source_id)s, %(ingestion_run_id)s, %(search_query)s,
                        %(title)s, %(description)s, %(publisher)s,
                        %(original_url)s, %(portal_url)s, %(published_at)s,
                        %(raw_metadata)s, %(market_region)s, %(market_topics)s,
                        %(canonical_url)s, %(normalized_title_hash)s,
                        %(event_fingerprint)s, %(selection_score)s,
                        %(selection_reasons)s, %(selection_policy_version)s,
                        %(selection_embedding)s::extensions.vector,
                        %(selection_embedding_model)s, %(summary_lines)s,
                        'succeeded', 'article_body', %(summary_model)s,
                        %(summary_prompt_version)s, %(source_content_sha256)s,
                        now(), 1, 'review_required'
                    )
                    on conflict do nothing
                    """,
                    rows_to_insert,
                )
                inserted_count = max(cursor.rowcount, 0)
            else:
                inserted_count = 0

            cursor.execute(
                """
                select count(*)
                from public.news_items
                where selection_policy_version is not null and is_active
                """
            )
            final_row = cursor.fetchone()
            if final_row is None:
                raise NaverNewsRepositoryError("failed to verify stored news count")
            final_count = int(final_row[0])
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'succeeded',
                    completed_at = now(),
                    response_code = '200',
                    response_message = 'OK',
                    source_record_count = %s,
                    normalized_record_count = %s,
                    upserted_record_count = %s,
                    metadata = metadata || %s
                where id = %s and status = 'running'
                """,
                (
                    raw_record_count,
                    candidate_count,
                    inserted_count,
                    Jsonb(
                        {
                            "selection_policy_version": "market-news-v1",
                            "rejected_record_count": rejected_record_count,
                            "selected_record_count": selected_count,
                            "summarized_record_count": len(articles),
                            "processing_failures": processing_failures,
                            "expired_record_count": expired_count,
                            "final_news_count": final_count,
                            "held_for_full_batch": held_for_full_batch,
                            "data_boundary": "news_metadata_and_summary",
                            "is_mock": False,
                        }
                    ),
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise NaverNewsRepositoryError(
                    "NAVER market-news run was not running during completion"
                )
        return MarketNewsRotationResult(
            inserted_count=inserted_count,
            expired_count=expired_count,
            final_count=final_count,
            held_for_full_batch=held_for_full_batch,
        )

    def fail_run(self, run_id: UUID, error: Exception) -> bool:
        if isinstance(error, psycopg.Error):
            safe_message = f"{type(error).__name__}: database operation failed"
        else:
            safe_message = f"{type(error).__name__}: {error}"[:1000]
        failure_metadata: dict[str, object] = {
            "outcome": "failed",
            "data_boundary": "news_metadata",
            "is_mock": False,
        }
        if isinstance(error, NaverNewsAllItemsRejectedError):
            failure_metadata.update(
                {
                    "total_search_results": error.total,
                    "raw_record_count": error.raw_item_count,
                    "rejected_record_count": error.rejected_count,
                    "rejection_reasons": list(error.rejected_reasons),
                }
            )
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'failed',
                    completed_at = now(),
                    error_message = %s,
                    metadata = metadata || %s
                where id = %s and status = 'running'
                """,
                (
                    safe_message,
                    Jsonb(failure_metadata),
                    run_id,
                ),
            )
            return cursor.rowcount == 1
