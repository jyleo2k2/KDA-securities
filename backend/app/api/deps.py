"""Shared dependencies for API routers."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from psycopg_pool import ConnectionPool

from ..benchmark_repository import BenchmarkRepository
from ..chat.disclosures import DisclosureReadRepository as ChatDisclosureRepository
from ..chat.knowledge import (
    FallbackKnowledgeRepository,
    LocalMarkdownKnowledgeRepository,
)
from ..chat.narrator import ClaudeNarrator
from ..chat.repository import ChatRepository
from ..chat.scenarios import LocalScenarioRepository
from ..chat.service import ChatService
from ..chat.suggested_prompts import SUGGESTED_CHAT_PROMPTS
from ..database import get_database_pool
from ..engine.audit import EngineAuditRepository
from ..engine.models import AccountType
from ..ingestion.embeddings import get_query_embedder
from ..market_evidence_repository import KrxMarketEvidenceRepository
from ..portfolio_universe_repository import PortfolioUniverseRepository
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


def get_krx_market_evidence_repository() -> KrxMarketEvidenceRepository:
    try:
        return KrxMarketEvidenceRepository.from_latest_cache()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Current KRX market evidence is not available",
        ) from exc


@lru_cache(maxsize=3)
def get_portfolio_universe_repository(
    account_type: AccountType,
) -> PortfolioUniverseRepository:
    return PortfolioUniverseRepository.from_latest_cache(account_type)


def get_retrieval_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalRepository:
    database_url = _database_url_or_503(
        settings, detail="Database is not configured"
    )
    return RetrievalRepository(
        database_url,
        embedder=get_query_embedder(),
        pool=get_database_pool(database_url),
    )


def get_disclosures_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DisclosureReadRepository:
    return DisclosureReadRepository(
        _database_url_or_503(settings, detail="Database is not configured")
    )


def get_benchmark_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BenchmarkRepository:
    database_url = _database_url_or_503(
        settings, detail="Benchmark database is not configured"
    )
    return BenchmarkRepository(database_url, pool=get_database_pool(database_url))


def get_chat_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatRepository:
    database_url = _database_url_or_503(
        settings, detail="Chat database is not configured"
    )
    return ChatRepository(database_url, pool=get_database_pool(database_url))


def get_optional_chat_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatRepository | None:
    if settings.database_url is None:
        return None
    database_url = settings.database_url.get_secret_value().strip()
    return (
        ChatRepository(database_url, pool=get_database_pool(database_url))
        if database_url
        else None
    )


@lru_cache(maxsize=1)
def _chat_service(database_url: str) -> ChatService:
    pool: ConnectionPool | None = (
        get_database_pool(database_url) if database_url else None
    )
    retrieval = (
        RetrievalRepository(
            database_url,
            embedder=get_query_embedder(),
            pool=pool,
        )
        if database_url
        else None
    )
    disclosures = ChatDisclosureRepository(database_url) if database_url else None
    local_knowledge = LocalMarkdownKnowledgeRepository()
    knowledge = (
        FallbackKnowledgeRepository(retrieval, local_knowledge)
        if retrieval is not None
        else local_knowledge
    )
    return ChatService(
        knowledge=knowledge,
        scenarios=LocalScenarioRepository(),
        disclosures=disclosures,
        news=retrieval,
        portfolio_universe_loader=get_portfolio_universe_repository,
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
    return _chat_service(database_url)


@lru_cache(maxsize=1)
def _chat_narrator(api_key: str, model: str) -> ClaudeNarrator:
    return ClaudeNarrator(api_key=api_key, model=model)


def get_chat_narrator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClaudeNarrator | None:
    if not settings.enable_claude_narration:
        return None
    if settings.anthropic_api_key is None:
        return None
    api_key = settings.anthropic_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return _chat_narrator(api_key, settings.anthropic_model)


def warm_chat_dependencies(settings: Settings) -> None:
    """Preload the fixed guide-page vectors before the API accepts requests."""

    embedder = get_query_embedder()
    if embedder is not None:
        embedder.prewarm_queries(SUGGESTED_CHAT_PROMPTS)


def clear_chat_dependencies() -> None:
    _chat_service.cache_clear()
    _chat_narrator.cache_clear()
