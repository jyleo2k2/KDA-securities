import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require_supabase_user_id
from ..chat.orchestrator import EvidenceAnswer
from ..chat.repository import (
    ChatRepository,
    ChatSessionAccessError,
    ChatSessionSummary,
    StoredChatMessage,
    StoredMessageEvidence,
)
from ..chat.service import (
    ChatService,
    DataSourceUnavailableError,
    LocalMarkdownKnowledgeRepository,
    QueryPlanExecutionError,
    get_chat_service,
)
from ..engine import PortfolioInput
from ..settings import Settings, get_settings
from .deps import _database_url_or_503

router = APIRouter(tags=["chat"])

_DATABASE_ERRORS = (psycopg.Error, ConnectionError)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    portfolio: PortfolioInput | None = None


class DemoChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    portfolio: PortfolioInput | None = None


class ChatResponse(BaseModel):
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    answer: EvidenceAnswer


class DemoChatResponse(BaseModel):
    persisted: bool = False
    answer: EvidenceAnswer


class SessionOut(BaseModel):
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


class MessageOut(BaseModel):
    message_id: UUID
    question_message_id: UUID | None
    role: str
    content: str
    answer: EvidenceAnswer | None
    model_name: str | None
    created_at: datetime
    evidence: list[MessageEvidenceOut]


def get_chat_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatRepository:
    database_url = _database_url_or_503(
        settings, detail="Chat database is not configured"
    )
    return ChatRepository(database_url)


def get_authenticated_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatService:
    _database_url_or_503(settings, detail="Chat database is not configured")
    return get_chat_service(settings)


def get_demo_chat_service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        disclosures=None,
        news=None,
        backend="local",
    )


def _answer_or_http_error(
    service: ChatService,
    request: ChatRequest | DemoChatRequest,
) -> EvidenceAnswer:
    try:
        return service.answer_question(
            request.question,
            portfolio=request.portfolio,
        )
    except QueryPlanExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except DataSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat data source is unavailable",
        ) from exc


@router.post("/chat/demo", response_model=DemoChatResponse)
def chat_demo(
    request: DemoChatRequest,
    service: Annotated[ChatService, Depends(get_demo_chat_service)],
) -> DemoChatResponse:
    answer = _answer_or_http_error(service, request)
    return DemoChatResponse(answer=answer)


@router.post("/chat", response_model=ChatResponse)
def chat_authenticated(
    request: ChatRequest,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
    service: Annotated[ChatService, Depends(get_authenticated_chat_service)],
) -> ChatResponse:
    try:
        session_id, user_message_id = repository.save_user_question(
            owner_id=owner_id,
            question=request.question,
            session_id=request.session_id,
        )
    except ChatSessionAccessError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc

    answer = _answer_or_http_error(service, request)
    model_name = "llm-restyled" if answer.used_llm_rewrite else "deterministic"
    try:
        assistant_message_id = repository.save_assistant_answer(
            owner_id=owner_id,
            session_id=session_id,
            user_message_id=user_message_id,
            answer=answer,
            model_name=model_name,
        )
    except ChatSessionAccessError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc
    return ChatResponse(
        session_id=session_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        answer=answer,
    )


@router.get("/chat/sessions", response_model=list[SessionOut])
def list_chat_sessions(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> list[SessionOut]:
    try:
        sessions: list[ChatSessionSummary] = repository.list_sessions(owner_id)
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc
    return [SessionOut.model_validate(session) for session in sessions]


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=list[MessageOut],
)
def get_chat_messages(
    session_id: UUID,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> list[MessageOut]:
    try:
        messages = repository.get_messages(
            owner_id=owner_id, session_id=session_id
        )
    except ChatSessionAccessError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat database is unavailable",
        ) from exc
    return [_message_out(message) for message in messages]


def _message_out(message: StoredChatMessage) -> MessageOut:
    answer = None
    question_message_id = None
    if message.role == "assistant":
        try:
            payload = json.loads(message.content)
            if "answer" in payload:
                answer = EvidenceAnswer.model_validate(payload["answer"])
                question_message_id = UUID(payload["question_message_id"])
            else:
                answer = EvidenceAnswer.model_validate(payload)
        except (json.JSONDecodeError, ValueError, TypeError):
            answer = None
    evidence: tuple[StoredMessageEvidence, ...] = message.evidence
    return MessageOut(
        message_id=message.message_id,
        question_message_id=question_message_id,
        role=message.role,
        content=message.content,
        answer=answer,
        model_name=message.model_name,
        created_at=message.created_at,
        evidence=[MessageEvidenceOut.model_validate(item) for item in evidence],
    )
