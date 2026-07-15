import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from .orchestrator import AnswerSource, EvidenceAnswer


class ChatSessionAccessError(LookupError):
    """The session does not exist or is not owned by the authenticated user."""


@dataclass(frozen=True, slots=True)
class ChatSessionSummary:
    session_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StoredMessageEvidence:
    document_id: UUID | None
    chunk_id: int | None
    news_item_id: UUID | None
    source_locator: str
    quote_text: str | None
    rank: int | None


@dataclass(frozen=True, slots=True)
class StoredChatMessage:
    message_id: UUID
    role: str
    content: str
    model_name: str | None
    created_at: datetime
    evidence: tuple[StoredMessageEvidence, ...]


class ChatRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def save_user_question(
        self,
        *,
        owner_id: UUID,
        question: str,
        session_id: UUID | None = None,
    ) -> tuple[UUID, UUID]:
        title = question.strip()[:80]
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            if session_id is None:
                cursor.execute(
                    """
                    insert into public.chat_sessions (owner_id, title)
                    values (%s, %s)
                    returning id
                    """,
                    (owner_id, title),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("failed to create chat session")
                session_id = row[0]
            else:
                self._lock_owned_session(cursor, session_id, owner_id)
            cursor.execute(
                """
                insert into public.chat_messages (session_id, role, content)
                values (%s, 'user', %s)
                returning id
                """,
                (session_id, question),
            )
            message_row = cursor.fetchone()
            if message_row is None:
                raise RuntimeError("failed to save user chat message")
            cursor.execute(
                """
                update public.chat_sessions
                set updated_at = now()
                where id = %s and owner_id = %s
                """,
                (session_id, owner_id),
            )
            return session_id, message_row[0]

    def save_assistant_answer(
        self,
        *,
        owner_id: UUID,
        session_id: UUID,
        user_message_id: UUID,
        answer: EvidenceAnswer,
        model_name: str,
    ) -> UUID:
        content = json.dumps(
            {
                "question_message_id": str(user_message_id),
                "answer": json.loads(answer.model_dump_json()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            self._lock_owned_session(cursor, session_id, owner_id)
            cursor.execute(
                """
                insert into public.chat_messages (
                    session_id, role, content, model_name
                )
                values (%s, 'assistant', %s, %s)
                returning id
                """,
                (session_id, content, model_name),
            )
            message_row = cursor.fetchone()
            if message_row is None:
                raise RuntimeError("failed to save assistant chat message")
            message_id: UUID = message_row[0]
            evidence_rows = self._evidence_rows(message_id, answer)
            if evidence_rows:
                cursor.executemany(
                    """
                    insert into public.chat_message_evidence (
                        message_id, document_id, chunk_id, news_item_id,
                        source_locator, quote_text, rank
                    )
                    values (
                        %(message_id)s, %(document_id)s, %(chunk_id)s,
                        %(news_item_id)s, %(source_locator)s,
                        %(quote_text)s, %(rank)s
                    )
                    """,
                    evidence_rows,
                )
            cursor.execute(
                """
                update public.chat_sessions
                set updated_at = now()
                where id = %s and owner_id = %s
                """,
                (session_id, owner_id),
            )
            return message_id

    def list_sessions(self, owner_id: UUID) -> list[ChatSessionSummary]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select id, title, created_at, updated_at
                from public.chat_sessions
                where owner_id = %s
                order by updated_at desc, id
                """,
                (owner_id,),
            )
            return [ChatSessionSummary(*row) for row in cursor]

    def get_messages(
        self, *, owner_id: UUID, session_id: UUID
    ) -> list[StoredChatMessage]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            self._require_owned_session(cursor, session_id, owner_id)
            cursor.execute(
                """
                select id, role, content, model_name, created_at
                from public.chat_messages
                where session_id = %s
                order by created_at, id
                """,
                (session_id,),
            )
            message_rows = list(cursor)
            message_ids = [row[0] for row in message_rows]
            evidence_by_message: dict[UUID, list[StoredMessageEvidence]] = {
                message_id: [] for message_id in message_ids
            }
            if message_ids:
                cursor.execute(
                    """
                    select
                        message_id, document_id, chunk_id, news_item_id,
                        source_locator, quote_text, rank
                    from public.chat_message_evidence
                    where message_id = any(%s::uuid[])
                    order by message_id, rank nulls last, id
                    """,
                    (message_ids,),
                )
                for row in cursor:
                    evidence_by_message[row[0]].append(
                        StoredMessageEvidence(*row[1:])
                    )
            return [
                StoredChatMessage(
                    message_id=row[0],
                    role=row[1],
                    content=row[2],
                    model_name=row[3],
                    created_at=row[4],
                    evidence=tuple(evidence_by_message[row[0]]),
                )
                for row in message_rows
            ]

    @staticmethod
    def _require_owned_session(
        cursor: Any, session_id: UUID, owner_id: UUID
    ) -> None:
        cursor.execute(
            """
            select 1
            from public.chat_sessions
            where id = %s and owner_id = %s
            """,
            (session_id, owner_id),
        )
        if cursor.fetchone() is None:
            raise ChatSessionAccessError("chat session was not found")

    @staticmethod
    def _lock_owned_session(
        cursor: Any, session_id: UUID, owner_id: UUID
    ) -> None:
        cursor.execute(
            """
            select 1
            from public.chat_sessions
            where id = %s and owner_id = %s
            for update
            """,
            (session_id, owner_id),
        )
        if cursor.fetchone() is None:
            raise ChatSessionAccessError("chat session was not found")

    @staticmethod
    def _evidence_rows(
        message_id: UUID, answer: EvidenceAnswer
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        quote = answer.narrative.facts[:2000]
        for rank, source in enumerate(answer.sources, start=1):
            references = ChatRepository._source_references(source)
            if references is None:
                continue
            document_id, chunk_id, news_item_id = references
            rows.append(
                {
                    "message_id": message_id,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "news_item_id": news_item_id,
                    "source_locator": source.url,
                    "quote_text": quote,
                    "rank": rank,
                }
            )
        return rows

    @staticmethod
    def _source_references(
        source: AnswerSource,
    ) -> tuple[UUID | None, int | None, UUID | None] | None:
        if source.news_item_id is not None:
            return None, None, UUID(source.news_item_id)
        if source.chunk_id is not None:
            document_id = UUID(source.document_id) if source.document_id else None
            return document_id, source.chunk_id, None
        return None
