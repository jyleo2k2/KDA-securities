import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
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
from scripts.ingest_knowledge import main as ingest_main

ROOT = Path(__file__).resolve().parents[1]


class FakeCursor:
    def __init__(
        self,
        run_id: UUID,
        document_id: UUID,
        *,
        existing_document: tuple | None = None,
        existing_chunks: tuple[tuple, ...] = (),
        trailing_count: int = 0,
    ) -> None:
        self.run_id = run_id
        self.document_id = document_id
        self.existing_document = existing_document
        self.existing_chunks = existing_chunks
        self.trailing_count = trailing_count
        self.statements: list[str] = []
        self.execute_params: list[object] = []
        self.chunk_rows: list[tuple] = []
        self._row = None
        self._rows: list[tuple] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None) -> None:
        statement = " ".join(str(query).split())
        self.statements.append(statement)
        self.execute_params.append(params)
        self._row = None
        self._rows = []
        self.rowcount = 0
        if statement.startswith("select id from public.data_sources"):
            self._row = (7,)
        elif (
            "insert into public.ingestion_runs" in statement
            and "returning id" in statement
        ):
            self._row = (self.run_id,)
        elif statement.startswith("select id, document_type"):
            self._rows = (
                [self.existing_document] if self.existing_document is not None else []
            )
        elif statement.startswith("select chunk_index, content, metadata"):
            self._rows = list(self.existing_chunks)
        elif (
            statement.startswith("insert into public.knowledge_documents")
            or statement.startswith("update public.knowledge_documents")
        ):
            self._row = (self.document_id,)
        elif statement.startswith("update public.knowledge_chunks"):
            self.rowcount = self.trailing_count

    def executemany(self, query, params) -> None:
        self.statements.append(" ".join(str(query).split()))
        self.execute_params.append(None)
        self.chunk_rows = list(params)

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


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

    assert len(documents) == 5
    for document in documents:
        assert document.license_status == "permitted"
        assert document.metadata["data_boundary"] == "verified_knowledge"
        assert document.metadata["contains_personal_data"] is False
        assert document.metadata["is_mock"] is False
        assert document.content_hash is not None
        assert len(document.content_hash) == 64
        assert all(len(chunk) <= 800 for chunk in document.chunks)


def test_seed_uses_the_same_canonical_knowledge_url_and_boundary() -> None:
    seed = (ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8")

    assert "project://docs/20_리서치/연금_기초.md#4-2" not in seed
    assert "project://docs/20_리서치/연금_기초.md" in seed
    assert '"data_boundary":"verified_knowledge"' in seed
    assert '"is_active":true' in seed


def test_manifest_rejects_mock_data_path(tmp_path) -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload["documents"][0]["path"] = "data/mock/README.md"
    payload["documents"][0]["source_url"] = "project://data/mock/README.md"
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


def _metadata(document, *, active: bool | None = None) -> dict[str, object]:
    metadata = {
        **document.metadata,
        "contains_personal_data": False,
        "data_boundary": "verified_knowledge",
        "is_mock": False,
    }
    if active is not None:
        metadata["is_active"] = active
    return metadata


def _stored_document(document, document_id: UUID, *, source_url: str | None = None):
    return (
        document_id,
        document.document_type,
        document.title,
        document.publisher,
        source_url or document.source_url,
        document.published_at,
        document.as_of_date,
        document.license_status,
        sha256(document.content.encode("utf-8")).hexdigest(),
        document.content,
        _metadata(document),
    )


def _with_content(document, content: str, chunks: tuple[str, ...]):
    return replace(
        document,
        content=content,
        chunks=chunks,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
    )


def test_repository_tracks_fresh_ingestion_in_one_connection(
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
    assert result.unchanged is False
    assert any("status = 'succeeded'" in item for item in cursor.statements)
    assert not any(item.startswith("delete ") for item in cursor.statements)
    assert len(cursor.chunk_rows) == len(document.chunks)


def test_identical_reingestion_is_a_chunk_noop(monkeypatch) -> None:
    document = load_approved_documents()[0]
    run_id = uuid4()
    document_id = uuid4()
    existing_chunks = tuple(
        (index, chunk, _metadata(document, active=True))
        for index, chunk in enumerate(document.chunks)
    )
    cursor = FakeCursor(
        run_id,
        document_id,
        existing_document=_stored_document(document, document_id),
        existing_chunks=existing_chunks,
    )
    monkeypatch.setattr(
        knowledge_repository.psycopg,
        "connect",
        lambda database_url: FakeConnection(cursor),
    )

    result = KnowledgeWriteRepository("postgresql://test").ingest_document(document)

    assert result.unchanged is True
    assert result.document_id == document_id
    assert cursor.chunk_rows == []
    assert not any(
        statement.startswith("update public.knowledge_documents")
        or statement.startswith("insert into public.knowledge_documents")
        or statement.startswith("update public.knowledge_chunks")
        for statement in cursor.statements
    )
    success_params = next(
        params
        for statement, params in zip(
            cursor.statements, cursor.execute_params, strict=True
        )
        if "status = 'succeeded'" in statement
    )
    assert success_params[0] == "NO_CHANGE"
    assert success_params[2] == 0


def test_changed_reingestion_keeps_ids_resets_changed_embedding_and_deactivates_tail(
    monkeypatch,
) -> None:
    approved = load_approved_documents()[0]
    original = _with_content(approved, "원래 본문", ("같은 첫 청크", "삭제될 청크"))
    changed = _with_content(approved, "바뀐 본문", ("바뀐 첫 청크",))
    run_id = uuid4()
    document_id = uuid4()
    cursor = FakeCursor(
        run_id,
        document_id,
        existing_document=_stored_document(
            original,
            document_id,
            source_url=f"{original.source_url}#4-2",
        ),
        existing_chunks=tuple(
            (index, chunk, _metadata(original, active=True))
            for index, chunk in enumerate(original.chunks)
        ),
        trailing_count=1,
    )
    monkeypatch.setattr(
        knowledge_repository.psycopg,
        "connect",
        lambda database_url: FakeConnection(cursor),
    )

    result = KnowledgeWriteRepository("postgresql://test").ingest_document(changed)

    assert result.unchanged is False
    assert result.document_id == document_id
    assert cursor.chunk_rows[0][0] == document_id
    chunk_statement = next(
        statement
        for statement in cursor.statements
        if statement.startswith("insert into public.knowledge_chunks")
    )
    assert "existing.content is distinct from excluded.content then null" in (
        chunk_statement
    )
    trailing_params = next(
        params
        for statement, params in zip(
            cursor.statements, cursor.execute_params, strict=True
        )
        if statement.startswith("update public.knowledge_chunks")
    )
    assert trailing_params[0].obj == {"is_active": False}
    assert trailing_params[2] == 1
    document_update_params = next(
        params
        for statement, params in zip(
            cursor.statements, cursor.execute_params, strict=True
        )
        if statement.startswith("update public.knowledge_documents")
    )
    assert document_update_params[3] == changed.source_url
    assert document_update_params[-1] == document_id
    assert not any(item.startswith("delete ") for item in cursor.statements)


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


def test_manifest_hash_and_personal_identifier_are_enforced(tmp_path) -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload["documents"][0]["content_sha256"] = "0" * 64
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KnowledgeManifestError, match="content_sha256"):
        load_approved_documents(manifest)

    document = _with_content(
        load_approved_documents()[0],
        "주민번호900101-1234567입니다",
        ("주민번호900101-1234567입니다",),
    )
    with pytest.raises(ValueError, match="personal identifier"):
        KnowledgeWriteRepository("postgresql://test").ingest_document(document)


def test_ingestion_cli_reports_invalid_chunk_size_without_traceback(capsys) -> None:
    assert ingest_main(["--validate-only", "--max-chars", "100"]) == 1
    assert "manifest 검증 실패" in capsys.readouterr().err
