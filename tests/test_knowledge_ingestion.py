import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from backend.app.ingestion.knowledge import (
    DEFAULT_MANIFEST,
    KnowledgeManifestError,
    chunk_markdown,
    load_approved_documents,
)
from backend.app.retrieval import knowledge_repository
from backend.app.retrieval.knowledge_repository import KnowledgeWriteRepository


class FakeCursor:
    def __init__(self, run_id: UUID, document_id: UUID) -> None:
        self.run_id = run_id
        self.document_id = document_id
        self.statements: list[str] = []
        self.chunk_rows: list[tuple] = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None) -> None:
        statement = " ".join(str(query).split())
        self.statements.append(statement)
        if statement.startswith("select id from public.data_sources"):
            self._row = (7,)
        elif (
            "insert into public.ingestion_runs" in statement
            and "returning id" in statement
        ):
            self._row = (self.run_id,)
        elif "insert into public.knowledge_documents" in statement:
            self._row = (self.document_id,)
        else:
            self._row = None

    def executemany(self, query, params) -> None:
        self.statements.append(" ".join(str(query).split()))
        self.chunk_rows = list(params)

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_chunk_markdown_keeps_headings_and_max_size() -> None:
    content = "# 첫 제목\n\n" + ("첫 문단입니다. " * 80) + "\n\n## 둘째\n\n내용"

    chunks = chunk_markdown(content, max_chars=500)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert chunks[0].startswith("첫 제목\n")
    assert any("둘째\n내용" in chunk for chunk in chunks)


def test_approved_manifest_loads_only_verified_non_mock_documents() -> None:
    documents = load_approved_documents()

    assert len(documents) == 1
    document = documents[0]
    assert document.license_status == "permitted"
    assert document.metadata["data_boundary"] == "verified_knowledge"
    assert document.metadata["contains_personal_data"] is False
    assert document.metadata["is_mock"] is False
    assert document.content_hash is not None
    assert len(document.content_hash) == 64
    assert all(len(chunk) <= 1800 for chunk in document.chunks)


def test_manifest_rejects_mock_data_path(tmp_path) -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload["documents"][0]["path"] = "data/mock/README.md"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KnowledgeManifestError, match="outside approved"):
        load_approved_documents(manifest)


def test_manifest_rejects_news_boundary(tmp_path) -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload["documents"][0]["document_type"] = "news"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KnowledgeManifestError, match="document_type"):
        load_approved_documents(manifest)


def test_repository_tracks_run_and_replaces_document_in_one_connection(
    monkeypatch,
) -> None:
    document = load_approved_documents()[0]
    run_id = uuid4()
    document_id = uuid4()
    cursor = FakeCursor(run_id, document_id)
    connection = FakeConnection(cursor)
    connect_count = 0

    def fake_connect(database_url: str) -> FakeConnection:
        nonlocal connect_count
        connect_count += 1
        return connection

    monkeypatch.setattr(knowledge_repository.psycopg, "connect", fake_connect)

    result = KnowledgeWriteRepository("postgresql://test").ingest_document(document)

    assert connect_count == 1
    assert result.run_id == run_id
    assert result.document_id == document_id
    assert result.chunk_count == len(document.chunks)
    assert any("status = 'succeeded'" in item for item in cursor.statements)
    assert any(
        item.startswith("delete from public.knowledge_chunks")
        for item in cursor.statements
    )
    assert len(cursor.chunk_rows) == len(document.chunks)


def test_repository_rejects_mock_metadata_before_database_call(monkeypatch) -> None:
    document = replace(
        load_approved_documents()[0],
        metadata={
            "contains_personal_data": False,
            "data_boundary": "verified_knowledge",
            "is_mock": True,
        },
    )
    monkeypatch.setattr(
        knowledge_repository.psycopg,
        "connect",
        lambda database_url: pytest.fail("database must not be called"),
    )

    with pytest.raises(ValueError, match="mock data"):
        KnowledgeWriteRepository("postgresql://test").ingest_document(document)
