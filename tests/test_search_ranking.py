import inspect
from uuid import uuid4

import psycopg
import pytest

from backend.app.chat.knowledge import (
    FallbackKnowledgeRepository,
    LocalMarkdownKnowledgeRepository,
)
from backend.app.retrieval.repository import (
    KnowledgeMatch,
    RetrievalRepository,
    _news_search_terms,
)
from backend.app.retrieval.search_ranking import (
    build_prefix_or_tsquery,
    rerank_knowledge_matches,
    search_tokens,
)


def _match(
    *,
    chunk_id: int,
    title: str,
    content: str,
    text_rank: float = 0.1,
) -> KnowledgeMatch:
    return KnowledgeMatch(
        chunk_id=chunk_id,
        document_id=uuid4(),
        title=title,
        source_url="project://docs/20_리서치/연금_기초.md",
        content=content,
        text_rank=text_rank,
        publisher="연금 코파일럿 팀",
        source_authority="금융감독원",
        document_type="research",
    )


def test_korean_query_normalization_handles_aliases_and_particles() -> None:
    assert search_tokens("ＩＲＰ는 위험자산을 알려줘") == ("irp", "위험자산")
    assert search_tokens("개인형 퇴직연금은 어떻게 운용해?") == ("irp", "운용해")
    assert search_tokens("확정기여형 위험자산") == ("dc", "위험자산")


def test_prefix_query_is_built_only_from_safe_tokens() -> None:
    tokens = search_tokens("IRP:* | !위험자산 & DROP TABLE")

    assert tokens == ("irp", "위험자산", "drop", "table")
    assert build_prefix_or_tsquery(tokens) == ("irp:* | 위험자산:* | drop:* | table:*")
    assert search_tokens("가" * 100) == ()


def test_reranker_prioritizes_title_and_full_query_coverage() -> None:
    title_match = _match(
        chunk_id=2,
        title="IRP 위험자산 한도",
        content="공식 규칙을 설명합니다.",
    )
    content_match = _match(
        chunk_id=1,
        title="연금 일반 안내",
        content="IRP 계좌를 설명하지만 위험자산 내용은 없습니다.",
        text_rank=0.9,
    )

    results = rerank_knowledge_matches(
        [content_match, title_match],
        search_tokens("IRP 위험자산"),
        limit=2,
    )

    assert results[0].chunk_id == title_match.chunk_id
    assert results[0].text_rank > results[1].text_rank


def test_repository_expands_candidates_and_uses_prefix_or_query(monkeypatch) -> None:
    repository = RetrievalRepository("postgresql://test")
    captured: dict[str, object] = {}
    candidates = [
        _match(
            chunk_id=1,
            title="IRP 위험자산 한도",
            content="IRP는 일반 위험자산을 제한합니다.",
        )
    ]

    def fake_fulltext(tsquery: str, *, limit: int) -> list[KnowledgeMatch]:
        captured["tsquery"] = tsquery
        captured["limit"] = limit
        return candidates

    monkeypatch.setattr(repository, "_search_knowledge_fulltext", fake_fulltext)

    results = repository.search_knowledge("IRP는 위험자산을", limit=2)

    assert captured == {"tsquery": "irp:* | 위험자산:*", "limit": 8}
    assert results[0].chunk_id == 1


def test_repository_skips_database_for_query_without_safe_tokens(monkeypatch) -> None:
    repository = RetrievalRepository("postgresql://test")
    called = False

    def fake_fulltext(tsquery: str, *, limit: int) -> list[KnowledgeMatch]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(repository, "_search_knowledge_fulltext", fake_fulltext)

    assert repository.search_knowledge("!!!") == []
    assert called is False


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("IRP", ("IRP", "개인형 퇴직연금")),
        ("개인형 퇴직연금", ("개인형 퇴직연금", "IRP")),
        ("디폴트옵션", ("디폴트옵션", "사전지정운용제도")),
        ("일반 연금", ("일반 연금",)),
    ),
)
def test_news_fallback_terms_are_limited_to_topic_aliases(
    query: str, expected: tuple[str, ...]
) -> None:
    assert _news_search_terms(query) == expected


class _StaticKnowledge:
    def __init__(self, matches: list[KnowledgeMatch]) -> None:
        self.matches = matches

    def search_knowledge(self, query: str, *, limit: int = 8):
        return self.matches[:limit]


class _FailingKnowledge:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def search_knowledge(self, query: str, *, limit: int = 8):
        raise self.error


def test_local_fallback_uses_only_the_approved_manifest() -> None:
    repository = LocalMarkdownKnowledgeRepository()

    results = repository.search_knowledge("적격 TDF 예외", limit=3)

    assert results
    assert results[0].source_url == "project://docs/20_리서치/연금_기초.md"
    assert all("30_스펙" not in result.source_url for result in results)


def test_fallback_uses_local_for_empty_results_and_database_errors() -> None:
    fallback_match = _match(
        chunk_id=9,
        title="IRP 위험자산 한도",
        content="검증 근거",
    )
    fallback = _StaticKnowledge([fallback_match])

    empty_result = FallbackKnowledgeRepository(_StaticKnowledge([]), fallback)
    database_error = FallbackKnowledgeRepository(
        _FailingKnowledge(psycopg.OperationalError("database unavailable")),
        fallback,
    )

    assert empty_result.search_knowledge("IRP") == [fallback_match]
    assert database_error.search_knowledge("IRP") == [fallback_match]


def test_fallback_does_not_hide_non_database_programming_errors() -> None:
    repository = FallbackKnowledgeRepository(
        _FailingKnowledge(RuntimeError("bug")),
        _StaticKnowledge([]),
    )

    with pytest.raises(RuntimeError, match="bug"):
        repository.search_knowledge("IRP")


def test_hybrid_sql_orders_candidates_before_limiting_and_filters_boundaries() -> None:
    source = inspect.getsource(RetrievalRepository._search_knowledge_hybrid)

    assert "order by text_score desc, kc.id" in source
    assert "order by\n                        kc.embedding <=>" in source
    assert "kd.metadata ->> 'data_boundary' = 'verified_knowledge'" in source
    assert "kc.metadata ->> 'data_boundary' = 'verified_knowledge'" in source
    assert "kc.metadata ->> 'is_active' is distinct from 'false'" in source
