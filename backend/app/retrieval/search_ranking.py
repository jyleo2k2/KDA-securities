"""Safe Korean query normalization and deterministic knowledge reranking."""

import re
import unicodedata
from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repository import KnowledgeMatch

MAX_QUERY_TOKENS = 12
MAX_TOKEN_CHARS = 40
_TOKEN_PATTERN = re.compile(r"[0-9a-z\uac00-\ud7a3]+")
_ALIASES = (
    ("개인형 퇴직연금제도", "irp"),
    ("개인형퇴직연금제도", "irp"),
    ("개인형 퇴직연금", "irp"),
    ("개인형퇴직연금", "irp"),
    ("확정기여형 퇴직연금", "dc"),
    ("확정기여형퇴직연금", "dc"),
    ("확정기여형", "dc"),
    ("irp형", "irp"),
    ("dc형", "dc"),
)
_PARTICLES = (
    "으로부터",
    "에서부터",
    "이라고",
    "이라는",
    "에서는",
    "에게서",
    "까지는",
    "부터는",
    "인가요",
    "일까요",
    "에서",
    "에게",
    "으로",
    "처럼",
    "보다",
    "까지",
    "부터",
    "하고",
    "이며",
    "에는",
    "라도",
    "와",
    "과",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "도",
    "만",
    "의",
)
_STOP_WORDS = {
    "그리고",
    "그런데",
    "대해서",
    "대한",
    "얼마나",
    "있나요",
    "인가요",
    "일까요",
    "어떻게",
    "무엇",
    "뭐야",
    "알려줘",
    "설명해줘",
    "차이",
    "비교",
}
_DOCUMENT_TYPE_BOOST = {
    "regulation": 1.0,
    "official_guide": 0.8,
    "research": 0.5,
    "product_disclosure": 0.2,
}


def canonicalize_search_text(text: str) -> str:
    """Apply NFKC, aliases, lowercase, and whitespace normalization."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    for source, target in _ALIASES:
        normalized = normalized.replace(source, f" {target} ")
    return re.sub(r"\s+", " ", normalized).strip()


def _strip_particle(token: str) -> str:
    for particle in _PARTICLES:
        if token.endswith(particle) and len(token) >= len(particle) + 2:
            return token[: -len(particle)]
    return token


@lru_cache(maxsize=4096)
def search_tokens(text: str, *, max_tokens: int = MAX_QUERY_TOKENS) -> tuple[str, ...]:
    """Return safe, unique tokens in input order."""
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in _TOKEN_PATTERN.findall(canonicalize_search_text(text)):
        token = _strip_particle(raw_token)
        if (
            len(token) < 2
            or len(token) > MAX_TOKEN_CHARS
            or token in _STOP_WORDS
            or token in seen
        ):
            continue
        tokens.append(token)
        seen.add(token)
        if len(tokens) == max_tokens:
            break
    return tuple(tokens)


def build_prefix_or_tsquery(tokens: tuple[str, ...]) -> str:
    """Build a ``to_tsquery`` value only from already-whitelisted tokens."""
    safe_tokens = [token for token in tokens if _TOKEN_PATTERN.fullmatch(token)]
    return " | ".join(f"{token}:*" for token in safe_tokens[:MAX_QUERY_TOKENS])


def _matches(query_token: str, document_tokens: set[str]) -> bool:
    return any(
        token == query_token or token.startswith(query_token)
        for token in document_tokens
    )


def text_matches_any(query_tokens: tuple[str, ...], text: str) -> bool:
    document_tokens = set(search_tokens(text, max_tokens=10000))
    return any(_matches(token, document_tokens) for token in query_tokens)


def text_matches_all(query_tokens: tuple[str, ...], text: str) -> bool:
    document_tokens = set(search_tokens(text, max_tokens=10000))
    return bool(query_tokens) and all(
        _matches(token, document_tokens) for token in query_tokens
    )


def _score(match: "KnowledgeMatch", query_tokens: tuple[str, ...]) -> float:
    fields = {
        "title": set(search_tokens(match.title, max_tokens=200)),
        "content": set(search_tokens(match.content, max_tokens=2000)),
        "publisher": set(search_tokens(match.publisher or "", max_tokens=50)),
        "authority": set(search_tokens(match.source_authority or "", max_tokens=50)),
    }
    matched_any: set[str] = set()
    exact_content_matches: set[str] = set()
    score = 0.0
    for token in query_tokens:
        if _matches(token, fields["title"]):
            score += 4.0
            matched_any.add(token)
        if _matches(token, fields["content"]):
            score += 1.5
            matched_any.add(token)
        if token in fields["content"]:
            exact_content_matches.add(token)
        if _matches(token, fields["publisher"]):
            score += 2.0
            matched_any.add(token)
        if _matches(token, fields["authority"]):
            score += 1.0
            matched_any.add(token)
    if query_tokens:
        score += 6.0 * len(matched_any) / len(query_tokens)
        if len(query_tokens) >= 3 and len(exact_content_matches) == len(query_tokens):
            # Prefix matching is intentionally broad. Complete exact coverage in
            # the chunk content is stronger evidence than a partial title match.
            score += 6.0
    score += _DOCUMENT_TYPE_BOOST.get(match.document_type or "", 0.0)
    score += max(0.0, min(float(match.text_rank), 1.0))
    return score


def rerank_knowledge_matches(
    matches: list["KnowledgeMatch"],
    query_tokens: tuple[str, ...],
    *,
    limit: int,
) -> list["KnowledgeMatch"]:
    """Rerank candidates without allowing the LLM to influence retrieval."""
    if not matches:
        return matches
    ranked = [(_score(match, query_tokens), match) for match in matches]
    ranked.sort(key=lambda item: (-item[0], item[1].chunk_id))
    bounded_limit = max(1, min(limit, 50))
    return [replace(match, text_rank=score) for score, match in ranked[:bounded_limit]]
