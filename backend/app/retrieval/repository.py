from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

from ..ingestion.embeddings import QueryEmbedder, vector_literal
from .search_ranking import (
    build_prefix_or_tsquery,
    rerank_knowledge_matches,
    search_tokens,
)

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
    publisher: str | None = None
    source_authority: str | None = None
    document_type: str | None = None


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
        tokens = search_tokens(query)
        if not tokens:
            return []
        tsquery = build_prefix_or_tsquery(tokens)
        bounded_limit = max(1, min(limit, 50))
        candidate_limit = min(200, bounded_limit * 4)
        if self._embedder is not None:
            try:
                query_embedding = self._embedder.embed_query(query)
            except Exception:
                # 임베딩 실패는 검색 실패가 아니다 — 전문검색 골든패스로 폴백.
                query_embedding = None
            if query_embedding is not None:
                candidates = self._search_knowledge_hybrid(
                    tsquery, query_embedding, limit=candidate_limit
                )
                return rerank_knowledge_matches(candidates, tokens, limit=bounded_limit)
        candidates = self._search_knowledge_fulltext(tsquery, limit=candidate_limit)
        return rerank_knowledge_matches(candidates, tokens, limit=bounded_limit)

    def _search_knowledge_fulltext(
        self, tsquery: str, *, limit: int
    ) -> list[KnowledgeMatch]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                with prepared_query as (
                    select to_tsquery('simple', %(tsquery)s) as ts_query
                )
                select
                    kc.id,
                    kd.id,
                    kd.title,
                    kd.source_url,
                    kc.content,
                    ts_rank_cd(kc.search_vector, prepared_query.ts_query)::real,
                    kd.publisher,
                    ds.authority,
                    kd.document_type
                from public.knowledge_chunks as kc
                join public.knowledge_documents as kd on kd.id = kc.document_id
                join public.data_sources as ds on ds.id = kd.source_id
                cross join prepared_query
                where kc.search_vector @@ prepared_query.ts_query
                  and kd.license_status = 'permitted'
                  and kd.document_type <> 'news'
                  and ds.is_active
                order by ts_rank_cd(
                    kc.search_vector, prepared_query.ts_query
                ) desc, kc.id
                limit greatest(1, least(%(limit)s, 200))
                """,
                {"tsquery": tsquery, "limit": limit},
            )
            return [KnowledgeMatch(*row) for row in cursor]

    def _search_knowledge_hybrid(
        self, tsquery: str, query_embedding: list[float], *, limit: int
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
                                to_tsquery('simple', %(tsquery)s)
                            ) desc, kc.id
                        ) as rnk
                    from public.knowledge_chunks as kc
                    join public.knowledge_documents as kd
                        on kd.id = kc.document_id
                    join public.data_sources as ds on ds.id = kd.source_id
                    where kc.search_vector
                          @@ to_tsquery('simple', %(tsquery)s)
                      and kd.license_status = 'permitted'
                      and kd.document_type <> 'news'
                      and ds.is_active
                    limit %(candidate_limit)s
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
                    join public.knowledge_documents as kd
                        on kd.id = kc.document_id
                    join public.data_sources as ds on ds.id = kd.source_id
                    where kc.embedding is not null
                      and kd.license_status = 'permitted'
                      and kd.document_type <> 'news'
                      and ds.is_active
                    limit %(candidate_limit)s
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
                    )::real as fused_rank,
                    kd.publisher,
                    ds.authority,
                    kd.document_type
                from text_hits as th
                full outer join vector_hits as vh on th.id = vh.id
                join public.knowledge_chunks as kc
                    on kc.id = coalesce(th.id, vh.id)
                join public.knowledge_documents as kd on kd.id = kc.document_id
                join public.data_sources as ds on ds.id = kd.source_id
                order by fused_rank desc, kc.id
                limit greatest(1, least(%(candidate_limit)s, 200))
                """,
                {
                    "tsquery": tsquery,
                    "query_vector": vector_literal(query_embedding),
                    "rrf_k": RRF_K,
                    "candidate_limit": limit,
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
