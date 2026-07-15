"""Shared dependencies for API routers (503 when the database is absent)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from ..chat.disclosures import DisclosureReadRepository as ChatDisclosureRepository
from ..chat.knowledge import LocalMarkdownKnowledgeRepository
from ..chat.narrator import ClaudeNarrator
from ..chat.scenarios import LocalScenarioRepository
from ..chat.service import ChatService
from ..engine.audit import EngineAuditRepository
from ..retrieval.disclosures_repository import DisclosureReadRepository
from ..retrieval.repository import RetrievalRepository
from ..settings import Settings, get_settings


def _database_url_or_503(settings: Settings, *, detail: str) -> str:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
    return database_url


def get_engine_audit_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EngineAuditRepository:
    return EngineAuditRepository(
        _database_url_or_503(
            settings, detail="Engine audit database is not configured"
        )
    )


def get_retrieval_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalRepository:
    return RetrievalRepository(
        _database_url_or_503(settings, detail="Database is not configured")
    )


def get_disclosures_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DisclosureReadRepository:
    return DisclosureReadRepository(
        _database_url_or_503(settings, detail="Database is not configured")
    )


def get_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatService:
    # 챗봇은 DB가 없어도 로컬 문서·시나리오로 동작한다(503 대신 조건부 축소).
    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    retrieval = RetrievalRepository(database_url) if database_url else None
    disclosures = ChatDisclosureRepository(database_url) if database_url else None
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        disclosures=disclosures,
        news=retrieval,
    )


def get_chat_narrator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClaudeNarrator | None:
    if settings.anthropic_api_key is None:
        return None
    api_key = settings.anthropic_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return ClaudeNarrator(api_key=api_key, model=settings.anthropic_model)
