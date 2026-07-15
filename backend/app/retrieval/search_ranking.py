import re
import unicodedata
from dataclasses import dataclass, replace

from .repository import KnowledgeMatch

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_SPACE = re.compile(r"\s+")
_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"개인형\s*퇴직\s*연금(?:\s*제도)?", re.I), "IRP"),
    (re.compile(r"확정\s*기여형(?:\s*퇴직\s*연금)?", re.I), "DC"),
    (re.compile(r"\bDC\s*형\b", re.I), "DC"),
    (re.compile(r"\bIRP\s*계좌\b", re.I), "IRP"),
    (re.compile(r"연금\s*저축", re.I), "연금저축"),
    (re.compile(r"위험\s*자산", re.I), "위험자산"),
    (re.compile(r"원리금\s*보장", re.I), "원리금보장"),
    (re.compile(r"디폴트\s*옵션", re.I), "디폴트옵션"),
)
_STOPWORDS = {
    "관련",
    "관해서",
    "대해",
    "대한",
    "무엇",
    "무엇인가요",
    "뭐야",
    "뭔가요",
    "알려줘",
    "알려주세요",
    "알려",
    "설명해줘",
    "설명해주세요",
    "설명",
    "궁금해",
    "궁금합니다",
    "질문",
}
_PARTICLES = (
    "에서는",
    "으로는",
    "에게서",
    "에서",
    "으로",
    "까지",
    "부터",
    "처럼",
    "보다",
    "에게",
    "한테",
    "께서",
    "이랑",
    "하고",
    "라도",
    "이나",
    "거나",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "로",
    "와",
    "과",
    "도",
    "만",
)
_DOCUMENT_TYPE_WEIGHTS = {
    "law": 0.35,
    "regulation": 0.35,
    "official_guide": 0.30,
    "official_document": 0.30,
    "research": 0.15,
    "curated": 0.10,
}


def _strip_particle(token: str) -> str:
    for particle in _PARTICLES:
        if token.endswith(particle) and len(token) - len(particle) >= 2:
            return token[: -len(particle)]
    return token


def normalize_korean_search_query(query: str, *, max_terms: int = 12) -> str:
    """Reduce a natural Korean question to stable PostgreSQL FTS terms."""
    normalized = unicodedata.normalize("NFKC", query).strip()
    for pattern, replacement in _ALIASES:
        normalized = pattern.sub(replacement, normalized)
    terms: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN.findall(normalized):
        term = _strip_particle(raw)
        if term.casefold() in _STOPWORDS or len(term) < 2:
            continue
        folded = term.upper() if term.casefold() in {"irp", "dc"} else term
        if folded.casefold() not in seen:
            terms.append(folded)
            seen.add(folded.casefold())
        if len(terms) >= max_terms:
            break
    return _SPACE.sub(" ", " ".join(terms)).strip()


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(text)}


@dataclass(frozen=True, slots=True)
class RankingWeights:
    title: float = 1.50
    document_type: float = 1.00
    publisher: float = 0.60
    authority: float = 0.45


_DEFAULT_RANKING_WEIGHTS = RankingWeights()


def _overlap_ratio(query_terms: set[str], text: str | None) -> float:
    if not query_terms or not text:
        return 0.0
    return len(query_terms & _tokens(text)) / len(query_terms)


def retrieval_score(
    match: KnowledgeMatch,
    normalized_query: str,
    *,
    weights: RankingWeights = _DEFAULT_RANKING_WEIGHTS,
) -> float:
    query_terms = _tokens(normalized_query)
    document_type_weight = _DOCUMENT_TYPE_WEIGHTS.get(
        (match.document_type or "").casefold(), 0.0
    )
    return (
        match.text_rank
        + weights.title * _overlap_ratio(query_terms, match.title)
        + weights.publisher * _overlap_ratio(query_terms, match.publisher)
        + weights.authority * _overlap_ratio(query_terms, match.authority)
        + weights.document_type * document_type_weight
    )


def rerank_knowledge_matches(
    matches: list[KnowledgeMatch],
    normalized_query: str,
    *,
    limit: int,
    weights: RankingWeights = _DEFAULT_RANKING_WEIGHTS,
) -> list[KnowledgeMatch]:
    scored = [
        replace(
            match,
            retrieval_score=retrieval_score(
                match, normalized_query, weights=weights
            ),
        )
        for match in matches
    ]
    scored.sort(
        key=lambda match: (
            -(match.retrieval_score or 0.0),
            -match.text_rank,
            match.chunk_id,
        )
    )
    return scored[: max(1, min(limit, 50))]
