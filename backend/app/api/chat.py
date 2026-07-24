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
from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, ConfigDict
from starlette.responses import StreamingResponse

from ..auth import require_supabase_user_id
from ..chat import ChatRequest, ChatResponse, ChatService
from ..chat._debug_log import log_chat_exchange  # 로컬 디버깅 전용 임시물(삭제 예정)
from ..chat.cards import ChatCardCatalog, chat_card_catalog
from ..chat.heroes import DemoHeroPortfolio, build_demo_heroes
from ..chat.models import (
    ChatCapabilities,
    ChatIntent,
    CompletedSurveyProfile,
    ScenarioSummary,
)
from ..chat.narrator import NARRATABLE_INTENTS, ClaudeNarrator
from ..chat.query_planner import (
    BlockedReason,
    QueryPlan,
    is_missed_tax_credit_question,
)
from ..chat.repository import (
    ChatRepository,
    ChatSessionAccessError,
    ChatSessionSummary,
    StoredChatMessage,
    StoredMessageEvidence,
)
from ..chat.scenarios import LocalScenarioRepository
from ..chat.tools import PENSION_TAX_CLOSING_NOTICE
from ..chat.topic_guard import ClaudeTopicGuard
from ..chat.user_context import (
    DemoUserContextRepository,
    DemoUserFinancialContext,
    apply_demo_context_evidence,
)
from ..engine import AccountType, ProfileSurveyInput, SurveyAnswer, evaluate_profile
from ..investment_profile_policy import assessment_validity
from ..investment_profile_repository import (
    InvestmentProfileRepository,
    StoredInvestmentProfile,
)
from .deps import (
    get_chat_narrator,
    get_chat_repository,
    get_chat_service,
    get_chat_topic_guard,
    get_demo_user_context_repository,
    get_optional_chat_repository,
    get_optional_demo_user_context_repository,
    get_optional_investment_profile_repository,
)
from .errors import ApiErrorCode, api_error

router = APIRouter(tags=["chat"])
logger = logging.getLogger("uvicorn.error")

_DATABASE_ERRORS = (psycopg.Error, ConnectionError)
_SALUTATION_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LEGACY_ETF_THEME_DRAFT_NOTICE = (
    "테마 설명은 사용자가 제공한 조사 내용을 서비스 분류체계로 정리한 것으로 "
    "공식 문서 검증 전 초안입니다."
)


def _without_legacy_etf_theme_draft_notice(response: ChatResponse) -> ChatResponse:
    """Keep a retired draft notice out of live and stored ETF-theme replies."""

    if response.intent != ChatIntent.ETF_THEME:
        return response
    limitations = [
        limitation
        for limitation in response.limitations
        if limitation != _LEGACY_ETF_THEME_DRAFT_NOTICE
    ]
    if len(limitations) == len(response.limitations):
        return response
    return response.model_copy(update={"limitations": limitations})


def _format_salutation(nickname: str | None) -> str:
    if nickname is None or _SALUTATION_CONTROL.search(nickname):
        return "고객님"
    normalized = re.sub(r"\(가상\)", "", " ".join(nickname.split())).strip()
    if not normalized or len(normalized) > 50:
        return "고객님"
    normalized = re.sub(r"\s+님$", "님", normalized)
    return normalized if normalized.endswith("님") else f"{normalized}님"


def _personalized_pension_tax_answer(nickname: str | None) -> str:
    customer = _format_salutation(nickname)
    return (
        f"{customer}의 올해 연금세액공제 혜택을 정리했어요.\n"
        "돌려받을 세금은 이렇게 계산했어요.\n"
        f"실제 환급액은 {customer}의 소득세 결정세액 등에 따라 달라질 수 있어요.\n"
        f"{PENSION_TAX_CLOSING_NOTICE}"
    )


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


def _load_saved_survey_profile(
    repository: InvestmentProfileRepository | None,
    owner_id: UUID,
    context: DemoUserFinancialContext | None,
) -> CompletedSurveyProfile | None:
    """Build the ETF-engine input from the owner's latest persisted assessment."""
    if repository is None or context is None:
        return None
    stored: StoredInvestmentProfile | None = repository.get_latest(owner_id)
    if stored is None or assessment_validity(stored.assessment.assessed_at).is_expired:
        return None
    if (
        stored.preferences is None
        or not stored.preferences.investor_information_provided
    ):
        return None
    if not 20 <= context.representative_age <= 54:
        return None
    grouped: dict[str, list[str]] = {}
    for answer in stored.assessment.answers:
        grouped.setdefault(answer.question_code, []).append(answer.selected_value)
    try:
        survey = ProfileSurveyInput(
            answers=[
                SurveyAnswer(question_code=question_code, selected_values=values)
                for question_code, values in grouped.items()
            ]
        )
        retirement_start_age = int(grouped["retirement_start_age"][0])
        evaluation = evaluate_profile(survey)
        return CompletedSurveyProfile(
            account_type=AccountType.IRP,
            current_age=context.representative_age,
            retirement_start_age=retirement_start_age,
            risk_profile=evaluation.risk_profile,
            loss_tolerance_percent=evaluation.loss_tolerance_percent,
        )
    except (KeyError, ValueError):
        logger.warning(
            "Stored investment profile could not be converted to a chat survey profile"
        )
        return None


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
    saved_survey_profile: CompletedSurveyProfile | None = None,
    *,
    use_saved_survey_profile: bool = False,
) -> ChatRequest:
    payload = request.model_dump(exclude={"session_id"})
    if context is not None:
        candidate_survey = (
            saved_survey_profile if use_saved_survey_profile else request.survey_profile
        )
        survey_profile = context.personalize_survey_profile(candidate_survey)
        conversation_context = request.conversation_context
        if conversation_context is not None:
            conversation_profile = (
                saved_survey_profile
                if use_saved_survey_profile
                else conversation_context.survey_profile
            )
            conversation_survey = context.personalize_survey_profile(
                conversation_profile
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
    if (
        response.intent == ChatIntent.PENSION_TAX
        and response.pension_tax_result is not None
        and response.pension_tax_result.tax_credit is not None
    ):
        missed_tax_credit = is_missed_tax_credit_question(request.message)
        response = response.model_copy(
            update=(
                {
                    "answer": response.answer.replace(
                        "고객님", _format_salutation(nickname)
                    ),
                    "data_mode": "missed_pension_tax_credit_engine",
                }
                if missed_tax_credit
                else {"answer": _personalized_pension_tax_answer(nickname)}
            )
        )
    if response.data_mode in {
        "verified_pension_account_overview",
        "verified_pension_account_deferred_topic",
    }:
        response = response.model_copy(
            update={"salutation": _format_salutation(nickname)}
        )
    response = _without_legacy_etf_theme_draft_notice(response)
    return response, response.intent not in {
        ChatIntent.OUT_OF_SCOPE,
        ChatIntent.PENSION_TAX,
    }


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_error(code: ApiErrorCode, message: str) -> str:
    return _sse("error", {"code": code, "message": message})


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
        "chat_stream_latency intent=%s preparation_ms=%d answer_ms=%d narration_ms=%d "
        "ttfa_ms=%d total_ms=%d",
        intent,
        (answer_started_at - started_at) * 1000,
        answer_ms * 1000,
        narration_ms * 1000,
        ((first_delta_at - started_at) * 1000 if first_delta_at is not None else -1),
        (finished_at - started_at) * 1000,
    )


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


@router.get("/chat/capabilities", response_model=ChatCapabilities)
def chat_capabilities(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatCapabilities:
    return service.capabilities


@router.get("/chat/cards", response_model=ChatCardCatalog)
def chat_cards() -> ChatCardCatalog:
    return chat_card_catalog()


@router.get("/chat/scenarios", response_model=list[ScenarioSummary])
def chat_scenarios(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
) -> list[ScenarioSummary]:
    return LocalScenarioRepository().list()


@router.get("/chat/heroes", response_model=list[DemoHeroPortfolio])
def chat_heroes(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
) -> tuple[DemoHeroPortfolio, ...]:
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
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "User pension context database is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if context is None:
        raise api_error(
            ApiErrorCode.RESOURCE_NOT_FOUND,
            "User pension context was not found",
            status.HTTP_404_NOT_FOUND,
        )
    return context


@router.post("/chat/stream")
async def chat_authenticated_stream(
    request: AuthenticatedChatRequest,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository | None, Depends(get_optional_chat_repository)],
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
    topic_guard: Annotated[ClaudeTopicGuard | None, Depends(get_chat_topic_guard)],
    context_repository: Annotated[
        DemoUserContextRepository | None,
        Depends(get_optional_demo_user_context_repository),
    ],
    investment_profile_repository: Annotated[
        InvestmentProfileRepository | None,
        Depends(get_optional_investment_profile_repository),
    ],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> StreamingResponse:
    """Authenticated variant that persists the final validated response.

    Out-of-scope answers need no database, so the idempotency/persistence
    steps are skipped entirely when there is nothing to save.
    """

    async def events() -> AsyncIterator[str]:
        yield _sse("phase", {"message": "질문을 살펴보고 있어요."})
        if request.session_id is not None and repository is None:
            yield _sse_error(
                ApiErrorCode.DATABASE_NOT_CONFIGURED,
                "Chat database is not configured",
            )
            return
        if repository is not None:
            try:
                replayed = await asyncio.to_thread(
                    repository.find_idempotent_exchange,
                    owner_id=owner_id,
                    idempotency_key=idempotency_key,
                )
            except _DATABASE_ERRORS:
                yield _sse_error(
                    ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                    "Chat database is unavailable",
                )
                return
            except RuntimeError:
                logger.exception("Chat replay contained an invalid stored response")
                yield _sse_error(
                    ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                    "Chat database is unavailable",
                )
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
            session_result, context_result = await asyncio.gather(
                asyncio.to_thread(
                    _restore_session_conversation_context,
                    request,
                    repository,
                    owner_id,
                ),
                asyncio.to_thread(
                    _load_demo_context,
                    context_repository,
                    owner_id,
                ),
                return_exceptions=True,
            )
            if isinstance(session_result, ChatSessionAccessError):
                yield _sse_error(
                    ApiErrorCode.SESSION_NOT_FOUND,
                    "Chat session not found",
                )
                return
            if isinstance(session_result, _DATABASE_ERRORS):
                yield _sse_error(
                    ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                    "Chat database is unavailable",
                )
                return
            if isinstance(session_result, BaseException):
                raise session_result
            request_with_context = session_result
            if isinstance(context_result, _DATABASE_ERRORS):
                context = None
            elif isinstance(context_result, BaseException):
                raise context_result
            else:
                context = context_result
        else:
            try:
                context = await asyncio.to_thread(
                    _load_demo_context,
                    context_repository,
                    owner_id,
                )
            except _DATABASE_ERRORS:
                context = None
        # Context 이후 독립적인 사용자 정보를 병렬로 읽습니다.
        nickname_result, survey_result = await asyncio.gather(
            asyncio.to_thread(
                _load_authenticated_nickname,
                context_repository,
                owner_id,
                context,
            ),
            asyncio.to_thread(
                _load_saved_survey_profile,
                investment_profile_repository,
                owner_id,
                context,
            ),
            return_exceptions=True,
        )
        if isinstance(nickname_result, _DATABASE_ERRORS):
            nickname = None
        elif isinstance(nickname_result, BaseException):
            raise nickname_result
        else:
            nickname = nickname_result
        if isinstance(survey_result, _DATABASE_ERRORS):
            saved_survey_profile = None
        elif isinstance(survey_result, BaseException):
            raise survey_result
        else:
            saved_survey_profile = survey_result
        chat_request = _authenticated_request(
            request_with_context,
            context,
            saved_survey_profile,
            use_saved_survey_profile=investment_profile_repository is not None,
        )
        started_at = perf_counter()
        planning_request = _authenticated_planning_request(
            request_with_context,
            chat_request,
        )
        plan = service.plan(planning_request)
        if topic_guard is not None and plan.blocked_reason is BlockedReason.UNSUPPORTED:
            yield _sse("phase", {"message": "알맞은 안내를 준비하고 있어요."})
            plan = await asyncio.to_thread(
                topic_guard.refine_plan,
                planning_request.message,
                plan,
            )
        yield _sse("phase", {"message": "필요한 정보를 확인하고 있어요."})
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
            yield _sse_error(
                ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                "Chat data source is unavailable",
            )
            return
        except RuntimeError:
            logger.exception("Chat stream received an invalid stored response")
            yield _sse_error(
                ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                "Chat data source is unavailable",
            )
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
            yield _sse("phase", {"message": "이해하기 쉽게 정리하고 있어요."})
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
            yield _sse("phase", {"message": "답변을 정리했어요."})
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
            log_chat_exchange(  # 로컬 디버깅 전용 임시물(삭제 예정)
                message=chat_request.message,
                response=response,
                latency_ms=(perf_counter() - started_at) * 1000,
                persisted=False,
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
            yield _sse_error(
                ApiErrorCode.DATABASE_NOT_CONFIGURED,
                "Chat database is not configured",
            )
            return

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
            yield _sse_error(ApiErrorCode.SESSION_NOT_FOUND, "Chat session not found")
            return
        except _DATABASE_ERRORS:
            yield _sse_error(
                ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                "Chat database is unavailable",
            )
            return
        except RuntimeError:
            logger.exception("Chat save produced an invalid stored response")
            yield _sse_error(
                ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
                "Chat database is unavailable",
            )
            return
        final_response = saved.response or response
        yield _sse("phase", {"message": "답변을 정리했어요."})
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
        log_chat_exchange(  # 로컬 디버깅 전용 임시물(삭제 예정)
            message=chat_request.message,
            response=final_response,
            latency_ms=(perf_counter() - started_at) * 1000,
            persisted=True,
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
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Chat database is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return [ChatSessionOut.model_validate(session) for session in sessions]


@router.delete("/chat/sessions", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_chat_sessions(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> Response:
    """Delete all stored conversations owned by the authenticated user."""

    try:
        repository.delete_all_sessions(owner_id=owner_id)
    except _DATABASE_ERRORS as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Chat database is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        raise api_error(
            ApiErrorCode.SESSION_NOT_FOUND,
            "Chat session not found",
            status.HTTP_404_NOT_FOUND,
        ) from exc
    except _DATABASE_ERRORS as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Chat database is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
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
        messages = repository.get_messages(owner_id=owner_id, session_id=session_id)
    except ChatSessionAccessError as exc:
        raise api_error(
            ApiErrorCode.SESSION_NOT_FOUND,
            "Chat session not found",
            status.HTTP_404_NOT_FOUND,
        ) from exc
    except _DATABASE_ERRORS as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Chat database is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
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
                response = _without_legacy_etf_theme_draft_notice(response)
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
