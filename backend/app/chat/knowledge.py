from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from ..ingestion.knowledge import DEFAULT_MANIFEST, load_approved_documents
from ..retrieval.repository import KnowledgeMatch, KnowledgeSearch
from ..retrieval.search_ranking import (
    rerank_knowledge_matches,
    search_tokens,
    text_matches_any,
)


@dataclass(frozen=True, slots=True)
class _Chunk:
    chunk_id: int
    document_id: UUID
    title: str
    source_url: str
    content: str
    publisher: str
    document_type: str
    as_of_date: date | None


class FallbackKnowledgeRepository:
    """Use approved local knowledge only for DB errors or an empty DB corpus."""

    def __init__(
        self,
        primary: KnowledgeSearch,
        fallback: KnowledgeSearch,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        try:
            matches = self._primary.search_knowledge(query, limit=limit)
        except psycopg.Error:
            return self._fallback.search_knowledge(query, limit=limit)
        return matches or self._fallback.search_knowledge(query, limit=limit)


class LocalMarkdownKnowledgeRepository:
    """Manifest-backed lexical RAG for DB-absent and DB-unavailable operation."""

    def __init__(self, manifest_path: Path = DEFAULT_MANIFEST) -> None:
        self._chunks = self._load_chunks(manifest_path)

    @staticmethod
    def _load_chunks(manifest_path: Path) -> tuple[_Chunk, ...]:
        chunks: list[_Chunk] = []
        next_id = 1
        for document in load_approved_documents(manifest_path):
            document_id = uuid5(NAMESPACE_URL, document.source_url)
            for content in document.chunks:
                chunks.append(
                    _Chunk(
                        chunk_id=next_id,
                        document_id=document_id,
                        title=document.title,
                        source_url=document.source_url,
                        content=content,
                        publisher=document.publisher,
                        document_type=document.document_type,
                        as_of_date=document.as_of_date,
                    )
                )
                next_id += 1
        return tuple(chunks)

    def search_knowledge(self, query: str, *, limit: int = 8) -> list[KnowledgeMatch]:
        terms = search_tokens(query)
        if not terms:
            return []
        matches: list[KnowledgeMatch] = []
        for chunk in self._chunks:
            if text_matches_any(terms, f"{chunk.title}\n{chunk.content}"):
                matches.append(
                    KnowledgeMatch(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        title=chunk.title,
                        source_url=chunk.source_url,
                        content=chunk.content,
                        text_rank=0.0,
                        publisher=chunk.publisher,
                        source_authority=chunk.publisher,
                        document_type=chunk.document_type,
                        as_of_date=chunk.as_of_date,
                    )
                )
        return rerank_knowledge_matches(
            matches,
            terms,
            limit=max(1, min(limit, 20)),
        )
