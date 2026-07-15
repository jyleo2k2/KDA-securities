from datetime import date
from uuid import UUID, uuid4

import pytest

from backend.app.ingestion.knowledge import (
    chunk_markdown,
    ingest_knowledge_document,
)
from backend.app.retrieval.knowledge_repository import (
    KnowledgeDocumentInput,
    KnowledgeRunHandle,
    KnowledgeSourceInput,
)


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.handle = KnowledgeRunHandle(uuid4(), 7)
        self.completed: KnowledgeDocumentInput | None = None
        self.failed: tuple[object, Exception] | None = None

    def start_run(self, source: KnowledgeSourceInput) -> KnowledgeRunHandle:
        assert source.source_type in {"official_document", "curated"}
        return self.handle

    def complete_document(
        self, handle: KnowledgeRunHandle, document: KnowledgeDocumentInput
    ) -> UUID:
        assert handle == self.handle
        self.completed = document
        return uuid4()

    def fail_run(self, run_id: object, error: Exception) -> None:
        self.failed = (run_id, error)


def _source() -> KnowledgeSourceInput:
    return KnowledgeSourceInput(
        code="fss_verified_guide",
        name="금융감독원 검증 문서",
        source_type="official_document",
        authority="금융감독원",
        base_url="https://www.fss.or.kr/",
    )


def _document(
    content: str,
    source_url: str = "https://www.fss.or.kr/guide",
) -> KnowledgeDocumentInput:
    return KnowledgeDocumentInput(
        source_code="fss_verified_guide",
        document_type="official_guide",
        title="퇴직연금 공식 안내",
        publisher="금융감독원",
        source_url=source_url,
        license_status="permitted",
        content=content,
        chunks=(),
        as_of_date=date(2026, 7, 15),
    )


def test_markdown_chunking_preserves_heading_context() -> None:
    chunks = chunk_markdown(
        "# 계좌별 원칙\n\nDC형 안내입니다.\n\n## 예외\n\n적격 TDF 안내입니다.",
        max_chars=200,
    )

    assert chunks == (
        "제목: 계좌별 원칙\n\nDC형 안내입니다.",
        "제목: 예외\n\n적격 TDF 안내입니다.",
    )


def test_official_document_is_chunked_and_completed() -> None:
    repository = FakeKnowledgeRepository()

    ingest_knowledge_document(
        repository,
        source=_source(),
        document=_document("# 원칙\n\n공식 지식 내용입니다."),
    )

    assert repository.completed is not None
    assert repository.completed.chunks == ("제목: 원칙\n\n공식 지식 내용입니다.",)
    assert repository.failed is None


@pytest.mark.parametrize(
    ("content", "source_url"),
    [
        ("사용자 계좌번호를 포함한 문서", "https://example.test/guide"),
        ("일반 내용", "user://account/current"),
        ("일반 내용", "data/mock/scenario-a.json"),
    ],
)
def test_user_or_mock_account_data_is_rejected_and_run_is_failed(
    content: str, source_url: str
) -> None:
    repository = FakeKnowledgeRepository()

    with pytest.raises(ValueError):
        ingest_knowledge_document(
            repository,
            source=_source(),
            document=_document(content, source_url),
        )

    assert repository.completed is None
    assert repository.failed is not None


def test_document_requires_published_or_as_of_date() -> None:
    repository = FakeKnowledgeRepository()
    document = _document("공식 내용")
    document = KnowledgeDocumentInput(
        source_code=document.source_code,
        document_type=document.document_type,
        title=document.title,
        publisher=document.publisher,
        source_url=document.source_url,
        license_status=document.license_status,
        content=document.content,
        chunks=(),
    )

    with pytest.raises(ValueError, match="published_at or as_of_date"):
        ingest_knowledge_document(repository, source=_source(), document=document)

    assert repository.failed is not None
