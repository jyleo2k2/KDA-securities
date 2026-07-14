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
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "select * from public.search_knowledge_chunks(%s, %s)",
                (query, limit),
            )
            return [KnowledgeMatch(*row) for row in cursor]

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
