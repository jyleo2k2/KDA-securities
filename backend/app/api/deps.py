"""Shared dependencies for API routers."""

import logging
from functools import lru_cache, partial
from pathlib import Path
from typing import Annotated

from fastapi import Depends, status
from psycopg_pool import ConnectionPool

from ..benchmark_repository import BenchmarkRepository
from ..chat.disclosures import DisclosureReadRepository as ChatDisclosureRepository
from ..chat.etf_product_features import ClaudeEtfProductFeatureGenerator
from ..chat.knowledge import (
    FallbackKnowledgeRepository,
    LocalMarkdownKnowledgeRepository,
)
from ..chat.live_news import NaverLiveNewsSearch
from ..chat.models import ChatRequest
from ..chat.narrator import ClaudeNarrator
from ..chat.repository import ChatRepository
from ..chat.scenarios import LocalScenarioRepository, PostgresScenarioRepository
from ..chat.service import ChatService
from ..chat.suggested_prompts import SUGGESTED_CHAT_PROMPTS
from ..chat.user_context import DemoUserContextRepository
from ..database import get_database_pool
from ..engine.audit import EngineAuditRepository
from ..engine.models import AccountType
from ..etf_component_repository import EtfComponentSnapshotRepository
from ..etf_market_repository import EtfMarketRepository
from ..etf_product_description_repository import (
    get_default_etf_product_description_repository,
)
from ..etf_theme_repository import get_default_etf_theme_repository
from ..etf_theme_verification_repository import (
    PostgresEtfThemeVerificationRepository,
)
from ..etf_universe_database import (
    EtfThemeProductUniverse,
    PostgresPortfolioUniverseRepository,
)
from ..ingestion.embeddings import get_query_embedder
from ..investment_profile_repository import InvestmentProfileRepository
from ..macro_evidence import MacroEvidenceRepository
from ..market_evidence_repository import KrxMarketEvidenceRepository
from ..pension_accounts_repository import PensionAccountRepository
from ..portfolio_universe_repository import (
    DEFAULT_RETURN_ROOT,
    PortfolioUniverseRepository,
)
from ..retrieval.disclosures_repository import DisclosureReadRepository
from ..retrieval.repository import RetrievalRepository
from ..settings import Settings, get_settings
from .errors import ApiErrorCode, api_error

logger = logging.getLogger(__name__)


def _database_url_or_503(settings: Settings, *, detail: str) -> str:
    if settings.database_url is None:
        raise api_error(
            ApiErrorCode.DATABASE_NOT_CONFIGURED,
            detail,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        raise api_error(
            ApiErrorCode.DATABASE_NOT_CONFIGURED,
            detail,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return database_url


def _database_pool(settings: Settings, database_url: str) -> ConnectionPool:
    return get_database_pool(
        database_url,
        max_size=settings.database_pool_max_size,
    )


def get_engine_audit_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EngineAuditRepository:
    database_url = _database_url_or_503(
        settings, detail="Engine audit database is not configured"
    )
    return EngineAuditRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_krx_market_evidence_repository() -> KrxMarketEvidenceRepository:
    try:
        return KrxMarketEvidenceRepository.from_latest_cache()
    except (FileNotFoundError, ValueError) as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Current KRX market evidence is not available",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@lru_cache(maxsize=6)
def get_portfolio_universe_repository(
    account_type: AccountType,
    database_url: str = "",
    database_pool_max_size: int = 5,
) -> PortfolioUniverseRepository:
    if database_url:
        return PostgresPortfolioUniverseRepository(
            database_url,
            pool=get_database_pool(database_url, max_size=database_pool_max_size),
        ).latest(account_type)
    return PortfolioUniverseRepository.from_latest_cache(account_type)


@lru_cache(maxsize=64)
def get_etf_theme_product_universe(
    isu_codes: tuple[str, ...] | None,
    database_url: str,
    database_pool_max_size: int = 5,
) -> EtfThemeProductUniverse:
    return PostgresPortfolioUniverseRepository(
        database_url,
        pool=get_database_pool(database_url, max_size=database_pool_max_size),
    ).latest_theme_products(isu_codes)


def portfolio_return_master_readiness(
    return_root: Path = DEFAULT_RETURN_ROOT,
) -> dict[AccountType, bool]:
    return {
        account_type: bool(
            list(return_root.glob(f"{account_type.value}_etf_cost_return_*.json"))
        )
        for account_type in AccountType
    }


def get_retrieval_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalRepository:
    database_url = _database_url_or_503(settings, detail="Database is not configured")
    return RetrievalRepository(
        database_url,
        embedder=get_query_embedder(),
        pool=_database_pool(settings, database_url),
    )


def get_disclosures_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DisclosureReadRepository:
    database_url = _database_url_or_503(settings, detail="Database is not configured")
    return DisclosureReadRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_benchmark_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BenchmarkRepository:
    database_url = _database_url_or_503(
        settings, detail="Benchmark database is not configured"
    )
    return BenchmarkRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_etf_market_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EtfMarketRepository:
    database_url = _database_url_or_503(
        settings, detail="KRX ETF market database is not configured"
    )
    return EtfMarketRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_chat_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatRepository:
    database_url = _database_url_or_503(
        settings, detail="Chat database is not configured"
    )
    return ChatRepository(database_url, pool=_database_pool(settings, database_url))


def get_optional_chat_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatRepository | None:
    if settings.database_url is None:
        return None
    database_url = settings.database_url.get_secret_value().strip()
    return (
        ChatRepository(database_url, pool=_database_pool(settings, database_url))
        if database_url
        else None
    )


def get_demo_user_context_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoUserContextRepository:
    database_url = _database_url_or_503(
        settings, detail="User pension context database is not configured"
    )
    return DemoUserContextRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_pension_account_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PensionAccountRepository:
    database_url = _database_url_or_503(
        settings, detail="User pension accounts database is not configured"
    )
    return PensionAccountRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_investment_profile_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvestmentProfileRepository:
    database_url = _database_url_or_503(
        settings, detail="Investment profile database is not configured"
    )
    return InvestmentProfileRepository(
        database_url,
        pool=_database_pool(settings, database_url),
    )


def get_optional_investment_profile_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvestmentProfileRepository | None:
    if settings.database_url is None:
        return None
    database_url = settings.database_url.get_secret_value().strip()
    return (
        InvestmentProfileRepository(
            database_url,
            pool=_database_pool(settings, database_url),
        )
        if database_url
        else None
    )


def get_optional_demo_user_context_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoUserContextRepository | None:
    if settings.database_url is None:
        return None
    database_url = settings.database_url.get_secret_value().strip()
    return (
        DemoUserContextRepository(
            database_url,
            pool=_database_pool(settings, database_url),
        )
        if database_url
        else None
    )


def get_macro_evidence_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MacroEvidenceRepository:
    return MacroEvidenceRepository(settings.macro_evidence_report_path)


@lru_cache(maxsize=4)
def _chat_service(
    database_url: str,
    macro_evidence_report_path: str,
    database_pool_max_size: int,
    naver_client_id: str = "",
    naver_client_secret: str = "",
    anthropic_api_key: str = "",
    anthropic_model: str = "",
) -> ChatService:
    pool: ConnectionPool | None = (
        get_database_pool(database_url, max_size=database_pool_max_size)
        if database_url
        else None
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
    disclosures = (
        ChatDisclosureRepository(database_url, pool=pool) if database_url else None
    )
    local_knowledge = LocalMarkdownKnowledgeRepository()
    knowledge = (
        FallbackKnowledgeRepository(retrieval, local_knowledge)
        if retrieval is not None
        else local_knowledge
    )
    return ChatService(
        knowledge=knowledge,
        scenarios=(
            PostgresScenarioRepository(database_url, pool=pool)
            if database_url
            else LocalScenarioRepository()
        ),
        disclosures=disclosures,
        news=retrieval,
        live_news=(
            NaverLiveNewsSearch(
                client_id=naver_client_id,
                client_secret=naver_client_secret,
            )
            if naver_client_id and naver_client_secret
            else None
        ),
        portfolio_universe_loader=partial(
            get_portfolio_universe_repository,
            database_url=database_url,
            database_pool_max_size=database_pool_max_size,
        ),
        theme_product_universe_loader=(
            partial(
                get_etf_theme_product_universe,
                database_url=database_url,
                database_pool_max_size=database_pool_max_size,
            )
            if database_url
            else None
        ),
        theme_repository=get_default_etf_theme_repository(),
        product_descriptions=get_default_etf_product_description_repository(),
        product_feature_generator=(
            ClaudeEtfProductFeatureGenerator(
                api_key=anthropic_api_key,
                model=anthropic_model,
            )
            if anthropic_api_key and anthropic_model
            else None
        ),
        component_snapshots=(
            EtfComponentSnapshotRepository(database_url, pool=pool)
            if database_url
            else None
        ),
        theme_verification=(
            PostgresEtfThemeVerificationRepository(database_url, pool=pool)
            if database_url
            else None
        ),
        macro_evidence=MacroEvidenceRepository(Path(macro_evidence_report_path)),
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
    naver_client_id = (
        settings.naver_api_hub_client_id.get_secret_value().strip()
        if settings.naver_api_hub_client_id is not None
        else ""
    )
    naver_client_secret = (
        settings.naver_api_hub_client_secret.get_secret_value().strip()
        if settings.naver_api_hub_client_secret is not None
        else ""
    )
    anthropic_api_key = (
        settings.anthropic_api_key.get_secret_value().strip()
        if settings.enable_etf_product_feature_generation
        and settings.anthropic_api_key is not None
        else ""
    )
    return _chat_service(
        database_url,
        str(settings.macro_evidence_report_path),
        settings.database_pool_max_size,
        naver_client_id,
        naver_client_secret,
        anthropic_api_key,
        settings.anthropic_model,
    )


@lru_cache(maxsize=1)
def _chat_narrator(
    api_key: str,
    model: str,
    cache_path: Path,
) -> ClaudeNarrator:
    return ClaudeNarrator(
        api_key=api_key,
        model=model,
        cache_path=cache_path,
    )


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
    return _chat_narrator(
        api_key,
        settings.anthropic_model,
        settings.narration_cache_path,
    )


def precompute_chat_narrations(settings: Settings) -> None:
    """Warm fixed demo questions without touching the request narrator agent."""

    try:
        narrator = get_chat_narrator(settings)
        if narrator is None:
            return
        service = get_chat_service(settings)
        scenarios = LocalScenarioRepository().list()
    except Exception:  # noqa: BLE001 — 부팅 워밍 실패는 요청과 격리
        logger.warning("narration_precompute_failed")
        return
    responses = []
    for scenario in scenarios:
        for prompt in SUGGESTED_CHAT_PROMPTS:
            try:
                responses.append(
                    service.ask(
                        ChatRequest(
                            message=prompt,
                            scenario_code=scenario.code,
                        )
                    )
                )
            except Exception:  # noqa: BLE001 — 개별 워밍 실패는 요청과 격리
                logger.warning(
                    "narration_precompute_answer_failed scenario=%s",
                    scenario.code,
                )
    try:
        narrator.precompute(responses)
    except Exception:  # noqa: BLE001 — 부팅 워밍 실패는 요청과 격리
        logger.warning("narration_precompute_failed")


def warm_chat_dependencies(settings: Settings) -> None:
    """Preload guide-page vectors and warm the narrator before requests."""

    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    if not database_url:
        readiness = portfolio_return_master_readiness()
        missing_accounts = [
            account_type.value
            for account_type, is_ready in readiness.items()
            if not is_ready
        ]
        if missing_accounts:
            logger.warning(
                "ETF return masters are unavailable for accounts: %s",
                ", ".join(missing_accounts),
            )

    embedder = get_query_embedder()
    if embedder is not None:
        embedder.prewarm_queries(SUGGESTED_CHAT_PROMPTS)
    narrator = get_chat_narrator(settings)
    if narrator is not None:
        narrator.prewarm()


def clear_chat_dependencies() -> None:
    _chat_service.cache_clear()
    _chat_narrator.cache_clear()
    get_portfolio_universe_repository.cache_clear()
    get_etf_theme_product_universe.cache_clear()
