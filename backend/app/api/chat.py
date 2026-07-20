"""Chat endpoints with optional Claude narration and authenticated history."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from time import perf_counter
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from starlette.responses import StreamingResponse

from ..auth import require_supabase_user_id
from ..chat import ChatRequest, ChatResponse, ChatService
from ..chat.cards import ChatCardCatalog, chat_card_catalog
from ..chat.heroes import DemoHeroPortfolio, build_demo_heroes
from ..chat.models import ChatCapabilities, ChatIntent, ScenarioSummary
from ..chat.narrator import NARRATABLE_INTENTS, ClaudeNarrator
from ..chat.query_planner import BlockedReason, QueryPlan
from ..chat.repository import (
    ChatRepository,
    ChatSessionAccessError,
    ChatSessionSummary,
    StoredChatMessage,
    StoredMessageEvidence,
)
from ..chat.scenarios import LocalScenarioRepository
from ..chat.user_context import (
    DemoUserContextRepository,
    DemoUserFinancialContext,
    apply_demo_context_evidence,
)
from .deps import (
    get_chat_narrator,
    get_chat_repository,
    get_chat_service,
    get_demo_user_context_repository,
    get_optional_chat_repository,
    get_optional_demo_user_context_repository,
)

router = APIRouter(tags=["chat"])
logger = logging.getLogger("uvicorn.error")

_DATABASE_ERRORS = (psycopg.Error, ConnectionError)
_SALUTATION_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _format_salutation(nickname: str | None) -> str:
    if nickname is None or _SALUTATION_CONTROL.search(nickname):
        return "고객님"
    normalized = " ".join(nickname.split()).strip()
    if not normalized or len(normalized) > 50:
        return "고객님"
    normalized = re.sub(r"\s+님$", "님", normalized)
    return normalized if normalized.endswith("님") else f"{normalized}님"


def _load_demo_context(
    repository: DemoUserContextRepository | None,
    owner_id: UUID,
) -> DemoUserFinancialContext | None:
    if repository is None:
        return None
    return repository.get(owner_id)


def _load_authenticated_nickname(
    repository: DemoUserContextRepository | None,
    owner_id: UUID,
    context: DemoUserFinancialContext | None,
) -> str | None:
    if context is not None:
        return context.nickname
    if repository is None:
        return None
    return repository.get_nickname(owner_id)


def _restore_session_conversation_context(
    request: "AuthenticatedChatRequest",
    repository: ChatRepository,
    owner_id: UUID,
) -> "AuthenticatedChatRequest":
    if request.session_id is None:
        return request
    context = repository.get_latest_conversation_context(
        owner_id=owner_id,
        session_id=request.session_id,
    )
    return request.model_copy(update={"conversation_context": context})


def _authenticated_request(
    request: "AuthenticatedChatRequest",
    context: DemoUserFinancialContext | None,
) -> ChatRequest:
    payload = request.model_dump(exclude={"session_id"})
    if context is not None:
        survey_profile = context.personalize_survey_profile(request.survey_profile)
        conversation_context = request.conversation_context
        if conversation_context is not None:
            conversation_survey = context.personalize_survey_profile(
                conversation_context.survey_profile
            )
            conversation_context = conversation_context.model_copy(
                update={
                    "account_type": (
                        conversation_survey.account_type
                        if conversation_survey is not None
                        else None
                    ),
                    "survey_profile": conversation_survey,
                    "selected_risk_profile": (
                        conversation_context.selected_risk_profile
                        if conversation_survey is not None
                        else None
                    ),
                }
            )
        payload.update(
            {
                "scenario_code": context.scenario_code,
                "pension_tax": context.to_pension_tax_input(),
                "survey_profile": survey_profile,
                "conversation_context": conversation_context,
            }
        )
    return ChatRequest.model_validate(payload)


def _authenticated_planning_request(
    request: "AuthenticatedChatRequest", chat_request: ChatRequest
) -> ChatRequest:
    if request.pension_tax is not None:
        return chat_request
    return chat_request.model_copy(update={"pension_tax": None})


def _authenticated_response(
    *,
    request: ChatRequest,
    plan: QueryPlan,
    service: ChatService,
    context: DemoUserFinancialContext | None,
    nickname: str | None,
) -> tuple[ChatResponse, bool]:
    direct_context = (
        context is not None
        and context.answers_directly(request.message)
        and plan.intent != ChatIntent.PENSION_TAX
        and plan.blocked_reason in (None, BlockedReason.UNSUPPORTED)
    )
    if direct_context:
        return context.direct_response(), False
    response = (
        service.ask(
            request,
            plan=plan,
            prefer_structured_pension_tax=True,
            preferred_news_topics=context.preferred_news_topics,
        )
        if context is not None
        else service.ask(request, plan=plan)
    )
    if context is not None:
        response = apply_demo_context_evidence(response, context)
    if response.data_mode in {
        "verified_pension_account_overview",
        "verified_pension_account_deferred_topic",
    }:
        response = response.model_copy(
            update={"salutation": _format_salutation(nickname)}
        )
    return response, True


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _answer_delta_events(answer: str) -> list[str]:
    """Send the safety-checked answer in one SSE event.

    The event name remains ``answer_delta`` so existing SSE clients retain the
    same contract. Typing feedback is a presentation concern in the frontend.
    """

    return [_sse("answer_delta", {"delta": answer})]


def _log_stream_latency(
    *,
    intent: ChatIntent,
    answer_started_at: float,
    narration_started_at: float | None,
    first_delta_at: float | None,
    started_at: float,
) -> None:
    finished_at = perf_counter()
    answer_ms = (narration_started_at or finished_at) - answer_started_at
    narration_ms = (
        finished_at - narration_started_at if narration_started_at is not None else 0
    )
    logger.info(
        "chat_stream_latency intent=%s answer_ms=%d narration_ms=%d "
        "ttfa_ms=%d total_ms=%d",
        intent,
        answer_ms * 1000,
        narration_ms * 1000,
        (
            (first_delta_at - started_at) * 1000
            if first_delta_at is not None
            else -1
        ),
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
    stream_before_narration = (
        narrator is not None
        and response.intent in NARRATABLE_INTENTS
        and bool(response.sources)
    )
    first_delta_at = None
    if stream_before_narration:
        first_delta_at = perf_counter()
        for event in _answer_delta_events(response.answer):
            yield event
    if narrator is not None:
        yield _sse("phase", {"message": "검증된 설명을 생성하고 있습니다."})
        narration_started_at = perf_counter()
        response = await asyncio.to_thread(
            narrator.narrate,
            response,
            pension_tax_input=request.pension_tax,
            pension_tax_message=request.message,
        )
        if response.narration_mode == "claude_verified":
            yield _sse("narration_update", {"answer": response.answer})
    else:
        narration_started_at = None
    yield _sse("phase", {"message": "답변 검증을 완료했습니다."})
    if not stream_before_narration:
        first_delta_at = perf_counter()
        for event in _answer_delta_events(response.answer):
            yield event
    _log_stream_latency(
        intent=response.intent,
        answer_started_at=answer_started_at,
        narration_started_at=narration_started_at,
        first_delta_at=first_delta_at,
        started_at=started_at,
    )
    yield _sse("response", {"response": response.model_dump(mode="json")})


class AuthenticatedChatRequest(ChatRequest):
    session_id: UUID | None = None


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


@router.get("/chat/cards", response_model=ChatCardCatalog)
def chat_cards() -> ChatCardCatalog:
    return chat_card_catalog()


@router.get("/chat/demo/scenarios", response_model=list[ScenarioSummary])
def chat_scenarios() -> list[ScenarioSummary]:
    return LocalScenarioRepository().list()


@router.get("/chat/demo/heroes", response_model=list[DemoHeroPortfolio])
def chat_demo_heroes() -> tuple[DemoHeroPortfolio, ...]:
    return build_demo_heroes()


@router.get(
    "/me/pension-context",
    response_model=DemoUserFinancialContext,
)
def get_my_pension_context(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        DemoUserContextRepository, Depends(get_demo_user_context_repository)
    ],
) -> DemoUserFinancialContext:
    try:
        context = repository.get(owner_id)
    except _DATABASE_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User pension context database is unavailable",
        ) from exc
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User pension context was not found",
        )
    return context


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


@router.post("/chat/stream")
async def chat_authenticated_stream(
    request: AuthenticatedChatRequest,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        ChatRepository | None, Depends(get_optional_chat_repository)
    ],
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
    context_repository: Annotated[
        DemoUserContextRepository | None,
        Depends(get_optional_demo_user_context_repository),
    ],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> StreamingResponse:
    """Authenticated variant that persists the final validated response.

    Out-of-scope answers need no database, so the idempotency/persistence
    steps are skipped entirely when there is nothing to save.
    """

    async def events() -> AsyncIterator[str]:
        yield _sse("phase", {"message": "요청을 확인하고 있습니다."})
        if request.session_id is not None and repository is None:
            yield _sse("error", {"detail": "Chat database is not configured"})
            return
        if repository is not None:
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

        request_with_context = request
        if repository is not None and request.session_id is not None:
            try:
                request_with_context = await asyncio.to_thread(
                    _restore_session_conversation_context,
                    request,
                    repository,
                    owner_id,
                )
            except ChatSessionAccessError:
                yield _sse("error", {"detail": "Chat session not found"})
                return
            except _DATABASE_ERRORS:
                yield _sse("error", {"detail": "Chat database is unavailable"})
                return

        try:
            context = await asyncio.to_thread(
                _load_demo_context,
                context_repository,
                owner_id,
            )
            nickname = await asyncio.to_thread(
                _load_authenticated_nickname,
                context_repository,
                owner_id,
                context,
            )
        except _DATABASE_ERRORS:
            context = None
            nickname = None
        chat_request = _authenticated_request(request_with_context, context)
        started_at = perf_counter()
        plan = service.plan(
            _authenticated_planning_request(request_with_context, chat_request)
        )
        yield _sse("phase", {"message": "근거를 검색하고 있습니다."})
        answer_started_at = perf_counter()
        try:
            response, allow_narration = await asyncio.to_thread(
                _authenticated_response,
                request=chat_request,
                plan=plan,
                service=service,
                context=context,
                nickname=nickname,
            )
        except _DATABASE_ERRORS:
            yield _sse("error", {"detail": "Chat data source is unavailable"})
            return
        stream_before_narration = (
            narrator is not None
            and allow_narration
            and response.intent in NARRATABLE_INTENTS
            and bool(response.sources)
        )
        first_delta_at = None
        if stream_before_narration:
            first_delta_at = perf_counter()
            for event in _answer_delta_events(response.answer):
                yield event
        if narrator is not None and allow_narration:
            yield _sse("phase", {"message": "검증된 설명을 생성하고 있습니다."})
            narration_started_at = perf_counter()
            response = await asyncio.to_thread(
                narrator.narrate,
                response,
                pension_tax_input=chat_request.pension_tax,
                pension_tax_message=chat_request.message,
            )
            if response.narration_mode == "claude_verified":
                yield _sse("narration_update", {"answer": response.answer})
        else:
            narration_started_at = None
        if response.intent == ChatIntent.OUT_OF_SCOPE:
            yield _sse("phase", {"message": "답변 검증을 완료했습니다."})
            first_delta_at = perf_counter()
            for event in _answer_delta_events(response.answer):
                yield event
            _log_stream_latency(
                intent=response.intent,
                answer_started_at=answer_started_at,
                narration_started_at=narration_started_at,
                first_delta_at=first_delta_at,
                started_at=started_at,
            )
            yield _sse(
                "response",
                {
                    "persisted": False,
                    "session_id": None,
                    "user_message_id": None,
                    "assistant_message_id": None,
                    "idempotency_replayed": False,
                    "response": response.model_dump(mode="json"),
                },
            )
            return
        if repository is None:
            yield _sse("error", {"detail": "Chat database is not configured"})
            return

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
        if not stream_before_narration:
            first_delta_at = perf_counter()
            for event in _answer_delta_events(final_response.answer):
                yield event
        _log_stream_latency(
            intent=final_response.intent,
            answer_started_at=answer_started_at,
            narration_started_at=narration_started_at,
            first_delta_at=first_delta_at,
            started_at=started_at,
        )
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


@router.delete(
    "/chat/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_chat_session(
    session_id: UUID,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> Response:
    try:
        repository.delete_session(owner_id=owner_id, session_id=session_id)
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
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
