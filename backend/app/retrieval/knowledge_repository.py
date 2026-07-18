from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .knowledge_policy import (
    ALLOWED_KNOWLEDGE_DOCUMENT_TYPES,
    ALLOWED_KNOWLEDGE_SOURCE_CODES,
    canonicalize_source_url,
    contains_sensitive_personal_data,
)


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentInput:
    source_code: str
    document_type: str
    title: str
    publisher: str
    source_url: str
    license_status: str
    content: str
    chunks: tuple[str, ...]
    published_at: datetime | None = None
    as_of_date: date | None = None
    content_hash: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeIngestionResult:
    run_id: UUID
    document_id: UUID
    chunk_count: int
    unchanged: bool


@dataclass(frozen=True, slots=True)
class _StoredDocument:
    document_id: UUID
    document_type: str
    title: str
    publisher: str
    source_url: str
    published_at: datetime | None
    as_of_date: date | None
    license_status: str
    content_hash: str | None
    content: str | None
    metadata: dict[str, object]
    active_chunks: tuple[tuple[int, str, dict[str, object]], ...]


class KnowledgeWriteRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def ingest_document(
        self, document: KnowledgeDocumentInput
    ) -> KnowledgeIngestionResult:
        self._validate_document(document)
        content_hash = sha256(document.content.encode("utf-8")).hexdigest()
        source_id: int | None = None
        try:
            with (
                psycopg.connect(self._database_url) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "select id from public.data_sources where code = %s and is_active",
                    (document.source_code,),
                )
                source_row = cursor.fetchone()
                if source_row is None:
                    raise RuntimeError("knowledge data source is missing")
                source_id = int(source_row[0])
                cursor.execute(
                    """
                    insert into public.ingestion_runs (
                        source_id, endpoint, requested_params, status, metadata
                    )
                    values (%s, %s, %s, 'running', %s)
                    returning id
                    """,
                    (
                        source_id,
                        document.source_url,
                        Jsonb(
                            {
                                "manifest_version": 1,
                                "content_sha256": content_hash,
                            }
                        ),
                        Jsonb(
                            {
                                "data_boundary": "verified_knowledge",
                                "is_mock": False,
                            }
                        ),
                    ),
                )
                run_row = cursor.fetchone()
                if run_row is None:
                    raise RuntimeError("failed to create knowledge ingestion run")
                run_id: UUID = run_row[0]
                metadata = self._document_metadata(document)
                chunk_metadata = {**metadata, "is_active": True}
                existing = self._load_existing_document(
                    cursor,
                    source_id=source_id,
                    source_url=document.source_url,
                )
                unchanged = self._is_unchanged(
                    existing,
                    document=document,
                    content_hash=content_hash,
                    metadata=metadata,
                    chunk_metadata=chunk_metadata,
                )
                if unchanged:
                    assert existing is not None
                    document_id = existing.document_id
                    upserted_count = 0
                else:
                    document_id = self._write_document(
                        cursor,
                        existing=existing,
                        document=document,
                        source_id=source_id,
                        content_hash=content_hash,
                        metadata=metadata,
                    )
                    upserted_count = self._upsert_chunks(
                        cursor,
                        document_id=document_id,
                        chunks=document.chunks,
                        metadata=chunk_metadata,
                    )
                cursor.execute(
                    """
                    update public.ingestion_runs
                    set status = 'succeeded',
                        completed_at = now(),
                        response_code = 'LOCAL_FILE',
                        response_message = %s,
                        source_record_count = 1,
                        normalized_record_count = %s,
                        upserted_record_count = %s
                    where id = %s and status = 'running'
                    """,
                    (
                        "NO_CHANGE" if unchanged else "OK",
                        len(document.chunks),
                        upserted_count,
                        run_id,
                    ),
                )
            return KnowledgeIngestionResult(
                run_id=run_id,
                document_id=document_id,
                chunk_count=len(document.chunks),
                unchanged=unchanged,
            )
        except Exception as error:
            if source_id is not None:
                with suppress(psycopg.Error):
                    self._record_failed_run(source_id, document, error)
            raise

    @staticmethod
    def _document_metadata(document: KnowledgeDocumentInput) -> dict[str, object]:
        return {
            **document.metadata,
            "contains_personal_data": False,
            "data_boundary": "verified_knowledge",
            "is_mock": False,
        }

    @staticmethod
    def _load_existing_document(
        cursor: psycopg.Cursor,
        *,
        source_id: int,
        source_url: str,
    ) -> _StoredDocument | None:
        canonical_url = canonicalize_source_url(source_url)
        cursor.execute(
            """
            select
                id, document_type, title, publisher, source_url,
                published_at, as_of_date, license_status, content_hash,
                content, metadata
            from public.knowledge_documents
            where source_id = %s
              and split_part(rtrim(source_url, '/'), '#', 1) = %s
            order by (source_url = %s) desc, created_at desc
            limit 2
            """,
            (source_id, canonical_url, source_url),
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise RuntimeError("duplicate canonical knowledge documents exist")
        row = rows[0]
        document_id: UUID = row[0]
        cursor.execute(
            """
            select chunk_index, content, metadata
            from public.knowledge_chunks
            where document_id = %s
              and metadata ->> 'is_active' is distinct from 'false'
            order by chunk_index
            """,
            (document_id,),
        )
        chunks = tuple(
            (int(index), str(content), dict(metadata))
            for index, content, metadata in cursor.fetchall()
        )
        return _StoredDocument(
            document_id=document_id,
            document_type=str(row[1]),
            title=str(row[2]),
            publisher=str(row[3]),
            source_url=str(row[4]),
            published_at=row[5],
            as_of_date=row[6],
            license_status=str(row[7]),
            content_hash=row[8],
            content=row[9],
            metadata=dict(row[10]),
            active_chunks=chunks,
        )

    @staticmethod
    def _is_unchanged(
        existing: _StoredDocument | None,
        *,
        document: KnowledgeDocumentInput,
        content_hash: str,
        metadata: dict[str, object],
        chunk_metadata: dict[str, object],
    ) -> bool:
        if existing is None:
            return False
        expected_chunks = tuple(
            (index, chunk, chunk_metadata)
            for index, chunk in enumerate(document.chunks)
        )
        return (
            existing.document_type == document.document_type
            and existing.title == document.title
            and existing.publisher == document.publisher
            and existing.source_url == document.source_url
            and existing.published_at == document.published_at
            and existing.as_of_date == document.as_of_date
            and existing.license_status == document.license_status
            and existing.content_hash == content_hash
            and existing.content == document.content
            and existing.metadata == metadata
            and existing.active_chunks == expected_chunks
        )

    @staticmethod
    def _write_document(
        cursor: psycopg.Cursor,
        *,
        existing: _StoredDocument | None,
        document: KnowledgeDocumentInput,
        source_id: int,
        content_hash: str,
        metadata: dict[str, object],
    ) -> UUID:
        values = (
            document.document_type,
            document.title,
            document.publisher,
            document.source_url,
            document.published_at,
            document.as_of_date,
            document.license_status,
            content_hash,
            document.content,
            Jsonb(metadata),
        )
        if existing is not None:
            cursor.execute(
                """
                update public.knowledge_documents
                set document_type = %s,
                    title = %s,
                    publisher = %s,
                    source_url = %s,
                    published_at = %s,
                    as_of_date = %s,
                    license_status = %s,
                    content_hash = %s,
                    content = %s,
                    metadata = %s,
                    updated_at = now()
                where id = %s
                returning id
                """,
                (*values, existing.document_id),
            )
        else:
            cursor.execute(
                """
                insert into public.knowledge_documents (
                    source_id, document_type, title, publisher, source_url,
                    published_at, as_of_date, license_status, content_hash,
                    content, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (source_id, source_url) do update set
                    document_type = excluded.document_type,
                    title = excluded.title,
                    publisher = excluded.publisher,
                    published_at = excluded.published_at,
                    as_of_date = excluded.as_of_date,
                    license_status = excluded.license_status,
                    content_hash = excluded.content_hash,
                    content = excluded.content,
                    metadata = excluded.metadata,
                    updated_at = now()
                returning id
                """,
                (source_id, *values),
            )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("failed to upsert knowledge document")
        return row[0]

    @staticmethod
    def _upsert_chunks(
        cursor: psycopg.Cursor,
        *,
        document_id: UUID,
        chunks: tuple[str, ...],
        metadata: dict[str, object],
    ) -> int:
        cursor.executemany(
            """
            insert into public.knowledge_chunks as existing (
                document_id, chunk_index, content, token_count, metadata
            )
            values (%s, %s, %s, %s, %s)
            on conflict (document_id, chunk_index) do update set
                content = excluded.content,
                token_count = excluded.token_count,
                metadata = excluded.metadata,
                embedding = case
                    when existing.content is distinct from excluded.content then null
                    else existing.embedding
                end,
                embedding_model = case
                    when existing.content is distinct from excluded.content then null
                    else existing.embedding_model
                end,
                embedding_dimensions = case
                    when existing.content is distinct from excluded.content then null
                    else existing.embedding_dimensions
                end
            """,
            [
                (
                    document_id,
                    index,
                    chunk,
                    len(chunk.split()),
                    Jsonb(metadata),
                )
                for index, chunk in enumerate(chunks)
            ],
        )
        cursor.execute(
            """
            update public.knowledge_chunks
            set metadata = metadata || %s
            where document_id = %s
              and chunk_index >= %s
              and metadata ->> 'is_active' is distinct from 'false'
            """,
            (Jsonb({"is_active": False}), document_id, len(chunks)),
        )
        trailing_count = max(cursor.rowcount, 0)
        return len(chunks) + trailing_count

    def _record_failed_run(
        self,
        source_id: int,
        document: KnowledgeDocumentInput,
        error: Exception,
    ) -> None:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                insert into public.ingestion_runs (
                    source_id, endpoint, requested_params, status,
                    completed_at, error_message, metadata
                )
                values (%s, %s, '{}'::jsonb, 'failed', now(), %s, %s)
                """,
                (
                    source_id,
                    document.source_url,
                    type(error).__name__,
                    Jsonb(
                        {
                            "data_boundary": "verified_knowledge",
                            "is_mock": False,
                        }
                    ),
                ),
            )

    @staticmethod
    def _validate_document(document: KnowledgeDocumentInput) -> None:
        if document.source_code not in ALLOWED_KNOWLEDGE_SOURCE_CODES:
            raise ValueError("source_code is not approved for RAG ingestion")
        if document.document_type not in ALLOWED_KNOWLEDGE_DOCUMENT_TYPES:
            raise ValueError("document_type is not approved for RAG ingestion")
        if document.license_status != "permitted":
            raise ValueError("full RAG content requires license_status=permitted")
        if (
            not document.content.strip()
            or not document.chunks
            or any(not chunk.strip() for chunk in document.chunks)
        ):
            raise ValueError("RAG document content and chunks are required")
        if (
            not document.source_url.startswith("project://docs/")
            or canonicalize_source_url(document.source_url) != document.source_url
        ):
            raise ValueError("RAG source_url must be a canonical project document")
        if document.metadata.get("contains_personal_data") is not False:
            raise ValueError("RAG metadata must explicitly exclude personal data")
        if document.metadata.get("data_boundary") != "verified_knowledge":
            raise ValueError("RAG data_boundary must be verified_knowledge")
        if document.metadata.get("is_mock") is not False:
            raise ValueError("mock data must not be stored in RAG")
        if contains_sensitive_personal_data(
            "\n".join((document.content, *document.chunks))
        ):
            raise ValueError("personal identifier detected in RAG content")
        actual_hash = sha256(document.content.encode("utf-8")).hexdigest()
        if document.content_hash is not None and document.content_hash != actual_hash:
            raise ValueError("content_hash does not match RAG document content")
