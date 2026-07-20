import logging
from datetime import UTC, datetime

from ..engine import (
    AccountType,
    EducationalPortfolioInput,
    EducationalRiskProfile,
)
from ..etf_theme_repository import EtfThemeRepository
from ..etf_theme_verification_repository import (
    EtfThemeVerificationReader,
)
from ..macro_evidence import (
    MacroEvidenceRepository,
)
from ..retrieval.repository import KnowledgeSearch
from .handlers._shared import (
    _RISK_PROFILE_RANKS,
    _SELECTED_SCENARIO_DIAGNOSIS_TERMS,
    DisclosureSearch,
    LiveNewsSearch,
    NewsSearch,
    PortfolioUniverseLoader,
    _decimal_text,
    _knowledge_topic,
    _mentioned_retirement_start_age,
    _news_comparison_block,
    _news_metadata_line,
    _news_summary_block,
    _requests_age_style_portfolio_guide,
    _requests_risk_profile_guide,
    _requests_risk_profile_portfolio_guide,
    _selected_risk_profile,
    _source_ids,
)
from .handlers._shared import (
    _knowledge_sources as _knowledge_sources,
)
from .handlers._shared import (  # noqa: F401
    _scenario_holdings_summary as _scenario_holdings_summary,
)
from .handlers.account_rules import blocked_response, handle_account_rule
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
from .live_news import (
    LiveMarketNewsSnapshot,
    LiveNewsUnavailable,
)
from .models import (
    AnswerBlock,
    AnswerBlockKind,
    AnswerSection,
    ChatIntent,
    ChatNewsItem,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    DataBoundary,
    MarketRegion,
    NewsConversationContext,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from .news_event_strategy import (
    NEWS_EVENT_POLICY_AS_OF,
    NEWS_EVENT_POLICY_VERSION,
    classify_news_event,
)
from .query_planner import (
    BlockedReason,
    QueryPlan,
    plan_question,
)
from .routing import IntentRouter, NewsFollowUp, NewsFollowUpAction
from .scenarios import ScenarioRepository

logger = logging.getLogger(__name__)


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
        theme_repository: EtfThemeRepository | None = None,
        theme_verification: EtfThemeVerificationReader | None = None,
        macro_evidence: MacroEvidenceRepository | None = None,
        router: IntentRouter | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scenarios = scenarios
        self._disclosures = disclosures
        self._news = news
        self._live_news = live_news
        self._portfolio_universe_loader = portfolio_universe_loader
        self._theme_repository = theme_repository
        self._theme_verification = theme_verification
        self._macro_evidence = macro_evidence
        self._router = router or IntentRouter()
        self.capabilities = build_capabilities(scenarios=scenarios)

    def plan(self, request: ChatRequest) -> QueryPlan:
        direct_plan = plan_question(
            request.message,
            default_max_results=request.max_results,
            structured_pension_tax=request.pension_tax is not None,
            theme_repository=self._theme_repository,
        )
        if self._is_selected_scenario_diagnosis_request(request, direct_plan):
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
        ):
            return direct_plan
        return contextual_plan

    @staticmethod
    def _is_selected_scenario_diagnosis_request(
        request: ChatRequest, plan: QueryPlan
    ) -> bool:
        return (
            request.scenario_code is not None
            and plan.intent
            in (
                ChatIntent.ACCOUNT_RULE,
                ChatIntent.EDUCATIONAL_PORTFOLIO,
                ChatIntent.OUT_OF_SCOPE,
            )
            and _SELECTED_SCENARIO_DIAGNOSIS_TERMS.search(request.message) is not None
        )

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
            response = blocked_response(resolved_plan.blocked_reason)
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
                survey_profile = (
                    original_request.survey_profile
                    or (
                        original_request.conversation_context.survey_profile
                        if original_request.conversation_context is not None
                        else None
                    )
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
                                    survey_profile.portfolio_account_types()
                                )
                            ],
                            portfolio_universe_loader=(
                                self._portfolio_universe_loader
                            ),
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
                    theme_repository=self._theme_repository,
                    theme_verification=self._theme_verification,
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
                    response = self._news_follow_up_response(
                        original_request, news_follow_up
                    )
                else:
                    exclude_item_ids = (
                        tuple(
                            original_request.conversation_context.news.news_item_ids
                        )
                        if news_follow_up is not None
                        and news_follow_up.action == NewsFollowUpAction.REFRESH
                        and original_request.conversation_context is not None
                        and original_request.conversation_context.news is not None
                        else ()
                    )
                    if resolved_plan.requests_event_strategy:
                        response = self._event_strategy_response(
                            original_request,
                            search_query=resolved_plan.news_query,
                            max_results=resolved_plan.max_results,
                            preferred_topics=preferred_news_topics,
                        )
                    else:
                        response = self._news_response(
                            request,
                            search_query=resolved_plan.news_query,
                            max_results=resolved_plan.max_results,
                            exclude_item_ids=exclude_item_ids,
                            preferred_topics=preferred_news_topics,
                        )
            elif resolved_plan.intent == ChatIntent.MACRO_EVIDENCE:
                response = macro_evidence_response(
                    request,
                    macro_evidence=self._macro_evidence,
                    portfolio_universe_loader=self._portfolio_universe_loader,
                )
            elif resolved_plan.intent == ChatIntent.PROVIDER_DISCLOSURE:
                account_type = resolved_plan.account_types[0]
                response = self._disclosure_response(request, account_type)
            elif resolved_plan.intent == ChatIntent.ACCOUNT_RULE:
                response = handle_account_rule(
                    request,
                    resolved_plan,
                    knowledge=self._knowledge,
                )
            else:
                response = blocked_response(BlockedReason.UNSUPPORTED)
        return finalize_response(response, original_request, resolved_plan)

    def _disclosure_response(
        self, request: ChatRequest, account_type: AccountType
    ) -> ChatResponse:
        if self._disclosures is None:
            return ChatResponse(
                intent=ChatIntent.PROVIDER_DISCLOSURE,
                answer=(
                    "원격 Supabase에 실제 공시 데이터가 없어 회사·사업자 수치를 "
                    "표시하지 않았어요. fixture(테스트용 데이터)를 실제 데이터처럼 "
                    "쓰지 않아요."
                ),
                data_mode="unavailable",
                limitations=["DATABASE_URL과 FSS 실적재가 필요합니다."],
            )
        rows = self._disclosures.search(
            request.message,
            account_type=account_type,
            limit=request.max_results,
        )
        if not rows:
            return ChatResponse(
                intent=ChatIntent.PROVIDER_DISCLOSURE,
                answer="조건에 맞는 최신 실제 공시를 찾지 못했어요.",
                data_mode="official_disclosure",
                limitations=["수집 상태와 질문의 회사명을 확인해 주세요."],
            )
        sources: list[SourceEvidence] = []
        numeric: list[NumericEvidence] = []
        lines: list[str] = []
        for index, row in enumerate(rows, start=1):
            evidence_id = f"disclosure:{index}"
            sources.append(
                SourceEvidence(
                    evidence_id=evidence_id,
                    label=f"FSS {row.account_type.value} 사업자 공시",
                    locator=row.source_locator,
                    publisher="금융감독원 통합연금포털",
                    as_of=row.period_end,
                    data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
                )
            )
            current_clause = (
                "당기 과거 수익률은 확인되지 않았고"
                if row.earn_rate_current_pct is None
                else (
                    "당기 과거 수익률은 "
                    f"{_decimal_text(row.earn_rate_current_pct)}%이고"
                )
            )
            three_year_clause = (
                "3년 연환산 수익률도 확인되지 않았어요"
                if row.avg_earn_rate_3y_pct is None
                else (
                    "3년 연환산 수익률은 "
                    f"{_decimal_text(row.avg_earn_rate_3y_pct)}%예요"
                )
            )
            lines.append(
                f"{row.company_name}의 {current_clause}, {three_year_clause}."
            )
            for label, value in (
                ("당기 과거 수익률", row.earn_rate_current_pct),
                ("3년 연환산 수익률", row.avg_earn_rate_3y_pct),
                ("1년 수수료율", row.fee_rate_1y_pct),
            ):
                if value is not None:
                    numeric.append(
                        NumericEvidence(
                            label=f"{row.company_name} {label}",
                            value=value,
                            unit="%",
                            evidence_id=evidence_id,
                            basis=f"{row.year}Q{row.quarter} FSS 공시",
                        )
                    )
        return ChatResponse(
            intent=ChatIntent.PROVIDER_DISCLOSURE,
            answer="과거 공시를 찾았어요. " + " ".join(lines),
            data_mode="official_disclosure",
            sections=[
                AnswerSection(
                    kind=SectionKind.FACT,
                    title="회사·사업자 과거 공시",
                    content=" ".join(lines),
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            numeric_evidence=numeric,
            limitations=[
                "사업자 집계 공시이며 개별 상품 또는 개인 계좌 수익률이 아닙니다.",
                "과거 실적은 미래 수익을 의미하지 않습니다.",
            ],
        )

    def _news_response(
        self,
        request: ChatRequest,
        *,
        search_query: str,
        max_results: int,
        exclude_item_ids: tuple[str, ...] = (),
        preferred_topics: tuple[str, ...] = (),
    ) -> ChatResponse:
        if self._news is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "저장된 뉴스 정보가 없어 최신 뉴스 답변을 만들지 않았어요."
                ),
                data_mode="unavailable",
                limitations=["NAVER 뉴스 수집과 DATABASE_URL이 필요합니다."],
            )
        is_market_news = search_query == "market" or search_query.startswith(
            "market:"
        )
        region = search_query.partition(":")[2] or None
        market_limit = min(max_results, 3)
        matches = (
            self._news.recent_market_news(
                region=region,
                days=5,
                limit=market_limit,
                exclude_item_ids=exclude_item_ids,
                preferred_topics=preferred_topics,
            )
            if is_market_news
            else self._news.latest_news(search_query, limit=request.max_results)
        )
        if not matches:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "최근 닷새간 요약이 끝난 증시 뉴스를 찾지 못했어요."
                    if is_market_news
                    else "해당 검색어로 저장된 뉴스 정보를 찾지 못했어요."
                ),
                data_mode="news_summary" if is_market_news else "news_metadata",
                limitations=["기사 본문을 임의로 생성하지 않습니다."],
            )
        sources = [
            SourceEvidence(
                evidence_id=f"news:{item.item_id}",
                label=item.title,
                locator=item.original_url,
                publisher="외부 뉴스 원문",
                as_of=item.published_at,
                data_boundary=(
                    DataBoundary.NEWS_SUMMARY
                    if is_market_news
                    else DataBoundary.NEWS_METADATA
                ),
            )
            for item in matches
        ]
        lines = (
            [_news_summary_block(item, index) for index, item in enumerate(matches)]
            if is_market_news
            else [_news_metadata_line(item) for item in matches]
        )
        answer_intro = (
            "최근 증시 뉴스를 찾았어요."
            if is_market_news
            else "관련 뉴스를 찾았어요."
        )
        limitations = (
            [
                "기사 원문에서 수집 시점에 생성한 LLM 3줄 요약입니다.",
                "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 합니다.",
            ]
            if is_market_news
            else [
                "기사 본문이 아닌 제목·요약·원문 링크 메타데이터입니다.",
                "뉴스 사실과 외부 의견은 원문에서 다시 확인해야 합니다.",
            ]
        )
        if is_market_news and len(matches) < market_limit:
            limitations.append(
                "최근 닷새간 저장된 증시 기사가 세 건 미만이라 "
                "조회된 기사만 제공합니다."
            )
        if is_market_news and max_results > 3:
            limitations.append("증시 뉴스는 한 번에 최대 세 건까지 제공해요.")
        if is_market_news and preferred_topics:
            limitations.append(
                "로그인 사용자의 가상 목계좌 자산군과 연관된 뉴스 주제를 "
                "우선 정렬했습니다."
            )
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=answer_intro + "\n\n" + "\n\n".join(lines),
            data_mode="news_summary" if is_market_news else "news_metadata",
            news_items=[
                ChatNewsItem(
                    evidence_id=f"news:{item.item_id}",
                    title=item.title,
                    description=None if is_market_news else item.description,
                    summary_lines=(list(item.summary_lines) if is_market_news else []),
                    original_url=item.original_url,
                    published_at=item.published_at,
                )
                for item in matches
            ],
            sections=[
                AnswerSection(
                    kind=SectionKind.EXTERNAL_OPINION,
                    title=(
                        "최근 닷새 한국·미국 증시 뉴스 3줄 요약"
                        if is_market_news
                        else "뉴스 검색 메타데이터"
                    ),
                    content="\n\n".join(lines),
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            limitations=limitations,
            conversation_context=(
                ConversationContext(
                    news=NewsConversationContext(
                        news_item_ids=[item.item_id for item in matches],
                        market_region=(
                            MarketRegion(region)
                            if region is not None
                            else MarketRegion.ALL
                        ),
                        shown_at=datetime.now(UTC),
                    )
                )
                if is_market_news
                else None
            ),
        )

    def _event_strategy_response(
        self,
        request: ChatRequest,
        *,
        search_query: str,
        max_results: int,
        preferred_topics: tuple[str, ...],
    ) -> ChatResponse:
        region = search_query.partition(":")[2] or None
        live_snapshot: LiveMarketNewsSnapshot | None = None
        if self._live_news is not None:
            try:
                live_snapshot = self._live_news.fetch_market_news(
                    region=region,
                    limit=min(max_results, 3),
                )
            except LiveNewsUnavailable:
                logger.warning("live_news_lookup_failed")

        topics_by_evidence: dict[str, tuple[str, ...]] = {}
        if live_snapshot is not None and live_snapshot.items:
            sources = [
                SourceEvidence(
                    evidence_id=f"live-news:{item.item_id}",
                    label=item.title,
                    locator=item.original_url,
                    publisher=item.publisher,
                    as_of=item.published_at,
                    data_boundary=DataBoundary.NEWS_METADATA,
                )
                for item in live_snapshot.items
            ]
            news_items = [
                ChatNewsItem(
                    evidence_id=f"live-news:{item.item_id}",
                    title=item.title,
                    description=item.description,
                    original_url=item.original_url,
                    published_at=item.published_at,
                )
                for item in live_snapshot.items
            ]
            topics_by_evidence = {
                f"live-news:{item.item_id}": item.topics
                for item in live_snapshot.items
            }
            metadata = "\n".join(
                f"- {item.title}: {item.description or 'NAVER 설명 없음'}"
                for item in live_snapshot.items
            )
            base = ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "NAVER 검색 API에서 최신 증시 뉴스 메타데이터를 조회했어요. "
                    "규칙 기반으로 이벤트와 ETF 산업·테마를 분류했어요."
                ),
                data_mode="live_news_event_strategy",
                news_items=news_items,
                sections=[
                    AnswerSection(
                        kind=SectionKind.EXTERNAL_OPINION,
                        title="실시간 NAVER 뉴스 메타데이터",
                        content=metadata,
                        evidence_ids=_source_ids(sources),
                    )
                ],
                sources=sources,
                limitations=[
                    (
                        "같은 시장의 직전 조회 결과를 짧게 재사용했어요."
                        if live_snapshot.from_cache
                        else "이번 질문 시점에 NAVER 검색 API를 조회했어요."
                    ),
                    "기사 본문이 아닌 NAVER 제목·설명 메타데이터입니다.",
                    "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 해요.",
                ],
            )
            return self._attach_event_strategy(
                base,
                request=request,
                topics_by_evidence=topics_by_evidence,
            )

        stored = self._news_response(
            request,
            search_query=search_query,
            max_results=max_results,
            preferred_topics=preferred_topics,
        )
        if not stored.news_items:
            return stored.model_copy(
                update={
                    "answer": (
                        "실시간 NAVER 조회와 저장 뉴스 조회에서 모두 "
                        "사용 가능한 증시 뉴스를 찾지 못했어요."
                    ),
                    "limitations": [
                        *stored.limitations,
                        "뉴스를 임의로 생성해 이벤트 전략을 만들지 않아요.",
                    ],
                }
            )
        stored = stored.model_copy(
            update={
                "data_mode": "stored_news_event_strategy",
                "answer": (
                    "실시간 NAVER 조회를 사용할 수 없어 최근 저장 뉴스를 "
                    "이벤트와 ETF 산업·테마로 분류했어요."
                ),
                "limitations": [
                    *stored.limitations,
                    "실시간 조회가 아니라 최근 저장 뉴스 기반입니다.",
                ],
            }
        )
        return self._attach_event_strategy(
            stored,
            request=request,
            topics_by_evidence=topics_by_evidence,
        )

    def _attach_event_strategy(
        self,
        response: ChatResponse,
        *,
        request: ChatRequest,
        topics_by_evidence: dict[str, tuple[str, ...]],
    ) -> ChatResponse:
        policy_source_id = "policy:live_news_event_strategy"
        catalog = (
            self._theme_repository.catalog
            if self._theme_repository is not None
            else None
        )
        rows: list[list[str]] = []
        news_source_ids: list[str] = []
        for item in response.news_items:
            classification = classify_news_event(
                title=item.title,
                description=(
                    item.description or " ".join(item.summary_lines)
                ),
                topics=topics_by_evidence.get(item.evidence_id, ()),
                theme_catalog=catalog,
            )
            theme_names = []
            if self._theme_repository is not None:
                theme_names = [
                    theme.name
                    for theme_id in classification.theme_ids
                    if (theme := self._theme_repository.get(theme_id)) is not None
                ]
            etf_labels = theme_names or list(classification.etf_groups)
            rows.append(
                [
                    item.title,
                    " · ".join(classification.event_labels),
                    " · ".join(etf_labels),
                    classification.check,
                ]
            )
            news_source_ids.append(item.evidence_id)

        survey = request.survey_profile or (
            request.conversation_context.survey_profile
            if request.conversation_context is not None
            else None
        )
        tactical_allowed = (
            survey is not None
            and _RISK_PROFILE_RANKS[survey.risk_profile]
            >= _RISK_PROFILE_RANKS[EducationalRiskProfile.ACTIVE]
        )
        if tactical_allowed:
            strategy_intro = (
                "현재 설문 성향 범위에서 전술 관찰 가이드를 제공해요. "
                "뉴스만으로 비중이나 주문을 결정하지 않아요."
            )
            strategy_items = [
                "기존 장기 코어 배분을 먼저 유지하고 테마는 전술 슬리브에서만 검토",
                "공식 발표·가격·거래대금·ETF 구성종목을 함께 확인",
                "계좌별 위험자산 한도와 규칙 엔진 목표비중을 먼저 적용",
                "리밸런싱은 목표비중 이탈과 신규 납입금 기준으로 별도 계산",
            ]
        elif survey is None:
            strategy_intro = (
                "투자성향 설문이 없어 이벤트·테마 분류만 제공해요. "
                "공격형 전술 운용 가이드는 성향 확인 뒤에 연결해요."
            )
            strategy_items = [
                "뉴스 단독 매수·매도 금지",
                "공식 발표와 ETF 구성종목을 먼저 확인",
            ]
        else:
            strategy_intro = (
                "현재 설문 성향보다 공격적인 이벤트 전술은 제안하지 않아요. "
                "뉴스와 ETF 산업·테마 분류만 참고용으로 제공해요."
            )
            strategy_items = [
                "장기 코어 배분과 정기 리밸런싱 원칙 유지",
                "뉴스 단독 매수·매도 금지",
            ]

        policy_source = SourceEvidence(
            evidence_id=policy_source_id,
            label=f"뉴스 이벤트 전략 가이드 정책 {NEWS_EVENT_POLICY_VERSION}",
            locator="backend/app/chat/news_event_strategy.py",
            publisher="연금 코파일럿 규칙 정책",
            as_of=NEWS_EVENT_POLICY_AS_OF,
            data_boundary=DataBoundary.ENGINE,
        )
        sections = [
            *response.sections,
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="이벤트·ETF 산업/테마 분류",
                content=(
                    "기사 메타데이터와 기존 ETF 테마 카탈로그를 규칙으로 "
                    "연결한 관찰 목록입니다."
                ),
                evidence_ids=[*news_source_ids, policy_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.TABLE,
                        headers=["뉴스", "이벤트", "ETF 산업·테마", "추가 확인"],
                        rows=rows,
                    )
                ],
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="이벤트 드리븐 운용 가이드",
                content=strategy_intro,
                evidence_ids=[policy_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="운용 체크",
                        items=strategy_items,
                    )
                ],
            ),
        ]
        return response.model_copy(
            update={
                "sections": sections,
                "sources": [*response.sources, policy_source],
                "limitations": [
                    *response.limitations,
                    "이벤트 분류는 방향성·수익률 예측이나 자동운용 신호가 아닙니다.",
                ],
                "conversation_context": ConversationContext(
                    account_type=(survey.account_type if survey is not None else None),
                    last_intent=ChatIntent.NEWS,
                    survey_profile=survey,
                ),
            }
        )

    def _news_follow_up_response(
        self, request: ChatRequest, follow_up: NewsFollowUp
    ) -> ChatResponse:
        context = request.conversation_context
        news_context = context.news if context is not None else None
        if news_context is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer="현재 세션에서 먼저 표시된 증시 뉴스가 없어요.",
                data_mode="news_follow_up",
                limitations=["먼저 증시 뉴스를 요청해 주세요."],
            )
        if follow_up.action == NewsFollowUpAction.CLARIFY:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "현재 세션에 여러 뉴스가 있어요. "
                    "첫 번째, 두 번째처럼 확인할 기사를 지정해 주세요."
                ),
                data_mode="news_follow_up",
                limitations=["여러 기사 중 대상을 임의로 선택하지 않아요."],
                conversation_context=ConversationContext(news=news_context),
            )
        if self._news is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer="저장된 뉴스 데이터에 연결할 수 없어요.",
                data_mode="unavailable",
                limitations=["DATABASE_URL과 저장된 뉴스 데이터가 필요해요."],
                conversation_context=ConversationContext(news=news_context),
            )

        selected = [
            (index, news_context.news_item_ids[index])
            for index in follow_up.item_indexes
        ]
        matches = self._news.news_by_ids(tuple(item_id for _, item_id in selected))
        matches_by_id = {item.item_id: item for item in matches}
        ordered = [
            (index, matches_by_id[item_id])
            for index, item_id in selected
            if item_id in matches_by_id
        ]
        if len(ordered) != len(selected):
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "세션에서 참조한 뉴스가 현재 저장소에 없어 다시 불러오지 "
                    "못했어요. 최신 증시 뉴스를 다시 요청해 주세요."
                ),
                data_mode="unavailable",
                limitations=["만료된 뉴스 내용을 임의로 복원하지 않아요."],
                conversation_context=ConversationContext(news=news_context),
            )
        if any(len(item.summary_lines) != 3 for _, item in ordered):
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer="검증된 3줄 요약이 없어 후속 비교를 만들지 않았어요.",
                data_mode="unavailable",
                limitations=["기사 내용을 임의로 보완하지 않아요."],
                conversation_context=ConversationContext(news=news_context),
            )

        sources = [
            SourceEvidence(
                evidence_id=f"news:{item.item_id}",
                label=item.title,
                locator=item.original_url,
                publisher="외부 뉴스 원문",
                as_of=item.published_at,
                data_boundary=DataBoundary.NEWS_SUMMARY,
            )
            for _, item in ordered
        ]
        if follow_up.action == NewsFollowUpAction.SOURCE:
            lines = [
                (
                    f"{index + 1}번째 뉴스 — {item.title}\n"
                    "발행일: "
                    + (
                        item.published_at.date().isoformat()
                        if item.published_at is not None
                        else "확인되지 않음"
                    )
                    + f"\n원문 링크: {item.original_url}"
                )
                for index, item in ordered
            ]
            title = "뉴스 출처와 발행일"
        elif follow_up.action == NewsFollowUpAction.COMPARE:
            lines = [
                _news_comparison_block(item, index) for index, item in ordered
            ]
            lines.insert(
                0,
                "기사별 검증된 메타데이터와 요약을 같은 항목으로 "
                "나란히 비교해요.",
            )
            title = "세션 뉴스 비교"
        else:
            lines = [_news_summary_block(item, index) for index, item in ordered]
            title = "선택한 뉴스 다시 보기"
        focus_id = selected[0][1] if len(selected) == 1 else None
        updated_news_context = news_context.model_copy(
            update={"focus_news_item_id": focus_id}
        )
        answer = "\n\n".join(lines)
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=answer,
            data_mode="news_follow_up",
            news_items=[
                ChatNewsItem(
                    evidence_id=f"news:{item.item_id}",
                    title=item.title,
                    summary_lines=list(item.summary_lines),
                    original_url=item.original_url,
                    published_at=item.published_at,
                )
                for _, item in ordered
            ],
            sections=[
                AnswerSection(
                    kind=SectionKind.EXTERNAL_OPINION,
                    title=title,
                    content=answer,
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            limitations=[
                "이 세션에서 앞서 보여드린 뉴스만 다시 조회했어요.",
                "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 해요.",
            ],
            conversation_context=ConversationContext(news=updated_news_context),
        )
