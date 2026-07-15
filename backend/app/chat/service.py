import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from backend.app.engine import (
    PortfolioInput,
    RiskCapEvaluation,
    evaluate_risk_cap,
)
from backend.app.ingestion.knowledge import chunk_markdown
from backend.app.retrieval.disclosures_repository import (
    DisclosureReadRepository,
    PensionSavingsProviderStat,
    RetirementProviderStat,
)
from backend.app.retrieval.repository import (
    KnowledgeMatch,
    NewsMatch,
    RetrievalRepository,
)
from backend.app.retrieval.search_ranking import (
    normalize_korean_search_query,
    rerank_knowledge_matches,
)
from backend.app.settings import Settings, get_settings

from .query_planner import (
    AmbiguousQuestionClassifier,
    DisclosureMetric,
    QueryIntent,
    QueryPlan,
    plan_question,
)

if TYPE_CHECKING:
    from .orchestrator import AnswerRestyler, EvidenceAnswer

_TOKEN = re.compile(r"[0-9A-Za-z가-힣_]+")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LOCAL_DOCUMENTS = (
    Path("docs/20_리서치/연금_기초.md"),
    Path("docs/30_스펙/아키텍처.md"),
)


class DataSourceUnavailableError(RuntimeError):
    """The requested live data source is intentionally unavailable."""


class QueryPlanExecutionError(ValueError):
    """A blocked or incomplete plan cannot be sent to a retrieval tool."""


class KnowledgeSearchRepository(Protocol):
    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]: ...


class NewsSearchRepository(Protocol):
    def latest_news(
        self, search_query: str, *, limit: int = 10
    ) -> list[NewsMatch]: ...


class DisclosureSearchRepository(Protocol):
    def latest_pension_savings_stats(
        self,
        *,
        year: int | None = None,
        quarter: int | None = None,
        provider_name: str | None = None,
        limit: int = 100,
    ) -> list[PensionSavingsProviderStat]: ...

    def latest_retirement_stats(
        self,
        *,
        scheme: str | None = None,
        year: int | None = None,
        quarter: int | None = None,
        provider_name: str | None = None,
        limit: int = 100,
    ) -> list[RetirementProviderStat]: ...


@dataclass(frozen=True, slots=True)
class _LocalChunk:
    chunk_id: int
    document_id: str
    title: str
    source_url: str
    content: str


class LocalMarkdownKnowledgeRepository:
    """Read only the project's verified common documents as an offline fallback."""

    def __init__(
        self,
        *,
        project_root: Path = _PROJECT_ROOT,
        document_paths: tuple[Path, ...] = _DEFAULT_LOCAL_DOCUMENTS,
    ) -> None:
        self._chunks = self._load_chunks(project_root, document_paths)

    @staticmethod
    def _load_chunks(
        project_root: Path, document_paths: tuple[Path, ...]
    ) -> tuple[_LocalChunk, ...]:
        chunks: list[_LocalChunk] = []
        for relative_path in document_paths:
            normalized = relative_path.as_posix().lower()
            if normalized.startswith("data/") or "fixture" in normalized:
                raise ValueError(
                    "fixtures and account data cannot be local RAG sources"
                )
            path = (project_root / relative_path).resolve()
            if not path.is_relative_to(project_root.resolve()):
                raise ValueError("local RAG document must stay inside the project")
            content = path.read_text(encoding="utf-8")
            document_hash = hashlib.sha256(
                relative_path.as_posix().encode()
            ).hexdigest()
            document_id = f"local:{document_hash[:24]}"
            title = next(
                (
                    line.removeprefix("#").strip()
                    for line in content.splitlines()
                    if line.startswith("# ")
                ),
                path.stem,
            )
            source_url = f"project://{relative_path.as_posix()}"
            for index, chunk in enumerate(chunk_markdown(content)):
                chunk_hash = hashlib.sha256(
                    f"{document_id}:{index}".encode()
                ).digest()
                chunks.append(
                    _LocalChunk(
                        chunk_id=int.from_bytes(chunk_hash[:8], "big"),
                        document_id=document_id,
                        title=title,
                        source_url=source_url,
                        content=chunk,
                    )
                )
        return tuple(chunks)

    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]:
        normalized_query = normalize_korean_search_query(query)
        terms = {
            term.casefold()
            for term in _TOKEN.findall(normalized_query)
            if len(term) > 1
        }
        if not terms:
            return []
        matches: list[tuple[float, _LocalChunk]] = []
        for chunk in self._chunks:
            searchable = f"{chunk.title}\n{chunk.content}".casefold()
            matched = sum(searchable.count(term) for term in terms)
            if matched:
                matches.append((float(matched), chunk))
        matches.sort(key=lambda item: (-item[0], item[1].chunk_id))
        results = [
            KnowledgeMatch(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                source_url=chunk.source_url,
                content=chunk.content,
                text_rank=rank,
            )
            for rank, chunk in matches
        ]
        return rerank_knowledge_matches(
            results, normalized_query, limit=max(1, min(limit, 50))
        )


@dataclass(slots=True)
class ChatService:
    knowledge: KnowledgeSearchRepository
    disclosures: DisclosureSearchRepository | None
    news: NewsSearchRepository | None
    backend: Literal["supabase", "local"]
    classifier: AmbiguousQuestionClassifier | None = None

    def plan_question(self, question: str) -> QueryPlan:
        return plan_question(question, classifier=self.classifier)

    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]:
        return self.knowledge.search_knowledge(query, limit=limit)

    def search_disclosures(
        self,
        disclosure_type: Literal["pension_savings", "db", "dc", "irp"],
        *,
        year: int | None = None,
        quarter: int | None = None,
        provider_name: str | None = None,
        limit: int = 100,
    ) -> list[PensionSavingsProviderStat | RetirementProviderStat]:
        if self.disclosures is None:
            raise DataSourceUnavailableError(
                "FSS disclosures require a configured database"
            )
        if disclosure_type == "pension_savings":
            return self.disclosures.latest_pension_savings_stats(
                year=year,
                quarter=quarter,
                provider_name=provider_name,
                limit=limit,
            )
        return self.disclosures.latest_retirement_stats(
            scheme=disclosure_type,
            year=year,
            quarter=quarter,
            provider_name=provider_name,
            limit=limit,
        )

    def latest_news(
        self, search_query: str, *, limit: int = 10
    ) -> list[NewsMatch]:
        if self.news is None:
            raise DataSourceUnavailableError(
                "latest news requires a configured database"
            )
        return self.news.latest_news(search_query, limit=limit)

    @staticmethod
    def evaluate_portfolio(portfolio: PortfolioInput) -> RiskCapEvaluation:
        return evaluate_risk_cap(portfolio)

    def execute_query_plan(
        self,
        plan: QueryPlan,
        *,
        original_question: str,
        portfolio: PortfolioInput | None = None,
    ) -> object:
        if plan.intent == QueryIntent.OUT_OF_SCOPE:
            raise QueryPlanExecutionError(
                f"query is blocked: {plan.blocked_reason or 'out_of_scope'}"
            )
        if plan.intent == QueryIntent.ACCOUNT_RULE:
            return self.search_knowledge(
                original_question, limit=plan.max_results
            )
        if plan.intent == QueryIntent.NEWS:
            return self.latest_news(
                plan.search_query or original_question,
                limit=plan.max_results,
            )
        if plan.intent == QueryIntent.PROVIDER_DISCLOSURE:
            if plan.account_type is None:
                raise QueryPlanExecutionError("disclosure plan has no account_type")
            year = int(plan.period[:4]) if plan.period != "latest" else None
            quarter = int(plan.period[-1]) if plan.period != "latest" else None
            available_metrics = (
                {
                    DisclosureMetric.RESERVE_KRW,
                    DisclosureMetric.EARN_RATE_1Y,
                    DisclosureMetric.AVG_EARN_RATE_3Y,
                    DisclosureMetric.FEE_RATE_1Y,
                }
                if plan.account_type.value == "pension_savings"
                else {
                    DisclosureMetric.RESERVE_KRW,
                    DisclosureMetric.EARN_RATE_CURRENT,
                    DisclosureMetric.AVG_EARN_RATE_3Y,
                    DisclosureMetric.AVG_EARN_RATE_5Y,
                }
            )
            unavailable = set(plan.metrics) - available_metrics
            if unavailable:
                names = ", ".join(sorted(metric.value for metric in unavailable))
                raise QueryPlanExecutionError(
                    f"metrics are not available in the existing read schema: {names}"
                )
            return self.search_disclosures(
                plan.account_type.value,
                year=year,
                quarter=quarter,
                provider_name=plan.provider_name,
                limit=plan.max_results,
            )
        if portfolio is None:
            raise QueryPlanExecutionError("mock_portfolio requires portfolio input")
        if (
            plan.account_type is not None
            and portfolio.account_type != plan.account_type
        ):
            raise QueryPlanExecutionError(
                "plan and portfolio account_type do not match"
            )
        return self.evaluate_portfolio(portfolio)

    def answer_question(
        self,
        question: str,
        *,
        portfolio: PortfolioInput | None = None,
        restyler: "AnswerRestyler | None" = None,
    ) -> "EvidenceAnswer":
        from .orchestrator import orchestrate_answer

        return orchestrate_answer(
            self,
            question,
            portfolio=portfolio,
            restyler=restyler,
        )


def get_chat_service(
    settings: Settings | None = None,
    *,
    classifier: AmbiguousQuestionClassifier | None = None,
) -> ChatService:
    resolved = settings or get_settings()
    database_url = (
        resolved.database_url.get_secret_value().strip()
        if resolved.database_url is not None
        else ""
    )
    if database_url:
        retrieval = RetrievalRepository(database_url)
        return ChatService(
            knowledge=retrieval,
            disclosures=DisclosureReadRepository(database_url),
            news=retrieval,
            backend="supabase",
            classifier=classifier,
        )
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        disclosures=None,
        news=None,
        backend="local",
        classifier=classifier,
    )
