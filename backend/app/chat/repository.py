import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from .models import ChatResponse, ConversationContext, DataBoundary


class ChatSessionAccessError(LookupError):
    """The session is absent or belongs to another authenticated user."""


@dataclass(frozen=True, slots=True)
class SavedChatExchange:
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    replayed: bool = False
    response: ChatResponse | None = None


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


_KNOWLEDGE_EVIDENCE_ID = re.compile(r"^knowledge:(\d+)$")
_NEWS_EVIDENCE_ID = re.compile(r"^news:([0-9a-fA-F-]{36})$")
_MessageRow = tuple[UUID, str, str, str | None, datetime]


def _assistant_question_message_id(content: str) -> UUID | None:
    try:
        payload = json.loads(content)
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return None
        return UUID(payload["question_message_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _assistant_conversation_context(content: str) -> ConversationContext | None:
    try:
        payload = json.loads(content)
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return None
        response = payload.get("response")
        if not isinstance(response, dict):
            return None
        context = response.get("conversation_context")
        return (
            ConversationContext.model_validate(context)
            if context is not None
            else None
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _order_message_rows(message_rows: list[_MessageRow]) -> list[_MessageRow]:
    """Keep each persisted assistant response beside its question."""

    rows_by_id = {row[0]: row for row in message_rows}

    def sort_key(
        row: _MessageRow,
    ) -> tuple[datetime, str, int, datetime, str]:
        anchor = row
        exchange_position = 0
        if row[1] == "assistant":
            question_id = _assistant_question_message_id(row[2])
            question = rows_by_id.get(question_id) if question_id else None
            if question is not None and question[1] == "user":
                anchor = question
                exchange_position = 1
        return (
            anchor[4],
            str(anchor[0]),
            exchange_position,
            row[4],
            str(row[0]),
        )

    return sorted(message_rows, key=sort_key)


class ChatRepository:
    def __init__(
        self, database_url: str, *, pool: ConnectionPool | None = None
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def save_exchange(
        self,
        *,
        owner_id: UUID,
        question: str,
        response: ChatResponse,
        session_id: UUID | None = None,
        idempotency_key: UUID | None = None,
    ) -> SavedChatExchange:
        """Persist both messages and relational evidence in one transaction."""

        title = question.strip()[:80]
        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            if idempotency_key is not None:
                # Serialize only retries for the same owner/key.  This prevents
                # two concurrent HTTP retries from creating two exchanges.
                cursor.execute(
                    """
                    select pg_advisory_xact_lock(
                        hashtextextended(%s, 0)
                    )
                    """,
                    (f"chat:{owner_id}:{idempotency_key}",),
                )
                replayed = self._find_idempotent_exchange(
                    cursor, owner_id, idempotency_key
                )
                if replayed is not None:
                    return replayed
            if session_id is None:
                cursor.execute(
                    """
                    insert into public.chat_sessions (owner_id, title)
                    values (%s, %s)
                    returning id
                    """,
                    (owner_id, title),
                )
                session_row = cursor.fetchone()
                if session_row is None:
                    raise RuntimeError("failed to create chat session")
                session_id = session_row[0]
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
            user_row = cursor.fetchone()
            if user_row is None:
                raise RuntimeError("failed to save user chat message")
            user_message_id: UUID = user_row[0]

            assistant_content = json.dumps(
                {
                    "schema_version": 1,
                    "question_message_id": str(user_message_id),
                    "response": response.model_dump(mode="json"),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            cursor.execute(
                """
                insert into public.chat_messages (
                    session_id, role, content, model_name
                )
                values (%s, 'assistant', %s, %s)
                returning id
                """,
                (
                    session_id,
                    assistant_content,
                    response.model_name,
                ),
            )
            assistant_row = cursor.fetchone()
            if assistant_row is None:
                raise RuntimeError("failed to save assistant chat message")
            assistant_message_id: UUID = assistant_row[0]

            evidence_rows = self._evidence_rows(assistant_message_id, response)
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
            if idempotency_key is not None:
                cursor.execute(
                    """
                    insert into public.chat_request_idempotency (
                        owner_id, idempotency_key, session_id,
                        user_message_id, assistant_message_id
                    )
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        owner_id,
                        idempotency_key,
                        session_id,
                        user_message_id,
                        assistant_message_id,
                    ),
                )
            return SavedChatExchange(
                session_id=session_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            )

    def find_idempotent_exchange(
        self, *, owner_id: UUID, idempotency_key: UUID
    ) -> SavedChatExchange | None:
        """Return an already committed exchange before invoking the LLM."""

        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            return self._find_idempotent_exchange(
                cursor, owner_id, idempotency_key
            )

    @staticmethod
    def _find_idempotent_exchange(
        cursor: Any, owner_id: UUID, idempotency_key: UUID
    ) -> SavedChatExchange | None:
        cursor.execute(
            """
            select
                request.session_id,
                request.user_message_id,
                request.assistant_message_id,
                assistant.content
            from public.chat_request_idempotency as request
            join public.chat_messages as assistant
              on assistant.id = request.assistant_message_id
            where request.owner_id = %s
              and request.idempotency_key = %s
            """,
            (owner_id, idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[3])
            stored_response = ChatResponse.model_validate(payload["response"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("stored idempotent chat response is invalid") from exc
        return SavedChatExchange(
            session_id=row[0],
            user_message_id=row[1],
            assistant_message_id=row[2],
            replayed=True,
            response=stored_response,
        )

    def list_sessions(self, owner_id: UUID) -> list[ChatSessionSummary]:
        with (
            self._connection() as connection,
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
            self._connection() as connection,
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
            # PostgreSQL now() is transaction-stable, so both halves of an
            # exchange can share a timestamp. Pair them before returning history.
            message_rows = _order_message_rows(list(cursor))
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

    def get_latest_conversation_context(
        self, *, owner_id: UUID, session_id: UUID
    ) -> ConversationContext | None:
        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            self._require_owned_session(cursor, session_id, owner_id)
            cursor.execute(
                """
                select content
                from public.chat_messages
                where session_id = %s and role = 'assistant'
                order by created_at desc, id desc
                limit 20
                """,
                (session_id,),
            )
            for row in cursor:
                context = _assistant_conversation_context(row[0])
                if context is not None:
                    return context
        return None

    def delete_session(self, *, owner_id: UUID, session_id: UUID) -> None:
        """Delete one owned session and its database-cascaded children."""

        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                delete from public.chat_sessions
                where id = %s and owner_id = %s
                returning id
                """,
                (session_id, owner_id),
            )
            if cursor.fetchone() is None:
                raise ChatSessionAccessError("chat session was not found")

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
        message_id: UUID, response: ChatResponse
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for rank, source in enumerate(response.sources, start=1):
            document_id: UUID | None = None
            chunk_id: int | None = None
            news_item_id: UUID | None = None
            if source.data_boundary == DataBoundary.VERIFIED_KNOWLEDGE:
                match = _KNOWLEDGE_EVIDENCE_ID.fullmatch(source.evidence_id)
                if match is None:
                    continue
                chunk_id = int(match.group(1))
            elif source.data_boundary in {
                DataBoundary.NEWS_METADATA,
                DataBoundary.NEWS_SUMMARY,
            }:
                match = _NEWS_EVIDENCE_ID.fullmatch(source.evidence_id)
                if match is None:
                    continue
                try:
                    news_item_id = UUID(match.group(1))
                except ValueError:
                    continue
            else:
                continue
            rows.append(
                {
                    "message_id": message_id,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "news_item_id": news_item_id,
                    "source_locator": source.locator,
                    "quote_text": None,
                    "rank": rank,
                }
            )
        return rows
