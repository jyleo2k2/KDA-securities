"""BGE-M3 embedding pipeline for knowledge chunks (아키텍처.md §10 확정 모델).

sentence-transformers는 선택 의존성 그룹(embeddings)이라 미설치 환경에서는
임베딩 없이 전문검색만 동작한다(골든패스 유지). 설치·적재:

    uv sync --group embeddings
    uv run --group embeddings python scripts/embed_knowledge_chunks.py
"""

from functools import lru_cache
from typing import Protocol

import psycopg

EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIMENSIONS = 1024


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class BgeM3Embedder:
    """Lazy-loading dense embedder; the model is fetched on first use."""

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            # 지연 import: embeddings 그룹 미설치 환경에서 모듈 import는 성공해야 한다.
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_query_embedder() -> BgeM3Embedder | None:
    """Return a shared embedder when the optional group is installed, else None.

    모델이 크므로(2GB+) 프로세스당 1회만 로드되도록 캐시한다.
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return None
    return BgeM3Embedder()


def vector_literal(values: list[float]) -> str:
    """Serialize a vector as the pgvector text literal ``[v1,v2,...]``."""
    return "[" + ",".join(format(value, "g") for value in values) + "]"


def embed_pending_chunks(
    database_url: str,
    embedder: BgeM3Embedder,
    *,
    batch_size: int = 16,
) -> int:
    """Embed chunks with no embedding or with a stale model; return the count.

    재임베딩 정책: embedding_model이 현재 모델과 다르면 다시 계산한다.
    """
    if not database_url:
        raise ValueError("database_url is required")
    embedded = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select kc.id, kc.content
                from public.knowledge_chunks as kc
                join public.knowledge_documents as kd on kd.id = kc.document_id
                join public.data_sources as ds on ds.id = kd.source_id
                where (
                    kc.embedding is null
                    or kc.embedding_model is distinct from %s
                )
                  and kc.metadata ->> 'is_active' is distinct from 'false'
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
                order by kc.id
                """,
                (EMBEDDING_MODEL,),
            )
            rows = cursor.fetchall()
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            vectors = embedder.embed([content for _, content in batch])
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    update public.knowledge_chunks
                    set embedding = %s::extensions.vector,
                        embedding_model = %s,
                        embedding_dimensions = %s
                    where id = %s
                    """,
                    [
                        (
                            vector_literal(vector),
                            EMBEDDING_MODEL,
                            EMBEDDING_DIMENSIONS,
                            chunk_id,
                        )
                        for (chunk_id, _), vector in zip(batch, vectors, strict=True)
                    ],
                )
            embedded += len(batch)
    return embedded
