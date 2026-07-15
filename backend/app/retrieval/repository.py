from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

from ..ingestion.embeddings import QueryEmbedder, vector_literal

# RRF(reciprocal rank fusion) 상수 — 관행값 60, 순위 융합의 완만함을 조절한다.
RRF_K = 60


@dataclass(frozen=True, slots=True)
class KnowledgeMatch:
    chunk_id: int
    document_id: UUID
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

    def __init__(
        self, database_url: str, *, embedder: QueryEmbedder | None = None
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._embedder = embedder

    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        if self._embedder is not None:
            try:
                query_embedding = self._embedder.embed_query(query)
            except Exception:
                # 임베딩 실패는 검색 실패가 아니다 — 전문검색 골든패스로 폴백.
                query_embedding = None
            if query_embedding is not None:
                return self._search_knowledge_hybrid(
                    query, query_embedding, limit=limit
                )
        return self._search_knowledge_fulltext(query, limit=limit)

    def _search_knowledge_fulltext(
        self, query: str, *, limit: int
    ) -> list[KnowledgeMatch]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "select * from public.search_knowledge_chunks(%s, %s)",
                (query, limit),
            )
            return [KnowledgeMatch(*row) for row in cursor]

    def _search_knowledge_hybrid(
        self, query: str, query_embedding: list[float], *, limit: int
    ) -> list[KnowledgeMatch]:
        """Fuse full-text and vector ranks with RRF; text_rank carries the score."""
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                with text_hits as (
                    select
                        kc.id,
                        row_number() over (
                            order by ts_rank_cd(
                                kc.search_vector,
                                websearch_to_tsquery('simple', %(query)s)
                            ) desc, kc.id
                        ) as rnk
                    from public.knowledge_chunks as kc
                    where %(query)s <> ''
                      and kc.search_vector
                          @@ websearch_to_tsquery('simple', %(query)s)
                    limit 30
                ),
                vector_hits as (
                    select
                        kc.id,
                        row_number() over (
                            order by
                                kc.embedding
                                    <=> %(query_vector)s::extensions.vector,
                                kc.id
                        ) as rnk
                    from public.knowledge_chunks as kc
                    where kc.embedding is not null
                    limit 30
                )
                select
                    kc.id,
                    kd.id,
                    kd.title,
                    kd.source_url,
                    kc.content,
                    (
                        coalesce(1.0 / (%(rrf_k)s + th.rnk), 0)
                        + coalesce(1.0 / (%(rrf_k)s + vh.rnk), 0)
                    )::real as fused_rank
                from text_hits as th
                full outer join vector_hits as vh on th.id = vh.id
                join public.knowledge_chunks as kc
                    on kc.id = coalesce(th.id, vh.id)
                join public.knowledge_documents as kd on kd.id = kc.document_id
                order by fused_rank desc, kc.id
                limit greatest(1, least(%(limit)s, 50))
                """,
                {
                    "query": query,
                    "query_vector": vector_literal(query_embedding),
                    "rrf_k": RRF_K,
                    "limit": limit,
                },
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
