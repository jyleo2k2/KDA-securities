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


class KnowledgeWriteRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def upsert_document(self, document: KnowledgeDocumentInput) -> UUID:
        if document.license_status != "permitted":
            raise ValueError("full RAG content requires license_status=permitted")
        if not document.content.strip() or not document.chunks:
            raise ValueError("RAG document content and chunks are required")
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
                    source_row[0],
                    document.document_type,
                    document.title,
                    document.publisher,
                    document.source_url,
                    document.published_at,
                    document.as_of_date,
                    document.license_status,
                    document.content,
                    Jsonb({"contains_personal_data": False}),
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
                        Jsonb({"contains_personal_data": False}),
                    )
                    for index, chunk in enumerate(document.chunks)
                ],
            )
            return document_id
