import re
from dataclasses import dataclass
from pathlib import Path

from ..retrieval.repository import KnowledgeMatch

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_FILES = (
    ROOT / "docs" / "20_리서치" / "연금_기초.md",
    ROOT / "docs" / "30_스펙" / "수익률_가정_모델.md",
)
STOP_WORDS = {
    "그리고",
    "그런데",
    "어떻게",
    "알려줘",
    "설명해줘",
    "차이가",
    "차이",
}
PARTICLES = (
    "에서는",
    "에는",
    "에서",
    "으로",
    "와",
    "과",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "도",
)


@dataclass(frozen=True, slots=True)
class _Chunk:
    chunk_id: int
    document_id: str
    title: str
    source_url: str
    content: str


def _terms(text: str) -> set[str]:
    normalized = text.lower().replace("dc형", "dc").replace("irp형", "irp")
    raw_terms = re.findall(r"[가-힣a-z0-9]{2,}", normalized)
    terms: set[str] = set()
    for raw_term in raw_terms:
        term = raw_term
        for particle in PARTICLES:
            if term.endswith(particle) and len(term) > len(particle) + 1:
                term = term[: -len(particle)]
                break
        if term not in STOP_WORDS:
            terms.add(term)
    return terms


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
        terms = _terms(query)
        scored: list[tuple[float, _Chunk]] = []
        for chunk in self._chunks:
            title = chunk.title.lower()
            content = chunk.content.lower()
            score = sum(4 for term in terms if term in title)
            score += sum(1 for term in terms if term in content)
            if score:
                scored.append((float(score), chunk))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [
            KnowledgeMatch(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                source_url=chunk.source_url,
                content=chunk.content,
                text_rank=score,
            )
            for score, chunk in scored[: max(1, min(limit, 20))]
        ]
