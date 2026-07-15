"""Chat MVP endpoints (chatbot-mvp 브랜치의 main.py 인라인 구현을 라우터로 이식).

Deterministic verified answers from ChatService; the optional Claude narrator
only rephrases and is rejected if it invents a new number.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..chat import ChatRequest, ChatResponse, ChatService
from ..chat.models import ChatCapabilities, ScenarioSummary
from ..chat.narrator import ClaudeNarrator
from ..chat.scenarios import LocalScenarioRepository
from .deps import get_chat_narrator, get_chat_service

router = APIRouter(tags=["chat"])


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
    """Unauthenticated MVP using mock accounts and read-only verified evidence."""

    response = service.ask(request)
    return narrator.narrate(response) if narrator is not None else response
