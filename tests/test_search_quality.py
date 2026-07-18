from pathlib import Path
from uuid import uuid4

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.ingestion.knowledge import load_approved_documents
from backend.app.retrieval.quality import (
    QualityCase,
    load_quality_cases,
    measure_search_quality,
)
from backend.app.retrieval.repository import KnowledgeMatch

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "search_quality" / "knowledge_v1.json"


def _match(*, chunk_id: int, content: str, source_url: str) -> KnowledgeMatch:
    return KnowledgeMatch(
        chunk_id=chunk_id,
        document_id=uuid4(),
        title="연금 기초",
        source_url=source_url,
        content=content,
        text_rank=1.0,
    )


class FakeRepository:
    def search_knowledge(self, query: str, *, limit: int = 8):
        if query == "성공":
            return [
                _match(
                    chunk_id=1,
                    content="무관한 내용",
                    source_url="project://docs/other.md",
                ),
                _match(
                    chunk_id=2,
                    content="IRP는 위험자산 한도를 적용합니다.",
                    source_url="project://docs/연금.md#section",
                ),
            ]
        return []


def test_benchmark_has_at_least_ten_unique_korean_cases() -> None:
    cases = load_quality_cases(BENCHMARK)
    approved_urls = {
        document.source_url for document in load_approved_documents()
    }

    assert len(cases) >= 10
    assert len({case.case_id for case in cases}) == len(cases)
    assert len({case.query for case in cases}) == len(cases)
    assert all(case.required_content_terms for case in cases)
    assert all(case.expected_source_url in approved_urls for case in cases)
    assert approved_urls <= {case.expected_source_url for case in cases}
    assert any(case.critical_top1 for case in cases)


def test_quality_requires_source_and_content_terms() -> None:
    cases = (
        QualityCase(
            case_id="hit",
            query="성공",
            expected_source_url="project://docs/연금.md",
            required_content_terms=("IRP", "위험자산"),
            critical_top1=True,
        ),
        QualityCase(
            case_id="miss",
            query="실패",
            expected_source_url="project://docs/연금.md",
            required_content_terms=("IRP",),
        ),
    )

    report = measure_search_quality(FakeRepository(), cases, limit=5)

    assert report.case_count == 2
    assert report.k == 5
    assert report.hit_count == 1
    assert report.hit_at_k == 0.5
    assert report.hit_at_1 == 0
    assert report.mrr_at_k == 0.25
    assert report.failed_case_ids == ("miss",)
    assert report.critical_top1_failed_case_ids == ("hit",)


def test_approved_local_corpus_meets_real_top1_quality_gate() -> None:
    cases = load_quality_cases(BENCHMARK)

    report = measure_search_quality(
        LocalMarkdownKnowledgeRepository(),
        cases,
        limit=5,
    )

    assert report.hit_at_k == 1
    assert report.hit_at_1 == 1
    assert report.mrr_at_k == 1
    assert report.failed_case_ids == ()
    assert report.critical_top1_failed_case_ids == ()


def test_relevance_requires_every_token_in_a_required_phrase() -> None:
    case = QualityCase(
        case_id="phrase",
        query="성공",
        expected_source_url="project://docs/연금.md",
        required_content_terms=("IRP 수수료",),
    )

    report = measure_search_quality(
        FakeRepository(),
        (case,),
        limit=5,
    )

    assert report.hit_count == 0
