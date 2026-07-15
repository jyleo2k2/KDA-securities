from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


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


class KnowledgeWriteRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def upsert_document(self, document: KnowledgeDocumentInput) -> UUID:
        """Compatibility wrapper; all writes are tracked by an ingestion run."""
        return self.ingest_document(document).document_id

    def ingest_document(
        self, document: KnowledgeDocumentInput
    ) -> KnowledgeIngestionResult:
        self._validate_document(document)
        content_hash = (
            document.content_hash
            or sha256(document.content.encode("utf-8")).hexdigest()
        )
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
                document_id = self._replace_document(
                    cursor,
                    document=document,
                    source_id=source_id,
                    content_hash=content_hash,
                )
                cursor.execute(
                    """
                    update public.ingestion_runs
                    set status = 'succeeded',
                        completed_at = now(),
                        response_code = 'LOCAL_FILE',
                        response_message = 'OK',
                        source_record_count = 1,
                        normalized_record_count = %s,
                        upserted_record_count = %s
                    where id = %s and status = 'running'
                    """,
                    (len(document.chunks), len(document.chunks), run_id),
                )
            return KnowledgeIngestionResult(
                run_id=run_id,
                document_id=document_id,
                chunk_count=len(document.chunks),
            )
        except Exception as error:
            if source_id is not None:
                with suppress(psycopg.Error):
                    self._record_failed_run(source_id, document, error)
            raise

    @staticmethod
    def _replace_document(
        cursor: psycopg.Cursor,
        *,
        document: KnowledgeDocumentInput,
        source_id: int,
        content_hash: str,
    ) -> UUID:
        metadata = {
            **document.metadata,
            "contains_personal_data": False,
            "data_boundary": "verified_knowledge",
            "is_mock": False,
        }
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
            (
                source_id,
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
            ),
        )
        document_row = cursor.fetchone()
        if document_row is None:
            raise RuntimeError("failed to upsert knowledge document")
        document_id: UUID = document_row[0]
        cursor.execute(
            "delete from public.knowledge_chunks where document_id = %s",
            (document_id,),
        )
        cursor.executemany(
            """
            insert into public.knowledge_chunks (
                document_id, chunk_index, content, token_count, metadata
            )
            values (%s, %s, %s, %s, %s)
            """,
            [
                (
                    document_id,
                    index,
                    chunk,
                    len(chunk.split()),
                    Jsonb(metadata),
                )
                for index, chunk in enumerate(document.chunks)
            ],
        )
        return document_id

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
        if document.license_status != "permitted":
            raise ValueError("full RAG content requires license_status=permitted")
        if not document.content.strip() or not document.chunks:
            raise ValueError("RAG document content and chunks are required")
        if document.document_type == "news":
            raise ValueError("news content is not part of verified-knowledge RAG")
        if document.metadata.get("contains_personal_data") is not False:
            raise ValueError("RAG metadata must explicitly exclude personal data")
        if document.metadata.get("data_boundary") != "verified_knowledge":
            raise ValueError("RAG data_boundary must be verified_knowledge")
        if document.metadata.get("is_mock") is not False:
            raise ValueError("mock data must not be stored in RAG")
