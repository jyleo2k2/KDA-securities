from backend.app.ingestion.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
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
