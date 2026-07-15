from dataclasses import dataclass
from datetime import datetime

import psycopg


@dataclass(frozen=True, slots=True)
class KnowledgeMatch:
    chunk_id: int
    document_id: str
    title: str
    source_url: str
    content: str
    text_rank: float
    document_type: str | None = None
    publisher: str | None = None
    authority: str | None = None
    retrieval_score: float | None = None


@dataclass(frozen=True, slots=True)
class NewsMatch:
    item_id: str
    title: str
    description: str | None
    original_url: str
    portal_url: str | None
    published_at: datetime | None


class RetrievalRepository:
    """Keep verified-knowledge search separate from latest-news lookup."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        from .search_ranking import (
            normalize_korean_search_query,
            rerank_knowledge_matches,
        )

        normalized_query = normalize_korean_search_query(query)
        if not normalized_query:
            return []
        requested_limit = max(1, min(limit, 50))
        candidate_limit = min(50, max(requested_limit * 4, requested_limit))
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    found.chunk_id, found.document_id, found.title,
                    found.source_url, found.content, found.text_rank,
                    document.document_type, document.publisher, source.authority
                from public.search_knowledge_chunks(%s, %s) as found
                join public.knowledge_documents as document
                  on document.id = found.document_id
                join public.data_sources as source
                  on source.id = document.source_id
                order by found.text_rank desc, found.chunk_id
                """,
                (normalized_query, candidate_limit),
            )
            matches = [
                KnowledgeMatch(
                    chunk_id=int(row[0]),
                    document_id=str(row[1]),
                    title=str(row[2]),
                    source_url=str(row[3]),
                    content=str(row[4]),
                    text_rank=float(row[5]),
                    document_type=str(row[6]),
                    publisher=str(row[7]),
                    authority=str(row[8]),
                )
                for row in cursor
            ]
        return rerank_knowledge_matches(
            matches, normalized_query, limit=requested_limit
        )

    def latest_news(self, search_query: str, *, limit: int = 10) -> list[NewsMatch]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    id::text, title, description, original_url,
                    portal_url, published_at
                from public.news_items
                where search_query = %s
                order by published_at desc nulls last, fetched_at desc
                limit %s
                """,
                (search_query, max(1, min(limit, 100))),
            )
            return [NewsMatch(*row) for row in cursor]
