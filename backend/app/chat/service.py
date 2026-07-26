import logging

from ..engine import (
    AccountType,
    EducationalPortfolioInput,
)
from ..etf_component_repository import EtfComponentSnapshotRepository
from ..etf_distribution_event_repository import PostgresEtfDistributionEventRepository
from ..etf_product_description_repository import (
    EtfProductDescriptionRepository,
)
from ..etf_theme_repository import EtfThemeRepository
from ..etf_theme_verification_repository import (
    EtfThemeVerificationReader,
)
from ..macro_evidence import (
    MacroEvidenceRepository,
)
from ..news_event_outcome_repository import NewsEventOutcomeReader
from ..retrieval.repository import KnowledgeSearch
from .etf_product_features import EtfProductFeatureGenerator
from .handlers._shared import (
    _RISK_PROFILE_RANKS,
    DisclosureSearch,
    LiveNewsSearch,
    NewsSearch,
    PortfolioUniverseLoader,
    ThemeProductUniverseLoader,
    _knowledge_topic,
    _mentioned_retirement_start_age,
    _requests_age_style_portfolio_guide,
    _requests_risk_profile_guide,
    _requests_risk_profile_portfolio_guide,
    _selected_risk_profile,
    is_selected_scenario_diagnosis_request,
)
from .handlers._shared import (
    _knowledge_sources as _knowledge_sources,
)
from .handlers._shared import (  # noqa: F401
    _scenario_holdings_summary as _scenario_holdings_summary,
)
from .handlers.account_rules import blocked_response, handle_account_rule
from .handlers.disclosures_news import (
    disclosure_response,
    event_strategy_response,
    news_follow_up_response,
    news_response,
)
from .handlers.distribution_events import (
    distribution_event_response,
    distribution_reinvestment_response,
)
from .handlers.pension_tax import pension_tax_response
from .handlers.portfolio import (
    age_style_portfolio_guide,
    completed_survey_required,
    custom_portfolio,
    educational_portfolio,
    educational_portfolios,
    etf_theme_response,
    macro_evidence_response,
    retirement_age_selection_guide,
    risk_profile_guardrail,
    risk_profile_portfolio_guide,
    risk_profile_selection_guide,
)
from .handlers.presentation import build_capabilities, finalize_response
from .handlers.scenarios import (
    scenario_code,
    scenario_response,
    scenario_selection_response,
)
from .models import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    MarketRegion,
)
from .query_planner import (
    BlockedReason,
    QueryPlan,
    plan_question,
)
from .routing import IntentRouter, NewsFollowUpAction
from .scenarios import ScenarioRepository

logger = logging.getLogger(__name__)

_EDUCATIONAL_STRATEGY_ACCOUNT_TYPES = (
    AccountType.DC,
    AccountType.PENSION_SAVINGS,
)


class ChatService:
    def __init__(
        self,
        *,
        knowledge: KnowledgeSearch,
        scenarios: ScenarioRepository,
        disclosures: DisclosureSearch | None = None,
        news: NewsSearch | None = None,
        live_news: LiveNewsSearch | None = None,
        portfolio_universe_loader: PortfolioUniverseLoader | None = None,
        theme_product_universe_loader: ThemeProductUniverseLoader | None = None,
        theme_repository: EtfThemeRepository | None = None,
        product_descriptions: EtfProductDescriptionRepository | None = None,
        product_feature_generator: EtfProductFeatureGenerator | None = None,
        component_snapshots: EtfComponentSnapshotRepository | None = None,
        theme_verification: EtfThemeVerificationReader | None = None,
        macro_evidence: MacroEvidenceRepository | None = None,
        distribution_events: PostgresEtfDistributionEventRepository | None = None,
        news_event_outcomes: NewsEventOutcomeReader | None = None,
        router: IntentRouter | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scenarios = scenarios
        self._disclosures = disclosures
        self._news = news
        self._live_news = live_news
        self._portfolio_universe_loader = portfolio_universe_loader
        self._theme_product_universe_loader = theme_product_universe_loader
        self._theme_repository = theme_repository
        self._product_descriptions = product_descriptions
        self._product_feature_generator = product_feature_generator
        self._component_snapshots = component_snapshots
        self._theme_verification = theme_verification
        self._macro_evidence = macro_evidence
        self._distribution_events = distribution_events
        self._news_event_outcomes = news_event_outcomes
        self._router = router or IntentRouter()
        self.capabilities = build_capabilities(scenarios=scenarios)

    def plan(self, request: ChatRequest) -> QueryPlan:
        direct_plan = plan_question(
            request.message,
            default_max_results=request.max_results,
            structured_pension_tax=request.pension_tax is not None,
            theme_repository=self._theme_repository,
        )
        if is_selected_scenario_diagnosis_request(request, direct_plan):
            return QueryPlan(
                normalized_message=direct_plan.normalized_message,
                intent=ChatIntent.MOCK_PORTFOLIO,
                max_results=direct_plan.max_results,
            )
        if direct_plan.blocked_reason not in {None, BlockedReason.UNSUPPORTED}:
            return direct_plan
        can_use_news_context = (
            direct_plan.intent == ChatIntent.NEWS
            or direct_plan.blocked_reason == BlockedReason.UNSUPPORTED
        )
        news_follow_up = (
            self._router.news_follow_up(request) if can_use_news_context else None
        )
        if news_follow_up is not None:
            region = news_follow_up.region
            news_query = (
                "context"
                if news_follow_up.action
                in {
                    NewsFollowUpAction.DETAIL,
                    NewsFollowUpAction.COMPARE,
                    NewsFollowUpAction.SOURCE,
                    NewsFollowUpAction.CLARIFY,
                }
                else "market"
                if region in {None, MarketRegion.ALL}
                else f"market:{region.value}"
            )
            return QueryPlan(
                normalized_message=direct_plan.normalized_message,
                intent=ChatIntent.NEWS,
                news_query=news_query,
                max_results=direct_plan.max_results,
            )
        if direct_plan.blocked_reason != BlockedReason.UNSUPPORTED:
            return direct_plan
        referent = self._router.resolve_referent(request)
        contextual_message = self._router.contextual_message(request)
        if contextual_message == request.message:
            return direct_plan
        contextual_plan = plan_question(
            contextual_message,
            default_max_results=request.max_results,
            structured_pension_tax=request.pension_tax is not None,
            theme_repository=self._theme_repository,
        )
        if (
            contextual_plan.intent == ChatIntent.ACCOUNT_RULE
            and _knowledge_topic(request.message, contextual_plan)[0] == "general"
            and referent is None
        ):
            return direct_plan
        return contextual_plan

    def ask(
        self,
        request: ChatRequest,
        *,
        plan: QueryPlan | None = None,
        prefer_structured_pension_tax: bool = False,
        preferred_news_topics: tuple[str, ...] = (),
    ) -> ChatResponse:
        original_request = request
        resolved_plan = plan or self.plan(request)
        if resolved_plan.blocked_reason is not None and not (
            resolved_plan.blocked_reason == BlockedReason.UNSUPPORTED
            and (
                request.portfolio is not None
                or request.educational_portfolio is not None
                or request.scenario_code is not None
            )
        ):
            response = blocked_response(
                resolved_plan.blocked_reason,
                user_message=request.message,
            )
        else:
            request = request.model_copy(
                update={
                    "message": resolved_plan.normalized_message,
                    "max_results": resolved_plan.max_results,
                }
            )
            if request.portfolio is not None:
                response = custom_portfolio(request)
            elif request.educational_portfolio is not None:
                response = educational_portfolio(
                    request.educational_portfolio,
                    portfolio_universe_loader=self._portfolio_universe_loader,
                    macro_evidence=self._macro_evidence,
                )
            elif resolved_plan.intent == ChatIntent.EDUCATIONAL_PORTFOLIO:
                survey_profile = original_request.survey_profile or (
                    original_request.conversation_context.survey_profile
                    if original_request.conversation_context is not None
                    else None
                )
                retirement_start_age = _mentioned_retirement_start_age(
                    original_request.message
                )
                if retirement_start_age is not None and not (
                    55 <= retirement_start_age <= 60
                ):
                    response = retirement_age_selection_guide()
                elif retirement_start_age is not None and survey_profile is not None:
                    survey_profile = survey_profile.model_copy(
                        update={"retirement_start_age": retirement_start_age}
                    )
                    original_request = original_request.model_copy(
                        update={"survey_profile": survey_profile}
                    )
                if retirement_start_age is not None and not (
                    55 <= retirement_start_age <= 60
                ):
                    pass
                elif _requests_age_style_portfolio_guide(original_request.message):
                    response = age_style_portfolio_guide()
                elif _requests_risk_profile_portfolio_guide(original_request.message):
                    response = risk_profile_portfolio_guide()
                elif _requests_risk_profile_guide(original_request.message):
                    response = risk_profile_selection_guide()
                elif survey_profile is None:
                    response = completed_survey_required()
                else:
                    previous_selection = (
                        original_request.conversation_context.selected_risk_profile
                        if original_request.conversation_context is not None
                        else None
                    )
                    selected_profile = (
                        _selected_risk_profile(original_request.message)
                        or previous_selection
                        or survey_profile.risk_profile
                    )
                    if (
                        _RISK_PROFILE_RANKS[selected_profile]
                        > _RISK_PROFILE_RANKS[survey_profile.risk_profile]
                    ):
                        response = risk_profile_guardrail(
                            assessed_profile=survey_profile.risk_profile,
                            requested_profile=selected_profile,
                        )
                        selected_profile = (
                            previous_selection
                            if previous_selection is not None
                            and _RISK_PROFILE_RANKS[previous_selection]
                            <= _RISK_PROFILE_RANKS[survey_profile.risk_profile]
                            else survey_profile.risk_profile
                        )
                    else:
                        response = educational_portfolios(
                            [
                                EducationalPortfolioInput(
                                    account_type=account_type,
                                    age=survey_profile.current_age,
                                    retirement_start_age=(
                                        survey_profile.retirement_start_age
                                    ),
                                    risk_profile=selected_profile,
                                    loss_tolerance_percent=(
                                        survey_profile.loss_tolerance_percent
                                    ),
                                )
                                for account_type in (
                                    _EDUCATIONAL_STRATEGY_ACCOUNT_TYPES
                                )
                            ],
                            portfolio_universe_loader=(self._portfolio_universe_loader),
                            macro_evidence=self._macro_evidence,
                        )
                    response = response.model_copy(
                        update={
                            "conversation_context": ConversationContext(
                                account_type=survey_profile.account_type,
                                last_intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
                                survey_profile=survey_profile,
                                selected_risk_profile=selected_profile,
                            )
                        }
                    )
            elif resolved_plan.intent == ChatIntent.ETF_THEME:
                response = etf_theme_response(
                    original_request,
                    resolved_plan,
                    portfolio_universe_loader=self._portfolio_universe_loader,
                    theme_product_universe_loader=(self._theme_product_universe_loader),
                    theme_repository=self._theme_repository,
                    product_descriptions=self._product_descriptions,
                    product_feature_generator=self._product_feature_generator,
                    component_snapshots=self._component_snapshots,
                    theme_verification=self._theme_verification,
                )
            elif resolved_plan.intent == ChatIntent.ETF_DISTRIBUTION:
                response = (
                    distribution_reinvestment_response(
                        resolved_plan.distribution_reinvestment,
                        events=self._distribution_events,
                    )
                    if "재투자" in resolved_plan.normalized_message
                    else distribution_event_response(
                        resolved_plan.distribution_isu_code,
                        events=self._distribution_events,
                    )
                )
            elif resolved_plan.intent == ChatIntent.PENSION_TAX:
                response = pension_tax_response(
                    request,
                    resolved_plan,
                    prefer_structured=prefer_structured_pension_tax,
                )
            elif resolved_plan.intent == ChatIntent.MOCK_PORTFOLIO:
                selected_scenario_code = request.scenario_code or scenario_code(
                    request.message
                )
                response = (
                    scenario_response(
                        selected_scenario_code,
                        scenarios=self._scenarios,
                    )
                    if selected_scenario_code is not None
                    else scenario_selection_response(scenarios=self._scenarios)
                )
            elif resolved_plan.intent == ChatIntent.NEWS:
                assert resolved_plan.news_query is not None
                news_follow_up = self._router.news_follow_up(original_request)
                if news_follow_up is not None and news_follow_up.action in {
                    NewsFollowUpAction.DETAIL,
                    NewsFollowUpAction.COMPARE,
                    NewsFollowUpAction.SOURCE,
                    NewsFollowUpAction.CLARIFY,
                }:
                    response = news_follow_up_response(
                        original_request,
                        news_follow_up,
                        news=self._news,
                    )
                else:
                    exclude_item_ids = (
                        tuple(original_request.conversation_context.news.news_item_ids)
                        if news_follow_up is not None
                        and news_follow_up.action == NewsFollowUpAction.REFRESH
                        and original_request.conversation_context is not None
                        and original_request.conversation_context.news is not None
                        else ()
                    )
                    response = (
                        event_strategy_response(
                            original_request,
                            search_query=resolved_plan.news_query,
                            max_results=resolved_plan.max_results,
                            preferred_topics=preferred_news_topics,
                            scope_notice=resolved_plan.news_scope_notice,
                            live_news=self._live_news,
                            news=self._news,
                            theme_repository=self._theme_repository,
                            portfolio_universe_loader=self._portfolio_universe_loader,
                            news_event_outcomes=self._news_event_outcomes,
                        )
                        if resolved_plan.requests_event_strategy
                        else news_response(
                            request,
                            search_query=resolved_plan.news_query,
                            max_results=resolved_plan.max_results,
                            exclude_item_ids=exclude_item_ids,
                            preferred_topics=preferred_news_topics,
                            scope_notice=resolved_plan.news_scope_notice,
                            news=self._news,
                        )
                    )
            elif resolved_plan.intent == ChatIntent.MACRO_EVIDENCE:
                response = macro_evidence_response(
                    request,
                    macro_evidence=self._macro_evidence,
                    portfolio_universe_loader=self._portfolio_universe_loader,
                )
            elif resolved_plan.intent == ChatIntent.PROVIDER_DISCLOSURE:
                account_type = resolved_plan.account_types[0]
                response = disclosure_response(
                    request,
                    account_type,
                    disclosures=self._disclosures,
                )
            elif resolved_plan.intent == ChatIntent.ACCOUNT_RULE:
                response = handle_account_rule(
                    request,
                    resolved_plan,
                    knowledge=self._knowledge,
                )
            else:
                response = blocked_response(
                    BlockedReason.UNSUPPORTED,
                    user_message=request.message,
                )
        return finalize_response(response, original_request, resolved_plan)
