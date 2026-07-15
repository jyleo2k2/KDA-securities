from dataclasses import dataclass
from pathlib import Path

from ..retrieval.repository import KnowledgeMatch
from ..retrieval.search_ranking import (
    rerank_knowledge_matches,
    search_tokens,
    text_matches_any,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_FILES = (
    ROOT / "docs" / "20_리서치" / "연금_기초.md",
    ROOT / "docs" / "30_스펙" / "수익률_가정_모델.md",
)


@dataclass(frozen=True, slots=True)
class _Chunk:
    chunk_id: int
    document_id: str
    title: str
    source_url: str
    content: str


class LocalMarkdownKnowledgeRepository:
    """Small local lexical RAG used before the remote Supabase index is available."""

    def __init__(self, paths: tuple[Path, ...] = DEFAULT_KNOWLEDGE_FILES) -> None:
        self._chunks = self._load_chunks(paths)

    @staticmethod
    def _load_chunks(paths: tuple[Path, ...]) -> tuple[_Chunk, ...]:
        chunks: list[_Chunk] = []
        next_id = 1
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            heading = path.stem
            body: list[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("#"):
                    if body:
                        content = "\n".join(body).strip()
                        if content:
                            chunks.append(
                                _Chunk(
                                    chunk_id=next_id,
                                    document_id=relative,
                                    title=heading,
                                    source_url=f"project://{relative}",
                                    content=content,
                                )
                            )
                            next_id += 1
                    heading = line.lstrip("#").strip()
                    body = []
                else:
                    body.append(line)
            content = "\n".join(body).strip()
            if content:
                chunks.append(
                    _Chunk(
                        chunk_id=next_id,
                        document_id=relative,
                        title=heading,
                        source_url=f"project://{relative}",
                        content=content,
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
                        publisher="연금 코파일럿 팀",
                        source_authority="검증된 프로젝트 문서",
                        document_type="research",
                    )
                )
        return rerank_knowledge_matches(
            matches,
            terms,
            limit=max(1, min(limit, 20)),
        )
