"""Shared test doubles reused across multiple test modules."""

import json
from uuid import UUID, uuid4

from backend.app.chat.repository import SavedChatExchange


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Split an SSE stream body into (event, data) pairs."""

    events = []
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        event_line, data_line = block.split("\n", 1)
        events.append(
            (
                event_line.removeprefix("event: "),
                json.loads(data_line.removeprefix("data: ")),
            )
        )
    return events


def final_sse_response(text: str) -> dict:
    """Return the payload of the terminal "response" SSE event."""

    for event, data in parse_sse(text):
        if event == "response":
            return data
    raise AssertionError("no response event in SSE stream")


class FakeChatRepository:
    """Minimal ChatRepository double: no-op idempotency lookup + in-memory save."""

    def __init__(
        self,
        *,
        session_id: UUID | None = None,
        user_message_id: UUID | None = None,
        assistant_message_id: UUID | None = None,
    ) -> None:
        self.saved: list[dict[str, object]] = []
        self._session_id = session_id or uuid4()
        self._user_message_id = user_message_id or uuid4()
        self._assistant_message_id = assistant_message_id or uuid4()

    def find_idempotent_exchange(self, **kwargs) -> SavedChatExchange | None:
        return None

    def save_exchange(self, **kwargs) -> SavedChatExchange:
        self.saved.append(kwargs)
        return SavedChatExchange(
            session_id=self._session_id,
            user_message_id=self._user_message_id,
            assistant_message_id=self._assistant_message_id,
            response=kwargs.get("response"),
        )


class FakeConnection:
    """psycopg-style connection double wrapping a single fake cursor."""

    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self.exit_exception = None

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.exit_exception = exc_type
        return False

    def cursor(self):
        return self._cursor
