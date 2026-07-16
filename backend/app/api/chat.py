"""Chat endpoints with optional Claude narration and authenticated history."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from time import perf_counter
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict
from starlette.responses import StreamingResponse

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
logger = logging.getLogger("uvicorn.error")

_DATABASE_ERRORS = (psycopg.Error, ConnectionError)


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _log_stream_latency(
    *,
    intent: ChatIntent,
    answer_started_at: float,
    narration_started_at: float | None,
    started_at: float,
) -> None:
    finished_at = perf_counter()
    answer_ms = (narration_started_at or finished_at) - answer_started_at
    narration_ms = (
        finished_at - narration_started_at if narration_started_at is not None else 0
    )
    logger.info(
        "chat_stream_latency intent=%s answer_ms=%d narration_ms=%d total_ms=%d",
        intent,
        answer_ms * 1000,
        narration_ms * 1000,
        (finished_at - started_at) * 1000,
    )


async def _stream_answer(
    *,
    request: ChatRequest,
    service: ChatService,
    narrator: ClaudeNarrator | None,
) -> AsyncIterator[str]:
    started_at = perf_counter()
    plan = service.plan(request)
    yield _sse("phase", {"message": "근거를 검색하고 있습니다."})
    answer_started_at = perf_counter()
    try:
        response = await asyncio.to_thread(service.ask, request, plan=plan)
    except _DATABASE_ERRORS:
        yield _sse("error", {"detail": "Chat data source is unavailable"})
        return
    if narrator is not None:
        yield _sse("phase", {"message": "검증된 설명을 생성하고 있습니다."})
        narration_started_at = perf_counter()
        response = await asyncio.to_thread(
            narrator.narrate,
            response,
            pension_tax_input=request.pension_tax,
            pension_tax_message=request.message,
        )
    else:
        narration_started_at = None
    _log_stream_latency(
        intent=response.intent,
        answer_started_at=answer_started_at,
        narration_started_at=narration_started_at,
        started_at=started_at,
    )
    yield _sse("phase", {"message": "답변 검증을 완료했습니다."})
    yield _sse("response", {"response": response.model_dump(mode="json")})


class AuthenticatedChatRequest(ChatRequest):
    session_id: UUID | None = None


class PersistedChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persisted: bool
    session_id: UUID | None = None
    user_message_id: UUID | None = None
    assistant_message_id: UUID | None = None
    idempotency_replayed: bool = False
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
    return (
        narrator.narrate(
            response,
            pension_tax_input=request.pension_tax,
            pension_tax_message=request.message,
        )
        if narrator is not None
        else response
    )


@router.post("/chat/demo/stream")
async def chat_demo_stream(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
) -> StreamingResponse:
    """Stream safe progress events and one final validated demo response."""

    return StreamingResponse(
        _stream_answer(request=request, service=service, narrator=narrator),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat", response_model=PersistedChatResponse)
def chat_authenticated(
    request: AuthenticatedChatRequest,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        ChatRepository | None, Depends(get_optional_chat_repository)
    ],
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> PersistedChatResponse:
    """Generate first, then atomically save one verified exchange."""

    if repository is not None:
        try:
            replayed = repository.find_idempotent_exchange(
                owner_id=owner_id, idempotency_key=idempotency_key
            )
        except _DATABASE_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Chat database is unavailable",
            ) from exc
        if replayed is not None and replayed.response is not None:
            return PersistedChatResponse(
                persisted=True,
                session_id=replayed.session_id,
                user_message_id=replayed.user_message_id,
                assistant_message_id=replayed.assistant_message_id,
                idempotency_replayed=True,
                response=replayed.response,
            )

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
        response = narrator.narrate(
            response,
            pension_tax_input=chat_request.pension_tax,
            pension_tax_message=chat_request.message,
        )

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
            idempotency_key=idempotency_key,
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
        idempotency_replayed=saved.replayed,
        response=saved.response or response,
    )


@router.post("/chat/stream")
async def chat_authenticated_stream(
    request: AuthenticatedChatRequest,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        ChatRepository | None, Depends(get_optional_chat_repository)
    ],
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> StreamingResponse:
    """Authenticated variant that persists the final validated response."""

    async def events() -> AsyncIterator[str]:
        if repository is None:
            yield _sse("error", {"detail": "Chat database is not configured"})
            return
        yield _sse("phase", {"message": "요청을 확인하고 있습니다."})
        try:
            replayed = await asyncio.to_thread(
                repository.find_idempotent_exchange,
                owner_id=owner_id,
                idempotency_key=idempotency_key,
            )
        except _DATABASE_ERRORS:
            yield _sse("error", {"detail": "Chat database is unavailable"})
            return
        if replayed is not None and replayed.response is not None:
            yield _sse(
                "response",
                {
                    "persisted": True,
                    "session_id": str(replayed.session_id),
                    "user_message_id": str(replayed.user_message_id),
                    "assistant_message_id": str(replayed.assistant_message_id),
                    "idempotency_replayed": True,
                    "response": replayed.response.model_dump(mode="json"),
                },
            )
            return

        chat_request = ChatRequest.model_validate(
            request.model_dump(exclude={"session_id"})
        )
        started_at = perf_counter()
        plan = service.plan(chat_request)
        yield _sse("phase", {"message": "근거를 검색하고 있습니다."})
        answer_started_at = perf_counter()
        try:
            response = await asyncio.to_thread(service.ask, chat_request, plan=plan)
        except _DATABASE_ERRORS:
            yield _sse("error", {"detail": "Chat data source is unavailable"})
            return
        if narrator is not None:
            yield _sse("phase", {"message": "검증된 설명을 생성하고 있습니다."})
            narration_started_at = perf_counter()
            response = await asyncio.to_thread(
                narrator.narrate,
                response,
                pension_tax_input=chat_request.pension_tax,
                pension_tax_message=chat_request.message,
            )
        else:
            narration_started_at = None
        _log_stream_latency(
            intent=response.intent,
            answer_started_at=answer_started_at,
            narration_started_at=narration_started_at,
            started_at=started_at,
        )
        yield _sse("phase", {"message": "대화 기록을 저장하고 있습니다."})
        try:
            saved = await asyncio.to_thread(
                repository.save_exchange,
                owner_id=owner_id,
                question=plan.normalized_message,
                response=response,
                session_id=request.session_id,
                idempotency_key=idempotency_key,
            )
        except ChatSessionAccessError:
            yield _sse("error", {"detail": "Chat session not found"})
            return
        except _DATABASE_ERRORS:
            yield _sse("error", {"detail": "Chat database is unavailable"})
            return
        final_response = saved.response or response
        yield _sse("phase", {"message": "답변 검증을 완료했습니다."})
        yield _sse(
            "response",
            {
                "persisted": True,
                "session_id": str(saved.session_id),
                "user_message_id": str(saved.user_message_id),
                "assistant_message_id": str(saved.assistant_message_id),
                "idempotency_replayed": saved.replayed,
                "response": final_response.model_dump(mode="json"),
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
