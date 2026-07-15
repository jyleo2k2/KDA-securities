from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass(frozen=True, slots=True)
class KnowledgeSourceInput:
    code: str
    name: str
    source_type: str
    authority: str
    base_url: str


@dataclass(frozen=True, slots=True)
class KnowledgeRunHandle:
    run_id: UUID
    source_id: int


class KnowledgeWriteRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def start_run(self, source: KnowledgeSourceInput) -> KnowledgeRunHandle:
        if source.source_type not in {"official_document", "curated"}:
            raise ValueError("knowledge source must be official_document or curated")
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                insert into public.data_sources (
                    code, name, source_type, authority, base_url, metadata
                )
                values (%s, %s, %s, %s, %s, %s)
                on conflict (code) do update set
                    name = excluded.name,
                    source_type = excluded.source_type,
                    authority = excluded.authority,
                    base_url = excluded.base_url,
                    metadata = excluded.metadata,
                    is_active = true,
                    updated_at = now()
                returning id
                """,
                (
                    source.code,
                    source.name,
                    source.source_type,
                    source.authority,
                    source.base_url,
                    Jsonb({"data_boundary": "verified_knowledge", "is_mock": False}),
                ),
            )
            source_row = cursor.fetchone()
            if source_row is None:
                raise RuntimeError("failed to resolve knowledge data source")
            source_id = int(source_row[0])
            cursor.execute(
                """
                insert into public.ingestion_runs (
                    source_id, endpoint, requested_params, status, metadata
                )
                values (%s, %s, '{}'::jsonb, 'running', %s)
                returning id
                """,
                (
                    source_id,
                    source.base_url,
                    Jsonb({"data_boundary": "verified_knowledge", "is_mock": False}),
                ),
            )
            run_row = cursor.fetchone()
            if run_row is None:
                raise RuntimeError("failed to create knowledge ingestion run")
            return KnowledgeRunHandle(run_id=run_row[0], source_id=source_id)

    def complete_document(
        self,
        handle: KnowledgeRunHandle,
        document: KnowledgeDocumentInput,
    ) -> UUID:
        document_id = self._upsert_document(document, source_id=handle.source_id)
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'succeeded', completed_at = now(),
                    response_code = 'LOCAL_OR_HTTP_DOCUMENT',
                    response_message = 'validated and chunked',
                    source_record_count = 1,
                    normalized_record_count = %s,
                    upserted_record_count = %s,
                    metadata = metadata || %s
                where id = %s and status = 'running'
                """,
                (
                    len(document.chunks),
                    len(document.chunks),
                    Jsonb(
                        {
                            "outcome": "succeeded",
                            "document_id": str(document_id),
                            "source_url": document.source_url,
                        }
                    ),
                    handle.run_id,
                ),
            )
        return document_id

    def fail_run(self, run_id: UUID, error: Exception) -> None:
        safe_message = f"{type(error).__name__}: {error}"[:1000]
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'failed', completed_at = now(), error_message = %s,
                    metadata = metadata || '{"outcome":"failed"}'::jsonb
                where id = %s and status = 'running'
                """,
                (safe_message, run_id),
            )

    def upsert_document(self, document: KnowledgeDocumentInput) -> UUID:
        return self._upsert_document(document)

    def _upsert_document(
        self,
        document: KnowledgeDocumentInput,
        *,
        source_id: int | None = None,
    ) -> UUID:
        if document.license_status != "permitted":
            raise ValueError("full RAG content requires license_status=permitted")
        if not document.content.strip() or not document.chunks:
            raise ValueError("RAG document content and chunks are required")
        if not document.source_url.strip():
            raise ValueError("knowledge source_url is required")
        if document.published_at is None and document.as_of_date is None:
            raise ValueError("published_at or as_of_date is required")
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            if source_id is None:
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
                insert into public.knowledge_documents (
                    source_id, document_type, title, publisher, source_url,
                    published_at, as_of_date, license_status, content, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (source_id, source_url) do update set
                    document_type = excluded.document_type,
                    title = excluded.title,
                    publisher = excluded.publisher,
                    published_at = excluded.published_at,
                    as_of_date = excluded.as_of_date,
                    license_status = excluded.license_status,
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
                    document.content,
                    Jsonb(
                        {
                            "contains_personal_data": False,
                            "verification_status": "verified",
                            "data_boundary": "verified_knowledge",
                            "is_mock": False,
                        }
                    ),
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
                    document_id, chunk_index, content, metadata
                )
                values (%s, %s, %s, %s)
                """,
                [
                    (
                        document_id,
                        index,
                        chunk,
                        Jsonb(
                            {
                                "contains_personal_data": False,
                                "data_boundary": "verified_knowledge",
                                "is_mock": False,
                            }
                        ),
                    )
                    for index, chunk in enumerate(document.chunks)
                ],
            )
            return document_id
