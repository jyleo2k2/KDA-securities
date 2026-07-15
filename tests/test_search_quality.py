from backend.app.retrieval.quality import (
    KnowledgeQualityCase,
    evaluate_knowledge_search,
)
from backend.app.retrieval.repository import KnowledgeMatch, RetrievalRepository
from backend.app.retrieval.search_ranking import (
    normalize_korean_search_query,
    rerank_knowledge_matches,
)


def _match(
    *,
    chunk_id: int,
    source_url: str,
    title: str,
    text_rank: float,
    document_type: str = "research",
    publisher: str = "연금 코파일럿 팀",
    authority: str = "연금 코파일럿 팀",
) -> KnowledgeMatch:
    return KnowledgeMatch(
        chunk_id=chunk_id,
        document_id=f"document-{chunk_id}",
        title=title,
        source_url=source_url,
        content="검색 근거",
        text_rank=text_rank,
        document_type=document_type,
        publisher=publisher,
        authority=authority,
    )


def test_normalize_korean_natural_language_query() -> None:
    assert (
        normalize_korean_search_query(
            "개인형 퇴직연금의 위험 자산 한도를 알려주세요"
        )
        == "IRP 위험자산 한도"
    )
    assert normalize_korean_search_query("DC형 원리금 보장 설명해줘") == (
        "DC 원리금보장"
    )


def test_reranking_prioritizes_title_document_type_and_publisher() -> None:
    content_only = _match(
        chunk_id=1,
        source_url="https://example.test/research",
        title="일반 연구",
        text_rank=0.8,
    )
    official_title = _match(
        chunk_id=2,
        source_url="https://fss.example/irp",
        title="금융감독원 IRP 위험자산 안내",
        text_rank=0.5,
        document_type="official_guide",
        publisher="금융감독원",
        authority="금융감독원",
    )

    ranked = rerank_knowledge_matches(
        [content_only, official_title],
        "금융감독원 IRP 위험자산",
        limit=2,
    )

    assert [match.chunk_id for match in ranked] == [2, 1]
    assert ranked[0].retrieval_score is not None
    assert ranked[0].retrieval_score > ranked[1].retrieval_score


class _QualityRepository:
    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]:
        del limit
        if query == "첫 질문":
            return [
                _match(
                    chunk_id=1,
                    source_url="source://irrelevant",
                    title="무관",
                    text_rank=1,
                ),
                _match(
                    chunk_id=2,
                    source_url="source://relevant",
                    title="관련",
                    text_rank=0.5,
                ),
            ]
        return []


def test_quality_report_measures_hit_rate_mrr_and_recall() -> None:
    report = evaluate_knowledge_search(
        _QualityRepository(),
        (
            KnowledgeQualityCase("첫 질문", ("source://relevant",)),
            KnowledgeQualityCase("누락 질문", ("source://missing",)),
        ),
        top_k=3,
    )

    assert report.hit_rate == 0.5
    assert report.mean_reciprocal_rank == 0.25
    assert report.mean_recall == 0.5
    assert report.missed_queries == ("누락 질문",)


def test_database_search_normalizes_overfetches_and_reranks(monkeypatch) -> None:
    rows = [
        (
            1,
            "document-1",
            "일반 연구",
            "https://example.test/research",
            "IRP 위험자산 한도",
            0.8,
            "research",
            "연구팀",
            "연구팀",
        ),
        (
            2,
            "document-2",
            "금융감독원 IRP 위험자산 안내",
            "https://fss.example/irp",
            "IRP 위험자산 한도",
            0.5,
            "official_guide",
            "금융감독원",
            "금융감독원",
        ),
    ]

    class Cursor:
        params: tuple[object, ...] | None = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement, params):
            assert "search_knowledge_chunks" in statement
            self.params = params

        def __iter__(self):
            return iter(rows)

    cursor = Cursor()

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return cursor

    monkeypatch.setattr(
        "backend.app.retrieval.repository.psycopg.connect",
        lambda _database_url: Connection(),
    )

    results = RetrievalRepository("postgresql://example/db").search_knowledge(
        "개인형 퇴직연금의 위험 자산 한도를 알려주세요",
        limit=1,
    )

    assert cursor.params == ("IRP 위험자산 한도", 4)
    assert [match.chunk_id for match in results] == [2]
