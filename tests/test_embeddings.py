import inspect

from backend.app.ingestion.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    BgeM3Embedder,
    embed_pending_chunks,
    vector_literal,
)
from backend.app.retrieval.repository import KnowledgeMatch, RetrievalRepository


class FailingEmbedder:
    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("model unavailable")


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.5] * EMBEDDING_DIMENSIONS


def test_model_contract_matches_architecture_decision() -> None:
    assert EMBEDDING_MODEL == "BAAI/bge-m3"
    assert EMBEDDING_DIMENSIONS == 1024


def test_vector_literal_is_pgvector_text_format() -> None:
    assert vector_literal([0.5, -1.0, 0.25]) == "[0.5,-1,0.25]"
    assert vector_literal([]) == "[]"


def test_search_falls_back_to_fulltext_when_embedding_fails(monkeypatch) -> None:
    sentinel: list[KnowledgeMatch] = []
    repository = RetrievalRepository("postgresql://x", embedder=FailingEmbedder())
    monkeypatch.setattr(
        repository, "_search_knowledge_fulltext", lambda query, limit: sentinel
    )
    assert repository.search_knowledge("irp") is sentinel


def test_search_uses_hybrid_when_embedder_available(monkeypatch) -> None:
    sentinel: list[KnowledgeMatch] = []
    captured: dict = {}

    def fake_hybrid(query, query_embedding, *, limit):
        captured["dimensions"] = len(query_embedding)
        return sentinel

    repository = RetrievalRepository("postgresql://x", embedder=FakeEmbedder())
    monkeypatch.setattr(repository, "_search_knowledge_hybrid", fake_hybrid)
    assert repository.search_knowledge("irp") is sentinel
    assert captured["dimensions"] == EMBEDDING_DIMENSIONS


def test_search_without_embedder_uses_fulltext(monkeypatch) -> None:
    sentinel: list[KnowledgeMatch] = []
    repository = RetrievalRepository("postgresql://x")
    monkeypatch.setattr(
        repository, "_search_knowledge_fulltext", lambda query, limit: sentinel
    )
    assert repository.search_knowledge("irp") is sentinel


def test_embedding_pipeline_excludes_inactive_and_unverified_chunks() -> None:
    source = inspect.getsource(embed_pending_chunks)

    assert "kc.metadata ->> 'is_active' is distinct from 'false'" in source
    assert "kd.metadata ->> 'data_boundary' = 'verified_knowledge'" in source
    assert "kd.metadata ->> 'contains_personal_data' = 'false'" in source
    assert "kc.metadata ->> 'data_boundary' = 'verified_knowledge'" in source


def test_prewarmed_query_uses_cached_embedding(monkeypatch) -> None:
    embedder = BgeM3Embedder()
    calls: list[list[str]] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [[float(index)] for index, _ in enumerate(texts, start=1)]

    monkeypatch.setattr(embedder, "embed", fake_embed)

    embedder.prewarm_queries(("IRP 위험자산", "연금 뉴스"))

    assert embedder.embed_query("IRP   위험자산") == [1.0]
    assert calls == [["IRP 위험자산", "연금 뉴스"]]
