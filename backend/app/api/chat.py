"""Chat endpoints with optional Claude narration and authenticated history."""

import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from ..auth import require_supabase_user_id
from ..chat import ChatRequest, ChatResponse, ChatService
from ..chat.models import ChatCapabilities, ChatIntent, ScenarioSummary
from ..chat.narrator import ClaudeNarrator
from ..chat.repository import (
    ChatRepository,
    ChatSessionAccessError,
    ChatSessionSummary,
    StoredChatMessage,
    StoredMessageEvidence,
)
from ..chat.scenarios import LocalScenarioRepository
from .deps import (
    get_chat_narrator,
    get_chat_repository,
    get_chat_service,
    get_optional_chat_repository,
)

router = APIRouter(tags=["chat"])

_DATABASE_ERRORS = (psycopg.Error, ConnectionError)


class AuthenticatedChatRequest(ChatRequest):
    session_id: UUID | None = None


class PersistedChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persisted: bool
    session_id: UUID | None = None
    user_message_id: UUID | None = None
    assistant_message_id: UUID | None = None
    response: ChatResponse


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID | None
    chunk_id: int | None
    news_item_id: UUID | None
    source_locator: str
    quote_text: str | None
    rank: int | None


class StoredChatMessageOut(BaseModel):
    message_id: UUID
    question_message_id: UUID | None
    role: str
    content: str
    response: ChatResponse | None
    model_name: str | None
    created_at: datetime
    evidence: list[MessageEvidenceOut]


@router.get("/chat/demo/capabilities", response_model=ChatCapabilities)
def chat_capabilities(
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatCapabilities:
    return service.capabilities()


@router.get("/chat/demo/scenarios", response_model=list[ScenarioSummary])
def chat_scenarios() -> list[ScenarioSummary]:
    return LocalScenarioRepository().list()


@router.post("/chat/demo", response_model=ChatResponse)
def chat_demo(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
) -> ChatResponse:
    """Unauthenticated MVP using mock accounts and read-only evidence."""

    try:
        response = service.ask(request)
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat data source is unavailable",
        ) from exc
    return narrator.narrate(response) if narrator is not None else response


@router.post("/chat", response_model=PersistedChatResponse)
def chat_authenticated(
    request: AuthenticatedChatRequest,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        ChatRepository | None, Depends(get_optional_chat_repository)
    ],
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
) -> PersistedChatResponse:
    """Generate first, then atomically save one verified exchange."""

    chat_request = ChatRequest.model_validate(
        request.model_dump(exclude={"session_id"})
    )
    plan = service.plan(chat_request)
    try:
        response = service.ask(chat_request, plan=plan)
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat data source is unavailable",
        ) from exc
    if narrator is not None:
        response = narrator.narrate(response)

    if response.intent == ChatIntent.OUT_OF_SCOPE:
        return PersistedChatResponse(persisted=False, response=response)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is not configured",
        )

    try:
        saved = repository.save_exchange(
            owner_id=owner_id,
            question=plan.normalized_message,
            response=response,
            session_id=request.session_id,
        )
    except ChatSessionAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc
    return PersistedChatResponse(
        persisted=True,
        session_id=saved.session_id,
        user_message_id=saved.user_message_id,
        assistant_message_id=saved.assistant_message_id,
        response=response,
    )


@router.get("/chat/sessions", response_model=list[ChatSessionOut])
def list_chat_sessions(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> list[ChatSessionOut]:
    try:
        sessions: list[ChatSessionSummary] = repository.list_sessions(owner_id)
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc
    return [ChatSessionOut.model_validate(session) for session in sessions]


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=list[StoredChatMessageOut],
)
def get_chat_messages(
    session_id: UUID,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> list[StoredChatMessageOut]:
    try:
        messages = repository.get_messages(
            owner_id=owner_id, session_id=session_id
        )
    except ChatSessionAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc
    return [_message_out(message) for message in messages]


def _message_out(message: StoredChatMessage) -> StoredChatMessageOut:
    response = None
    question_message_id = None
    content = message.content
    if message.role == "assistant":
        try:
            payload = json.loads(message.content)
            if not isinstance(payload, dict):
                raise TypeError("assistant payload must be a JSON object")
            if payload.get("schema_version") == 1:
                response = ChatResponse.model_validate(payload["response"])
                question_message_id = UUID(payload["question_message_id"])
                content = response.answer
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            response = None
            question_message_id = None
            content = "저장된 답변 형식을 읽을 수 없습니다."
    evidence: tuple[StoredMessageEvidence, ...] = message.evidence
    return StoredChatMessageOut(
        message_id=message.message_id,
        question_message_id=question_message_id,
        role=message.role,
        content=content,
        response=response,
        model_name=message.model_name,
        created_at=message.created_at,
        evidence=[MessageEvidenceOut.model_validate(item) for item in evidence],
    )
