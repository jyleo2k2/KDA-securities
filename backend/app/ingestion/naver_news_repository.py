from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from backend.app.text_normalization import normalize_search_text

from .naver_news import NAVER_NEWS_ENDPOINT, NaverNewsResponse


class NaverNewsRepositoryError(RuntimeError):
    """A repository contract failure safe to expose in ingestion output."""


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
    ) -> tuple[UUID, int]:
        query = normalize_search_text(query)
        if not query:
            raise ValueError("query must not be empty")
        requested_params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": sort,
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
                            "storage_policy": "metadata_only",
                            "data_boundary": "news_metadata",
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

    def complete_run(
        self,
        *,
        run_id: UUID,
        source_id: int,
        query: str,
        response: NaverNewsResponse,
    ) -> int:
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
            # TODO: add news_item_query_links so one URL can retain every query match.
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
                on conflict (source_id, original_url) do update set
                    ingestion_run_id = excluded.ingestion_run_id,
                    search_query = excluded.search_query,
                    title = excluded.title,
                    description = excluded.description,
                    portal_url = excluded.portal_url,
                    published_at = excluded.published_at,
                    fetched_at = now(),
                    raw_metadata = excluded.raw_metadata
                """,
                rows,
            )
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
                    len(rows),
                    Jsonb(
                        {
                            "total_search_results": response.total,
                            "rejected_record_count": response.rejected_count,
                            "rejection_reasons": list(response.rejected_reasons),
                            "outcome": response.outcome,
                            "data_boundary": "news_metadata",
                            "is_mock": False,
                        }
                    ),
                    run_id,
                ),
            )
        return len(rows)

    def fail_run(self, run_id: UUID, error: Exception) -> None:
        if isinstance(error, psycopg.Error):
            safe_message = f"{type(error).__name__}: database operation failed"
        else:
            safe_message = f"{type(error).__name__}: {error}"[:1000]
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
                    Jsonb(
                        {
                            "outcome": "failed",
                            "data_boundary": "news_metadata",
                            "is_mock": False,
                        }
                    ),
                    run_id,
                ),
            )
