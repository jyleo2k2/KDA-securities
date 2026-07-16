from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

from ..ingestion.embeddings import QueryEmbedder, vector_literal
from ..text_normalization import normalize_search_text
from .search_ranking import (
    build_prefix_or_tsquery,
    rerank_knowledge_matches,
    search_tokens,
)

# RRF(reciprocal rank fusion) 상수 — 관행값 60, 순위 융합의 완만함을 조절한다.
RRF_K = 60

_NEWS_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "irp": ("IRP", "개인형 퇴직연금"),
    "개인형 퇴직연금": ("개인형 퇴직연금", "IRP"),
    "퇴직연금": ("퇴직연금", "IRP", "개인형 퇴직연금", "확정기여형"),
    "연금저축": ("연금저축",),
    "디폴트옵션": ("디폴트옵션", "사전지정운용제도"),
    "사전지정운용제도": ("사전지정운용제도", "디폴트옵션"),
    "tdf": ("TDF", "타깃데이트펀드", "타깃 데이트 펀드"),
    "타깃데이트펀드": ("타깃데이트펀드", "TDF", "타깃 데이트 펀드"),
}


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
                  and kd.document_type in ('official_guide', 'regulation', 'research')
                  and ds.code in (
                      'project_verified_knowledge',
                      'retirement_pension_official_rules'
                  )
                  and ds.is_active
                  and kd.metadata ->> 'data_boundary' = 'verified_knowledge'
                  and kd.metadata ->> 'contains_personal_data' = 'false'
                  and kd.metadata ->> 'is_mock' = 'false'
                  and kc.metadata ->> 'data_boundary' = 'verified_knowledge'
                  and kc.metadata ->> 'contains_personal_data' = 'false'
                  and kc.metadata ->> 'is_mock' = 'false'
                  and kc.metadata ->> 'is_active' is distinct from 'false'
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
                with prepared_query as (
                    select to_tsquery('simple', %(tsquery)s) as ts_query
                ),
                text_candidates as (
                    select
                        kc.id,
                        ts_rank_cd(
                            kc.search_vector,
                            prepared_query.ts_query
                        ) as text_score
                    from public.knowledge_chunks as kc
                    join public.knowledge_documents as kd
                        on kd.id = kc.document_id
                    join public.data_sources as ds on ds.id = kd.source_id
                    cross join prepared_query
                    where kc.search_vector @@ prepared_query.ts_query
                      and kd.license_status = 'permitted'
                      and kd.document_type in (
                          'official_guide', 'regulation', 'research'
                      )
                      and ds.code in (
                          'project_verified_knowledge',
                          'retirement_pension_official_rules'
                      )
                      and ds.is_active
                      and kd.metadata ->> 'data_boundary' = 'verified_knowledge'
                      and kd.metadata ->> 'contains_personal_data' = 'false'
                      and kd.metadata ->> 'is_mock' = 'false'
                      and kc.metadata ->> 'data_boundary' = 'verified_knowledge'
                      and kc.metadata ->> 'contains_personal_data' = 'false'
                      and kc.metadata ->> 'is_mock' = 'false'
                      and kc.metadata ->> 'is_active' is distinct from 'false'
                    order by text_score desc, kc.id
                    limit %(candidate_limit)s
                ),
                text_hits as (
                    select
                        id,
                        row_number() over (
                            order by text_score desc, id
                        ) as rnk
                    from text_candidates
                ),
                vector_candidates as (
                    select
                        kc.id,
                        kc.embedding
                            <=> %(query_vector)s::extensions.vector as distance
                    from public.knowledge_chunks as kc
                    join public.knowledge_documents as kd
                        on kd.id = kc.document_id
                    join public.data_sources as ds on ds.id = kd.source_id
                    where kc.embedding is not null
                      and kd.license_status = 'permitted'
                      and kd.document_type in (
                          'official_guide', 'regulation', 'research'
                      )
                      and ds.code in (
                          'project_verified_knowledge',
                          'retirement_pension_official_rules'
                      )
                      and ds.is_active
                      and kd.metadata ->> 'data_boundary' = 'verified_knowledge'
                      and kd.metadata ->> 'contains_personal_data' = 'false'
                      and kd.metadata ->> 'is_mock' = 'false'
                      and kc.metadata ->> 'data_boundary' = 'verified_knowledge'
                      and kc.metadata ->> 'contains_personal_data' = 'false'
                      and kc.metadata ->> 'is_mock' = 'false'
                      and kc.metadata ->> 'is_active' is distinct from 'false'
                    order by
                        kc.embedding <=> %(query_vector)s::extensions.vector,
                        kc.id
                    limit %(candidate_limit)s
                ),
                vector_hits as (
                    select
                        id,
                        row_number() over (order by distance, id) as rnk
                    from vector_candidates
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
        normalized_query = normalize_search_text(search_query)
        if not normalized_query:
            return []
        bounded_limit = max(1, min(limit, 100))
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
                (normalized_query, bounded_limit),
            )
            exact_matches = [NewsMatch(*row) for row in cursor]
            if exact_matches:
                return exact_matches

            terms = _news_search_terms(normalized_query)
            patterns = [f"%{term}%" for term in terms]
            cursor.execute(
                """
                select
                    id::text, title, description, original_url,
                    portal_url, published_at
                from public.news_items
                where title ilike any(%s::text[])
                   or coalesce(description, '') ilike any(%s::text[])
                order by published_at desc nulls last, fetched_at desc
                limit %s
                """,
                (patterns, patterns, bounded_limit),
            )
            return [NewsMatch(*row) for row in cursor]


def _news_search_terms(search_query: str) -> tuple[str, ...]:
    normalized_query = normalize_search_text(search_query)
    if not normalized_query:
        return ()
    aliases = _NEWS_QUERY_ALIASES.get(normalized_query.casefold(), ())
    return tuple(dict.fromkeys((normalized_query, *aliases)))
