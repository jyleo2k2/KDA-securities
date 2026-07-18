import logging
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from ..engine import (
    AccountType,
    EducationalPortfolioEvaluation,
    EducationalPortfolioInput,
    EducationalRiskProfile,
    NonPensionWithdrawalEvaluation,
    PensionTaxCreditEvaluation,
    PensionTaxToolResult,
    WithdrawalCalculationStatus,
    build_educational_portfolio,
    evaluate_mock_scenario,
    evaluate_risk_cap,
)
from ..retrieval.repository import KnowledgeMatch, NewsMatch
from .disclosures import ProviderDisclosure
from .models import (
    AnswerSection,
    ChatCapabilities,
    ChatIntent,
    ChatNewsItem,
    ChatRequest,
    ChatResponse,
    ChatVisualization,
    ConversationContext,
    DataBoundary,
    MarketRegion,
    NewsConversationContext,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
    VisualizationDatum,
    VisualizationDatumRole,
    VisualizationKind,
    extract_numeric_claims,
)
from .pension_account_overview import (
    build_deferred_pension_topic_response,
    build_pension_account_overview_response,
)
from .pension_tax_parser import resolve_pension_tax_inputs
from .query_planner import AccountRuleTopic, BlockedReason, QueryPlan, plan_question
from .routing import IntentRouter, NewsFollowUp, NewsFollowUpAction
from .scenarios import ScenarioRepository
from .tools import (
    DC_WITHDRAWAL_EXCLUSION_NOTICE,
    PENSION_TAX_CLOSING_NOTICE,
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)

logger = logging.getLogger(__name__)


class KnowledgeSearch(Protocol):
    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]: ...


class DisclosureSearch(Protocol):
    def search(
        self,
        question: str,
        *,
        account_type: AccountType,
        limit: int,
    ) -> list[ProviderDisclosure]: ...


class NewsSearch(Protocol):
    def latest_news(self, search_query: str, *, limit: int = 10) -> list[NewsMatch]: ...

    def random_recent_news(
        self, search_query: str, *, days: int = 5, limit: int = 3
    ) -> list[NewsMatch]: ...

    def recent_market_news(
        self,
        *,
        region: str | None = None,
        days: int = 5,
        limit: int = 3,
        exclude_item_ids: tuple[str, ...] = (),
    ) -> list[NewsMatch]: ...

    def news_by_ids(self, item_ids: tuple[str, ...]) -> list[NewsMatch]: ...


class PortfolioUniverse(Protocol):
    products: list[dict[str, Any]]
    histories: dict[str, dict[date, Decimal]]
    history_sources: dict[str, str]
    as_of: date


class PortfolioUniverseLoader(Protocol):
    def __call__(self, account_type: AccountType) -> PortfolioUniverse: ...


SCENARIO_KEYWORDS = {
    "방치": "dc_dormant",
    "세액공제": "tax_contribution_uninvested",
    "미운용": "tax_contribution_uninvested",
    "중복": "overlap_risk_concentration",
    "편중": "overlap_risk_concentration",
}
_SELECTED_SCENARIO_DIAGNOSIS_TERMS = re.compile(
    r"(?:내|나의)\s*(?:연금|계좌|자산).{0,20}(?:관리|상태|구성|확인|어떻게)"
    r"|지금\s*(?:뭘|무엇을).{0,20}(?:먼저\s*)?확인"
)
_ASSET_CLASS_LABELS = {
    "deposit": "원리금보장형 자산",
    "cash": "현금성 자산",
    "bond": "채권형 자산",
    "global_equity": "글로벌 주식형 자산",
    "eligible_tdf": "적격 TDF",
}


def _news_metadata_line(item: NewsMatch) -> str:
    headline = (
        f"{item.title} ({item.published_at.date().isoformat()})"
        if item.published_at is not None
        else item.title
    )
    if item.description is None:
        return headline
    summary = re.sub(r"\s+", " ", item.description).strip()[:180]
    return f"{headline} — {summary}" if summary else headline


def _news_summary_block(item: NewsMatch, index: int) -> str:
    ordinal = ("첫 번째", "두 번째", "세 번째")
    label = ordinal[index] if index < len(ordinal) else f"{index + 1}번째"
    headline = (
        f"{item.title} ({item.published_at.date().isoformat()})"
        if item.published_at is not None
        else item.title
    )
    if item.publisher:
        headline = f"{item.publisher} · {headline}"
    summary = "\n".join(item.summary_lines)
    return f"{label} 뉴스 — {headline}\n{summary}\n원문 링크: {item.original_url}"


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _one_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


_RISK_PROFILE_LABELS = {
    "stable": "안정형",
    "stable_seeking": "안정추구형",
    "risk_neutral": "위험중립형",
    "active": "적극투자형",
    "aggressive": "공격투자형",
}
_ACCOUNT_TYPE_LABELS = {
    AccountType.DC: "DC형",
    AccountType.IRP: "IRP",
    AccountType.PENSION_SAVINGS: "연금저축펀드",
}
_RISK_PROFILE_RANKS = {
    EducationalRiskProfile.STABLE: 0,
    EducationalRiskProfile.STABLE_SEEKING: 1,
    EducationalRiskProfile.RISK_NEUTRAL: 2,
    EducationalRiskProfile.ACTIVE: 3,
    EducationalRiskProfile.AGGRESSIVE: 4,
}
_RISK_PROFILE_PATTERNS = (
    (re.compile(r"안정\s*추구형"), EducationalRiskProfile.STABLE_SEEKING),
    (re.compile(r"위험\s*중립형"), EducationalRiskProfile.RISK_NEUTRAL),
    (re.compile(r"적극\s*투자형"), EducationalRiskProfile.ACTIVE),
    (re.compile(r"공격\s*투자형"), EducationalRiskProfile.AGGRESSIVE),
    (re.compile(r"안정형"), EducationalRiskProfile.STABLE),
)
_RISK_PROFILE_GUIDE_PATTERNS = (
    re.compile(
        r"투자\s*(?:성향|스타일).{0,24}"
        r"(?:뭐|무엇|어떤|종류|구분|알려|설명|모르|선택지)"
    ),
    re.compile(
        r"(?:뭐|무엇|어떤|종류|구분|알려|설명|모르|선택지).{0,24}"
        r"투자\s*(?:성향|스타일)"
    ),
)
_RISK_PROFILE_PORTFOLIO_REQUEST = re.compile(
    r"포트폴리오|자산\s*배분|연금\s*(?:운용|투자)\s*전략|"
    r"운용\s*전략|투자\s*전략|수익률|설계"
)
_STRATEGY_LABELS = {
    "capital_preservation_core": "자본보전 중심 전략",
    "defensive_diversified_core": "방어적 분산 전략",
    "balanced_core_satellite": "코어·위성 전략",
    "growth_core_satellite": "성장 코어·위성 전략",
    "barbell_growth_tactical": "바벨형 성장·전술 전략",
}
_SLEEVE_LABELS = {
    "core_equity": "주식",
    "real_assets": "실물자산",
    "tactical": "전술자산",
    "fixed_income": "채권",
    "cash": "현금",
}
_ROLE_SENTENCES = {
    "long_term_growth_core": "주식 ETF를 장기 성장 핵심자산으로 둡니다.",
    "inflation_and_diversification": (
        "실물자산은 인플레이션 대응과 분산 역할을 맡습니다."
    ),
    "capped_tactical_satellite": (
        "전술자산은 한도가 정해진 위성자산으로만 활용합니다."
    ),
    "drawdown_buffer": "채권은 하락 위험을 완충하는 역할을 맡습니다.",
    "liquidity_and_rebalancing_reserve": (
        "현금은 유동성과 리밸런싱 여력을 확보합니다."
    ),
}


def _selected_risk_profile(message: str) -> EducationalRiskProfile | None:
    for pattern, profile in _RISK_PROFILE_PATTERNS:
        if pattern.search(message):
            return profile
    return None


def _requests_risk_profile_guide(message: str) -> bool:
    if _selected_risk_profile(message) is not None:
        return False
    if _RISK_PROFILE_PORTFOLIO_REQUEST.search(message):
        return False
    return any(pattern.search(message) for pattern in _RISK_PROFILE_GUIDE_PATTERNS)


def _strategy_summary(evaluation: EducationalPortfolioEvaluation) -> str:
    profile = _RISK_PROFILE_LABELS[evaluation.evaluated_input.risk_profile.value]
    strategy = _STRATEGY_LABELS[evaluation.strategy_label]
    role_sentences = [
        _ROLE_SENTENCES[target.role] for target in evaluation.target_sleeves
    ]
    return (
        f"{evaluation.planning_horizon_years}년의 장기 운용기간을 고려한 "
        f"{profile} {strategy}입니다. " + " ".join(role_sentences)
    )


def _target_portfolio_summary(
    evaluation: EducationalPortfolioEvaluation,
) -> str:
    candidates_by_sleeve: dict[str, list[str]] = {}
    for candidate in evaluation.candidates:
        candidates_by_sleeve.setdefault(candidate.sleeve, []).append(candidate.isu_name)
    lines = []
    for target in evaluation.target_sleeves:
        label = _SLEEVE_LABELS[target.sleeve]
        percent = _decimal_text(_one_decimal(target.target_percent))
        names = " · ".join(candidates_by_sleeve.get(target.sleeve, []))
        candidate_text = f" (엔진 편입 후보: {names})" if names else ""
        lines.append(f"{label} 약 {percent}%{candidate_text}")
    risk_target = _decimal_text(
        _one_decimal(evaluation.final_general_risk_target_percent)
    )
    return (
        ",\n".join(lines)
        + f"\n일반 위험자산 목표비중은 전체의 약 {risk_target}%입니다."
    )


def _rebalancing_summary(evaluation: EducationalPortfolioEvaluation) -> str:
    rebalancing = evaluation.rebalancing
    threshold = _decimal_text(_one_decimal(rebalancing.drift_threshold_percent_points))
    parts = [
        f"목표비중에서 {threshold}%포인트를 초과해 벗어난 자산군은 "
        "리밸런싱 점검 대상으로 봅니다."
    ]
    if rebalancing.contribution_first:
        parts.append("매도보다 신규 납입금을 부족한 자산에 먼저 배분합니다.")
    if not rebalancing.sell_instruction_produced:
        parts.append("자동 매도 지시는 만들지 않습니다.")
    if rebalancing.status == "not_requested":
        parts.append("보유자산 입력이 없어 현재 이탈폭 계산은 생략했습니다.")
    else:
        review = [
            _SLEEVE_LABELS[item.sleeve]
            for item in rebalancing.sleeves
            if item.status != "within_drift_band"
        ]
        if review:
            parts.append(f"현재 입력에서는 {' · '.join(review)}을(를) 점검합니다.")
        else:
            parts.append("현재 입력에서는 모든 자산군이 허용 범위 안입니다.")
        if rebalancing.status == "partial_unclassified_holdings":
            parts.append("분류되지 않은 보유자산은 별도 확인이 필요합니다.")
    return " ".join(parts)


def _knowledge_sources(matches: list[KnowledgeMatch]) -> list[SourceEvidence]:
    return [
        SourceEvidence(
            evidence_id=f"knowledge:{match.chunk_id}",
            label=match.title,
            locator=match.source_url,
            publisher="연금 코파일럿 검증 지식",
            as_of=match.as_of_date,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        )
        for match in matches
    ]


def _source_ids(sources: list[SourceEvidence]) -> list[str]:
    return [source.evidence_id for source in sources]


class ChatService:
    def __init__(
        self,
        *,
        knowledge: KnowledgeSearch,
        scenarios: ScenarioRepository,
        disclosures: DisclosureSearch | None = None,
        news: NewsSearch | None = None,
        portfolio_universe_loader: PortfolioUniverseLoader | None = None,
        router: IntentRouter | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scenarios = scenarios
        self._disclosures = disclosures
        self._news = news
        self._portfolio_universe_loader = portfolio_universe_loader
        self._router = router or IntentRouter()

    def capabilities(self) -> ChatCapabilities:
        return ChatCapabilities(
            supported=[
                "DC형·IRP·연금저축 계좌 규칙 근거 Q&A",
                "목계좌 시나리오 위험자산 한도와 통합 자산군 진단",
                "연령·성향·수령개시연령별 교육용 포트폴리오 위험·계획가정",
                "연금저축·IRP 당해연도 납입액 세액공제 간이 계산",
                "연금저축·IRP 연금외수령 16.5% 간이 추정",
                "근거·기준일·실데이터/목데이터 경계 표시",
            ],
            conditional=[
                "Supabase 실적재 후 회사·사업자 과거 공시 비교",
                "NAVER 증시뉴스 적재 후 매체·3줄 요약·원문 링크 조회",
            ],
            unsupported=[
                "DC·IRP 개별 상품 비교",
                "LLM의 미래 수익률·목표가 직접 예측",
                "주문·자동운용",
            ],
            scenario_codes=[item.code for item in self._scenarios.list()],
        )

    def plan(self, request: ChatRequest) -> QueryPlan:
        direct_plan = plan_question(
            request.message, default_max_results=request.max_results
        )
        if self._is_selected_scenario_diagnosis_request(request, direct_plan):
            return QueryPlan(
                normalized_message=direct_plan.normalized_message,
                intent=ChatIntent.MOCK_PORTFOLIO,
                max_results=direct_plan.max_results,
            )
        if direct_plan.blocked_reason not in {
            None,
            BlockedReason.UNSUPPORTED,
            BlockedReason.UNSUPPORTED_NEWS_TOPIC,
        }:
            return direct_plan
        news_follow_up = self._router.news_follow_up(request)
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
                max_results=3,
            )
        if direct_plan.blocked_reason != BlockedReason.UNSUPPORTED:
            return direct_plan
        contextual_message = self._router.contextual_message(request)
        if contextual_message == request.message:
            return direct_plan
        return plan_question(
            contextual_message, default_max_results=request.max_results
        )

    @staticmethod
    def _is_selected_scenario_diagnosis_request(
        request: ChatRequest, plan: QueryPlan
    ) -> bool:
        return (
            request.scenario_code is not None
            and plan.intent in (ChatIntent.ACCOUNT_RULE, ChatIntent.OUT_OF_SCOPE)
            and _SELECTED_SCENARIO_DIAGNOSIS_TERMS.search(request.message) is not None
        )

    def ask(
        self,
        request: ChatRequest,
        *,
        plan: QueryPlan | None = None,
        prefer_structured_pension_tax: bool = False,
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
            response = self._blocked_response(resolved_plan.blocked_reason)
        else:
            request = request.model_copy(
                update={
                    "message": resolved_plan.normalized_message,
                    "max_results": resolved_plan.max_results,
                }
            )
            if request.portfolio is not None:
                response = self._custom_portfolio(request)
            elif request.educational_portfolio is not None:
                response = self._educational_portfolio(request.educational_portfolio)
            elif resolved_plan.intent == ChatIntent.EDUCATIONAL_PORTFOLIO:
                survey_profile = original_request.survey_profile or (
                    original_request.conversation_context.survey_profile
                    if original_request.conversation_context is not None
                    else None
                )
                if _requests_risk_profile_guide(original_request.message):
                    response = self._risk_profile_selection_guide()
                elif survey_profile is None:
                    response = self._completed_survey_required()
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
                        response = self._risk_profile_guardrail(
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
                        response = self._educational_portfolios(
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
                            ]
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
            elif resolved_plan.intent == ChatIntent.PENSION_TAX:
                response = self._pension_tax_response(
                    request,
                    resolved_plan,
                    prefer_structured=prefer_structured_pension_tax,
                )
            elif resolved_plan.intent == ChatIntent.MOCK_PORTFOLIO:
                scenario_code = request.scenario_code or self._scenario_code(
                    request.message
                )
                response = (
                    self._scenario_response(scenario_code)
                    if scenario_code is not None
                    else self._scenario_selection_response()
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
                    response = self._news_response(
                        request,
                        search_query=resolved_plan.news_query,
                        max_results=resolved_plan.max_results,
                        exclude_item_ids=exclude_item_ids,
                    )
            elif resolved_plan.intent == ChatIntent.PROVIDER_DISCLOSURE:
                account_type = resolved_plan.account_types[0]
                response = self._disclosure_response(request, account_type)
            elif resolved_plan.intent == ChatIntent.ACCOUNT_RULE:
                if (
                    resolved_plan.account_rule_topic
                    == AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW
                ):
                    response = self._pension_account_overview_response()
                elif resolved_plan.account_rule_topic is not None:
                    response = build_deferred_pension_topic_response(
                        resolved_plan.account_rule_topic
                    )
                else:
                    response = self._account_rule_response(request, resolved_plan)
            else:
                response = self._blocked_response(BlockedReason.UNSUPPORTED)
        return self._with_context(
            self._attach_visualizations(response), original_request, resolved_plan
        )

    @staticmethod
    def _attach_visualizations(response: ChatResponse) -> ChatResponse:
        """Attach only views backed by the response's existing engine evidence."""

        if response.scenario_evaluation is not None:
            evaluation = response.scenario_evaluation
            visualization = ChatVisualization(
                kind=VisualizationKind.ASSET_ALLOCATION,
                title="전체 자산 구성",
                description="계좌를 합쳐 어떤 자산에 얼마나 담겼는지 보여줘요.",
                data_boundary=DataBoundary.MOCK,
                evidence_ids=["mock:scenario", "engine:scenario"],
                items=[
                    VisualizationDatum(
                        label=_ASSET_CLASS_LABELS[item.asset_class_code],
                        value=item.allocation_percent,
                        unit="%",
                        role=VisualizationDatumRole.SEGMENT,
                    )
                    for item in evaluation.asset_allocations
                ],
            )
            return response.model_copy(update={"visualizations": [visualization]})

        tax_credit = (
            response.pension_tax_result.tax_credit
            if response.pension_tax_result is not None
            else None
        )
        if tax_credit is not None and tax_credit.rate_determined:
            rate = tax_credit.rate_scenarios[0]
            visualization = ChatVisualization(
                kind=VisualizationKind.TAX_SUMMARY,
                title="세액공제 요약",
                description="입력한 납입액과 규칙 엔진 계산 결과를 함께 보여줘요.",
                data_boundary=DataBoundary.ENGINE,
                evidence_ids=[
                    "user:pension_tax",
                    "engine:pension_tax",
                    "rule:pension_tax:credit",
                ],
                items=[
                    VisualizationDatum(
                        label="세액공제 대상 납입액",
                        value=tax_credit.total_eligible_contribution_krw,
                        unit="KRW",
                        role=VisualizationDatumRole.VALUE,
                    ),
                    VisualizationDatum(
                        label="예상 세액공제액",
                        value=rate.estimated_tax_credit_krw,
                        unit="KRW",
                        role=VisualizationDatumRole.VALUE,
                    ),
                ],
            )
            return response.model_copy(update={"visualizations": [visualization]})

        risk_items = [
            item
            for item in response.numeric_evidence
            if "위험자산 비중" in item.label or "위험자산 한도" in item.label
        ]
        if not risk_items:
            return response
        visualization_items = [
            VisualizationDatum(
                label=item.label,
                value=item.value,
                unit=item.unit,
                role=(
                    VisualizationDatumRole.CURRENT
                    if "비중" in item.label
                    else VisualizationDatumRole.LIMIT
                ),
            )
            for item in risk_items
        ]
        visualization = ChatVisualization(
            kind=VisualizationKind.RISK_CAP,
            title="위험자산 기준",
            description="현재 비중과 계좌 기준을 한눈에 비교해 보세요.",
            data_boundary=(
                DataBoundary.ENGINE
                if any(item.evidence_id.startswith("engine:") for item in risk_items)
                else DataBoundary.VERIFIED_KNOWLEDGE
            ),
            evidence_ids=list(dict.fromkeys(item.evidence_id for item in risk_items)),
            items=visualization_items,
        )
        return response.model_copy(update={"visualizations": [visualization]})

    @staticmethod
    def _with_context(
        response: ChatResponse, request: ChatRequest, plan: QueryPlan
    ) -> ChatResponse:
        previous = request.conversation_context
        response_context = response.conversation_context
        survey_profile = (
            request.survey_profile
            or (
                response_context.survey_profile
                if response_context is not None
                else None
            )
            or (previous.survey_profile if previous is not None else None)
        )
        selected_risk_profile = (
            response_context.selected_risk_profile
            if response_context is not None
            and response_context.selected_risk_profile is not None
            else previous.selected_risk_profile
            if previous is not None
            else None
        )
        account_type = (
            response_context.account_type
            if response_context is not None
            and response_context.account_type is not None
            else plan.account_types[0]
            if len(plan.account_types) == 1
            else request.portfolio.account_type
            if request.portfolio is not None
            else request.educational_portfolio.account_type
            if request.educational_portfolio is not None
            else survey_profile.account_type
            if survey_profile is not None
            else previous.account_type
            if previous is not None
            else None
        )
        scenario_code = (
            request.scenario_code
            or (
                response_context.scenario_code if response_context is not None else None
            )
            or (previous.scenario_code if previous is not None else None)
        )
        news_context = (
            response_context.news
            if response_context is not None and response_context.news is not None
            else previous.news
            if previous is not None
            else None
        )
        return response.model_copy(
            update={
                "conversation_context": ConversationContext(
                    account_type=account_type,
                    scenario_code=scenario_code,
                    last_intent=response.intent,
                    survey_profile=survey_profile,
                    selected_risk_profile=selected_risk_profile,
                    news=news_context,
                )
            }
        )

    def _pension_tax_response(
        self,
        request: ChatRequest,
        plan: QueryPlan,
        *,
        prefer_structured: bool = False,
    ) -> ChatResponse:
        resolved_inputs = resolve_pension_tax_inputs(
            request.message,
            request.pension_tax,
            prefer_structured=prefer_structured,
        )
        missing: list[str] = []
        if plan.requests_tax_credit and resolved_inputs.tax_credit is None:
            missing.extend(resolved_inputs.missing_tax_credit)
        if plan.requests_withdrawal_tax and resolved_inputs.withdrawal is None:
            missing.extend(resolved_inputs.missing_withdrawal)
        if missing:
            missing_text = "·".join(dict.fromkeys(missing))
            return ChatResponse(
                intent=ChatIntent.PENSION_TAX,
                answer=(
                    f"질문에서 {missing_text}을(를) 확인하지 못했습니다. "
                    "해당 값만 질문에 포함하거나 연금세액 입력 패널에 "
                    f"입력해 주세요.\n{PENSION_TAX_CLOSING_NOTICE}"
                ),
                data_mode="input_required",
                limitations=[
                    "계좌번호·주민등록번호·인증정보는 입력하지 마세요.",
                    "입력 금액은 세무자문이 아닌 교육용 간이 계산에만 사용합니다.",
                ],
            )

        tax_credit: PensionTaxCreditEvaluation | None = None
        withdrawal: NonPensionWithdrawalEvaluation | None = None
        if plan.requests_tax_credit:
            assert resolved_inputs.tax_credit is not None
            tax_credit = calculate_pension_tax_credit_tool(resolved_inputs.tax_credit)
        if plan.requests_withdrawal_tax:
            assert resolved_inputs.withdrawal is not None
            withdrawal = estimate_non_pension_withdrawal_tax_tool(
                resolved_inputs.withdrawal
            )
        result = PensionTaxToolResult(
            tax_credit=tax_credit,
            withdrawal=withdrawal,
        )
        sources = self._pension_tax_sources(result)
        numeric: list[NumericEvidence] = []
        sections: list[AnswerSection] = []
        answer_parts: list[str] = []
        limitations: list[str] = []

        if tax_credit is not None:
            credit_text = self._tax_credit_text(tax_credit)
            answer_parts.append(credit_text)
            sections.append(
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="당해연도 세액공제 간이 계산",
                    content=credit_text,
                    evidence_ids=[
                        "user:pension_tax",
                        "engine:pension_tax",
                        "rule:pension_tax:credit",
                    ],
                )
            )
            numeric.extend(self._tax_credit_numeric(tax_credit))
            limitations.append(tax_credit.assumption_notice)

        if withdrawal is not None:
            withdrawal_text = self._withdrawal_text(withdrawal)
            answer_parts.append(withdrawal_text)
            sections.append(
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="연금외수령 기타소득 간이 추정",
                    content=withdrawal_text,
                    evidence_ids=[
                        "user:pension_tax",
                        "engine:pension_tax",
                        "rule:pension_tax:withdrawal_order",
                        "rule:pension_tax:withdrawal",
                    ],
                )
            )
            numeric.extend(self._withdrawal_numeric(withdrawal))
            limitations.extend(withdrawal.assumptions)
            limitations.extend(withdrawal.limitations)

        closing_notices = []
        if withdrawal is not None:
            closing_notices.append(DC_WITHDRAWAL_EXCLUSION_NOTICE)
        closing_notices.append(PENSION_TAX_CLOSING_NOTICE)
        return ChatResponse(
            intent=ChatIntent.PENSION_TAX,
            answer=" ".join(answer_parts) + "\n" + "\n".join(closing_notices),
            data_mode="user_input_engine",
            sections=sections,
            sources=sources,
            numeric_evidence=numeric,
            pension_tax_result=result,
            limitations=list(dict.fromkeys(limitations)),
        )

    @staticmethod
    def _pension_tax_sources(
        result: PensionTaxToolResult,
    ) -> list[SourceEvidence]:
        evidence = [
            *(result.tax_credit.evidence if result.tax_credit is not None else []),
            *(result.withdrawal.evidence if result.withdrawal is not None else []),
        ]
        credit_source = next(
            (item for item in evidence if "59조의3" in item.label),
            None,
        )
        withdrawal_source = next(
            (item for item in evidence if "원천징수세율" in item.label),
            None,
        )
        withdrawal_order_source = next(
            (item for item in evidence if "인출순서" in item.label),
            None,
        )
        sources = [
            SourceEvidence(
                evidence_id="user:pension_tax",
                label="사용자가 입력한 계좌 잔액·당해연도 납입액",
                locator="request://pension-tax",
                publisher="사용자 입력",
                data_boundary=DataBoundary.USER_INPUT,
            ),
            SourceEvidence(
                evidence_id="engine:pension_tax",
                label="연금계좌 세액공제·연금외수령 규칙 엔진",
                locator="engine://pension_tax_guidance/2026-07-15.1",
                publisher="연금 코파일럿 규칙 엔진",
                as_of=date(2026, 7, 15),
                data_boundary=DataBoundary.ENGINE,
            ),
        ]
        if result.tax_credit is not None and credit_source is not None:
            sources.append(
                SourceEvidence(
                    evidence_id="rule:pension_tax:credit",
                    label=credit_source.label,
                    locator=credit_source.reference,
                    publisher="국가법령정보센터",
                    as_of=credit_source.as_of,
                    data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                )
            )
        if result.withdrawal is not None and withdrawal_source is not None:
            if withdrawal_order_source is not None:
                sources.append(
                    SourceEvidence(
                        evidence_id="rule:pension_tax:withdrawal_order",
                        label=withdrawal_order_source.label,
                        locator=withdrawal_order_source.reference,
                        publisher="국가법령정보센터",
                        as_of=withdrawal_order_source.as_of,
                        data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                    )
                )
            sources.append(
                SourceEvidence(
                    evidence_id="rule:pension_tax:withdrawal",
                    label=withdrawal_source.label,
                    locator=withdrawal_source.reference,
                    publisher="국세청",
                    as_of=withdrawal_source.as_of,
                    data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                )
            )
        return sources

    @staticmethod
    def _krw(value: Decimal) -> str:
        if value >= 10_000:
            in_man = value / Decimal("10000")
            text = f"{in_man:,.4f}".rstrip("0").rstrip(".")
            return f"{text}만 원"
        return f"{value:,.0f}원"

    @classmethod
    def _tax_credit_text(cls, result: PensionTaxCreditEvaluation) -> str:
        base = (
            "세액공제 대상은 총 "
            f"{cls._krw(result.total_eligible_contribution_krw)}입니다. "
            "입력한 납입액은 연금저축 "
            f"{cls._krw(result.pension_savings_contribution_krw)}, IRP "
            f"{cls._krw(result.irp_contribution_krw)}입니다."
        )
        if result.rate_determined:
            scenario = result.rate_scenarios[0]
            return (
                f"{base} 표시율 "
                f"{_decimal_text(scenario.local_inclusive_display_rate_percent)}% 기준 "
                "예상 세액공제액은 "
                f"{cls._krw(scenario.estimated_tax_credit_krw)}입니다."
            )
        ordered = sorted(
            result.rate_scenarios,
            key=lambda item: item.estimated_tax_credit_krw,
        )
        return (
            f"{base} 소득정보가 없어 표시율 "
            f"{_decimal_text(ordered[0].local_inclusive_display_rate_percent)}%와 "
            f"{_decimal_text(ordered[-1].local_inclusive_display_rate_percent)}% "
            "시나리오로 계산한 예상 세액공제액은 "
            f"{cls._krw(ordered[0].estimated_tax_credit_krw)}부터 "
            f"{cls._krw(ordered[-1].estimated_tax_credit_krw)}까지입니다."
        )

    @staticmethod
    def _tax_credit_numeric(
        result: PensionTaxCreditEvaluation,
    ) -> list[NumericEvidence]:
        numeric = [
            NumericEvidence(
                label="연금저축 당해연도 납입액",
                value=result.pension_savings_contribution_krw,
                unit="KRW",
                evidence_id="user:pension_tax",
                basis="사용자 입력",
            ),
            NumericEvidence(
                label="IRP 당해연도 납입액",
                value=result.irp_contribution_krw,
                unit="KRW",
                evidence_id="user:pension_tax",
                basis="사용자 입력",
            ),
            NumericEvidence(
                label="합산 세액공제 대상 납입액",
                value=result.total_eligible_contribution_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="2026년 연금저축 600만원·합산 900만원 한도",
            ),
        ]
        for scenario in result.rate_scenarios:
            numeric.extend(
                [
                    NumericEvidence(
                        label=f"{scenario.label} 표시율",
                        value=scenario.local_inclusive_display_rate_percent,
                        unit="%",
                        evidence_id="rule:pension_tax:credit",
                        basis="소득세율과 개인지방소득세 효과 포함",
                    ),
                    NumericEvidence(
                        label=f"{scenario.label} 예상 세액공제액",
                        value=scenario.estimated_tax_credit_krw,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="규칙 엔진 계산",
                    ),
                ]
            )
        return numeric

    @classmethod
    def _withdrawal_text(cls, result: NonPensionWithdrawalEvaluation) -> str:
        if result.status == WithdrawalCalculationStatus.REQUIRES_REVIEW:
            if result.total_balance_krw is None:
                return (
                    "의료비 등 부득이한 인출 사유는 일반 연금외수령과 "
                    "과세방식이 다를 수 있어 요청한 예상세액을 계산하지 "
                    "않았습니다. 먼저 법정 요건과 적용 과세방식을 확인해야 "
                    "합니다."
                )
            return (
                f"두 계좌 잔액 합계는 {cls._krw(result.total_balance_krw)}입니다. "
                "인출 사유를 먼저 확인해야 하므로 기타소득 간이 예상액은 "
                "계산하지 않았습니다."
            )
        assert result.assumed_other_income_tax_base_krw is not None
        assert result.other_income_rate_percent is not None
        assert result.estimated_max_other_income_withholding_krw is not None
        return (
            f"두 계좌 잔액 합계 {cls._krw(result.total_balance_krw)}에서 "
            "당해연도 납입 과세제외액 "
            f"{cls._krw(result.total_current_year_contribution_excluded_krw)} 등을 "
            "반영한 16.5% 간이 과세대상액은 "
            f"{cls._krw(result.assumed_other_income_tax_base_krw)}입니다. "
            "지방소득세를 포함한 기타소득 원천징수 최대 간이 추정액은 "
            f"{cls._krw(result.estimated_max_other_income_withholding_krw)}입니다."
        )

    @staticmethod
    def _withdrawal_numeric(
        result: NonPensionWithdrawalEvaluation,
    ) -> list[NumericEvidence]:
        numeric = []
        if result.total_balance_krw is not None:
            numeric.append(
                NumericEvidence(
                    label="연금저축·IRP 잔액 합계",
                    value=result.total_balance_krw,
                    unit="KRW",
                    evidence_id="engine:pension_tax",
                    basis="사용자 입력 잔액 합산",
                )
            )
        if result.status == WithdrawalCalculationStatus.REQUIRES_REVIEW:
            return numeric
        assert result.assumed_other_income_tax_base_krw is not None
        assert result.other_income_rate_percent is not None
        assert result.estimated_max_other_income_withholding_krw is not None
        numeric.extend(
            [
                NumericEvidence(
                    label="당해연도 납입 과세제외액",
                    value=result.total_current_year_contribution_excluded_krw,
                    unit="KRW",
                    evidence_id="rule:pension_tax:withdrawal_order",
                    basis="소득세법 시행령 인출순서",
                ),
                NumericEvidence(
                    label="기타소득 간이 과세대상액",
                    value=result.assumed_other_income_tax_base_krw,
                    unit="KRW",
                    evidence_id="engine:pension_tax",
                    basis="과세제외 재원을 차감한 규칙 엔진 계산",
                ),
                NumericEvidence(
                    label="연금외수령 기타소득 표시세율",
                    value=result.other_income_rate_percent,
                    unit="%",
                    evidence_id="rule:pension_tax:withdrawal",
                    basis="소득세 15%와 개인지방소득세 1.5% 포함",
                ),
                NumericEvidence(
                    label="최대 기타소득 원천징수 간이 추정액",
                    value=result.estimated_max_other_income_withholding_krw,
                    unit="KRW",
                    evidence_id="engine:pension_tax",
                    basis="규칙 엔진 계산",
                ),
            ]
        )
        return numeric

    @staticmethod
    def _blocked_response(reason: BlockedReason) -> ChatResponse:
        if reason == BlockedReason.SENSITIVE_INFORMATION:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "개인 식별정보나 인증정보가 포함된 질문은 처리하지 않습니다. "
                    "해당 값을 삭제한 뒤 제도나 운용 원리만 질문해 주세요."
                ),
                data_mode="blocked",
                limitations=[
                    "입력 원문은 검색이나 AI 설명 단계로 전달하지 않았습니다."
                ],
            )
        if reason == BlockedReason.FUTURE_PREDICTION:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "미래 수익률·목표가·수익 보장은 제공하지 않습니다. "
                    "구조화된 포트폴리오 입력이 있으면 규칙 엔진이 계산한 "
                    "CMA 기반 장기 계획가정과 과거 위험지표만 설명합니다."
                ),
                data_mode="blocked",
                limitations=[
                    "LLM의 미래 수익 예측은 지원하지 않습니다.",
                    "계획가정은 예측이나 보장 수익률이 아닙니다.",
                ],
            )
        if reason == BlockedReason.ORDER_REQUEST:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "상품 선택과 주문은 이용자가 금융회사 공식 채널에서 직접 "
                    "수행해야 합니다. 챗봇은 판단 기준과 근거만 설명합니다."
                ),
                data_mode="blocked",
                limitations=["주문·자동운용은 지원하지 않습니다."],
            )
        if reason == BlockedReason.PRODUCT_LEVEL_UNAVAILABLE:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "현재 실적재 계약은 연금저축 회사와 퇴직연금 사업자 집계 "
                    "단위입니다. 개별 상품 데이터로 오인될 수 있어 상품 단위 "
                    "비교·추천은 제공하지 않습니다."
                ),
                data_mode="unavailable",
                limitations=["검증된 개별 상품 식별자와 적격성 데이터가 필요합니다."],
            )
        if reason == BlockedReason.ACCOUNT_SELECTION_REQUIRED:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "공시 수치는 계좌 제도별 항목이 달라 한 번에 섞어 비교하지 "
                    "않습니다. DC형, IRP, 연금저축 중 하나를 지정해 주세요."
                ),
                data_mode="blocked",
                limitations=["계좌별 공시 계약을 분리해 조회합니다."],
            )
        if reason == BlockedReason.UNSUPPORTED_NEWS_TOPIC:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "현재 뉴스 기능은 한국·미국 주요 증시뉴스만 제공합니다. "
                    "연금·특정 기업별 뉴스는 증시뉴스로 바꿔 답하지 않습니다."
                ),
                data_mode="unavailable",
                limitations=[
                    "증시 뉴스, 한국 증시 뉴스 또는 미국 증시 뉴스로 질문해 주세요."
                ],
            )
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "현재 MVP는 연금계좌 규칙, 목계좌 진단, 과거 공시와 뉴스 "
                "근거 조회에 답할 수 있습니다. 질문에 계좌 유형이나 진단할 "
                "목시나리오를 포함해 주세요."
            ),
            data_mode="safe_fallback",
            limitations=["범용 투자·세무·법률 상담은 지원하지 않습니다."],
        )

    def _account_rule_response(
        self, request: ChatRequest, plan: QueryPlan
    ) -> ChatResponse:
        matches = self._knowledge.search_knowledge(request.message, limit=3)
        sources = _knowledge_sources(matches)
        if not matches:
            return ChatResponse(
                intent=ChatIntent.ACCOUNT_RULE,
                answer="검증된 근거 문서를 찾지 못해 답변을 생성하지 않았습니다.",
                data_mode="verified_knowledge",
                limitations=["질문을 계좌 유형과 함께 더 구체적으로 입력해 주세요."],
            )

        risk_question = "위험자산" in request.message or "한도" in request.message
        has_retirement_account = bool(
            {AccountType.DC, AccountType.IRP}.intersection(plan.account_types)
        )
        has_pension_savings = AccountType.PENSION_SAVINGS in plan.account_types
        numeric: list[NumericEvidence] = []
        if plan.combines_account_rules and risk_question:
            answer = (
                "계좌가 여러 개면 헷갈릴 수 있어요. 위험자산 기준은 여러 "
                "연금계좌를 합쳐서 보지 않고, 계좌마다 따로 확인해요. DC와 "
                "IRP는 각 계좌에서 위험자산을 계좌 돈의 70%까지만 담을 수 "
                "있고, 연금저축펀드에는 같은 비율 제한이 없어요."
            )
            numeric.append(
                NumericEvidence(
                    label="DC형·IRP 계좌별 일반 위험자산 한도",
                    value=Decimal("70"),
                    unit="%",
                    evidence_id=sources[0].evidence_id,
                    basis="검증된 계좌별 규칙",
                )
            )
        elif risk_question and has_pension_savings and not has_retirement_account:
            answer = (
                "연금저축펀드는 DC와 IRP처럼 위험자산 비율을 제한하지 않아요. "
                "대신 원하는 상품을 담을 수 있는지는 따로 확인해야 해요."
            )
        elif risk_question and has_retirement_account:
            answer = (
                "DC와 IRP에서는 위험자산을 계좌 돈의 70%까지만 담을 수 "
                "있습니다. 위험자산은 주식처럼 가격이 오르내릴 수 있는 "
                "자산입니다. 적격 TDF와 일부 "
                "디폴트옵션은 별도 기준이 적용될 수 있습니다. 연금저축펀드에는 "
                "이 비율 제한이 없지만, 담을 수 있는 상품인지는 확인이 필요합니다."
            )
            numeric.append(
                NumericEvidence(
                    label="DC형·IRP 계좌별 일반 위험자산 한도",
                    value=Decimal("70"),
                    unit="%",
                    evidence_id=sources[0].evidence_id,
                    basis="검증된 계좌 규칙",
                )
            )
        elif has_pension_savings and self._is_eligibility_question(request.message):
            answer = (
                "연금저축에서는 특정 상품을 편입할 수 있는지 상품별 적격성으로 "
                "확인해야 합니다. 현재 챗봇에는 공식 상품 식별자·적격성 데이터가 "
                "없어 개별 상품의 편입 가능 여부를 확정하지 않습니다."
            )
        else:
            excerpt = re.sub(r"\s+", " ", matches[0].content).strip()[:600]
            answer = f"검증 문서에서 확인한 내용입니다. {excerpt}"
            for index, (value, unit) in enumerate(
                sorted(extract_numeric_claims(answer)), start=1
            ):
                numeric.append(
                    NumericEvidence(
                        label=f"{matches[0].title} 답변 수치 {index}",
                        value=value,
                        unit=unit,
                        evidence_id=sources[0].evidence_id,
                        basis="검증된 지식 문서 답변 인용",
                    )
                )

        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer=answer,
            data_mode="verified_knowledge",
            sections=[
                AnswerSection(
                    kind=SectionKind.FACT,
                    title="검색된 근거",
                    content=re.sub(r"\s+", " ", match.content).strip()[:800],
                    evidence_ids=[f"knowledge:{match.chunk_id}"],
                )
                for match in matches
            ],
            sources=sources,
            numeric_evidence=numeric,
            limitations=["상품별 적격성은 공식 상품 데이터로 별도 확인해야 합니다."],
        )

    @staticmethod
    def _pension_account_overview_response() -> ChatResponse:
        return build_pension_account_overview_response()

    @staticmethod
    def _is_eligibility_question(message: str) -> bool:
        return any(term in message for term in ("편입", "적격", "가능한 상품"))

    def _custom_portfolio(self, request: ChatRequest) -> ChatResponse:
        assert request.portfolio is not None
        evaluation = evaluate_risk_cap(request.portfolio)
        source = SourceEvidence(
            evidence_id="engine:risk_cap",
            label=evaluation.evidence[0].source.label,
            locator=evaluation.evidence[0].source.reference,
            as_of=evaluation.evidence[0].source.as_of,
            publisher="연금 코파일럿 규칙 엔진",
            data_boundary=DataBoundary.ENGINE,
        )
        ratio = _decimal_text(evaluation.general_risky_ratio_percent)
        if evaluation.limit_percent is None:
            answer = (
                f"입력한 연금저축 목포트폴리오의 일반 위험자산 비중은 {ratio}%입니다. "
                "DC형·IRP의 총량 한도는 적용하지 않고 상품 적격성을 별도로 "
                "확인해야 합니다."
            )
        else:
            status_text = "한도 이내" if evaluation.within_limit else "한도 초과"
            answer = (
                f"입력한 {evaluation.evaluated_input.account_type.value.upper()} "
                f"목포트폴리오의 일반 위험자산 비중은 {ratio}%이며 {status_text}입니다."
            )
        numeric = [
            NumericEvidence(
                label="일반 위험자산 비중",
                value=evaluation.general_risky_ratio_percent,
                unit="%",
                evidence_id=source.evidence_id,
                basis="규칙 엔진 계산",
            )
        ]
        if evaluation.limit_percent is not None:
            numeric.append(
                NumericEvidence(
                    label="일반 위험자산 한도",
                    value=evaluation.limit_percent,
                    unit="%",
                    evidence_id=source.evidence_id,
                    basis="버전형 계좌 규칙",
                )
            )
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=answer,
            data_mode="request_mock",
            sources=[source],
            numeric_evidence=numeric,
            engine_results=[evaluation],
            limitations=["입력 포트폴리오는 실제 계좌가 아닌 목데이터로 처리했습니다."],
        )

    @staticmethod
    def _completed_survey_required() -> ChatResponse:
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                "완료된 투자성향 설문 결과를 찾지 못했습니다. "
                "프로필에서 설문을 완료한 뒤 투자전략을 다시 요청해 주세요."
            ),
            data_mode="survey_required",
            limitations=[
                "챗봇 대화에서는 나이와 수령 나이를 다시 수집하지 않습니다.",
                "설문 결과가 연결되기 전에는 규칙 엔진을 호출하지 않습니다.",
            ],
        )

    @staticmethod
    def _risk_profile_selection_guide() -> ChatResponse:
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                "투자성향은 안정형, 안정추구형, 위험중립형, 적극투자형, "
                "공격투자형의 다섯 유형으로 구분합니다. 원하는 유형을 하나 "
                "선택해 말해 주세요."
            ),
            data_mode="risk_profile_selection",
            sections=[
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="투자성향 선택",
                    content=(
                        "안정형: 원금 보전과 낮은 변동성을 우선합니다.\n"
                        "안정추구형: 채권 중심으로 운용하되 제한적으로 "
                        "위험자산을 활용합니다.\n"
                        "위험중립형: 성장성과 안정성의 균형을 추구합니다.\n"
                        "적극투자형: 주식 비중을 높여 장기 성장을 추구합니다.\n"
                        "공격투자형: 높은 변동성을 감수하고 성장·전술자산을 "
                        "적극적으로 활용합니다.\n\n"
                        "예: 위험중립형으로 ETF 포트폴리오를 보여줘"
                    ),
                )
            ],
            limitations=[
                "완료된 설문 결과보다 위험한 투자성향의 포트폴리오는 "
                "제안하지 않습니다.",
                "투자성향을 선택하기 전에는 ETF 포트폴리오를 계산하지 않습니다.",
            ],
        )

    @staticmethod
    def _risk_profile_guardrail(
        *,
        assessed_profile: EducationalRiskProfile,
        requested_profile: EducationalRiskProfile,
    ) -> ChatResponse:
        assessed_label = _RISK_PROFILE_LABELS[assessed_profile.value]
        requested_label = _RISK_PROFILE_LABELS[requested_profile.value]
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                f"설문 결과는 {assessed_label}입니다. {requested_label} ETF "
                "포트폴리오는 설문 성향보다 위험해 제안하지 않습니다. "
                f"{assessed_label} 또는 더 보수적인 투자성향을 선택해 주세요."
            ),
            data_mode="profile_guardrail",
            limitations=[
                "설문에서 확인된 투자성향보다 위험한 상품 구성은 제안하지 않습니다."
            ],
        )

    def _educational_portfolio(
        self, request: EducationalPortfolioInput
    ) -> ChatResponse:
        account_label = _ACCOUNT_TYPE_LABELS[request.account_type]
        if self._portfolio_universe_loader is None:
            return ChatResponse(
                intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
                answer=(
                    f"{account_label} 계좌용 교육 포트폴리오 데이터 저장소가 "
                    "연결되지 않았습니다."
                ),
                data_mode="unavailable",
                limitations=[
                    f"{account_label} 계좌 결과를 임의 수치로 대신 계산하지 않았습니다."
                ],
            )
        try:
            repository = self._portfolio_universe_loader(request.account_type)
            evaluation = build_educational_portfolio(
                request,
                products=repository.products,
                histories=repository.histories,
                history_sources=repository.history_sources,
                source_as_of=repository.as_of,
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            logger.warning(
                "Educational portfolio data unavailable for account=%s: %s",
                request.account_type.value,
                exc,
            )
            missing_master = isinstance(
                exc, FileNotFoundError
            ) and "no cost-return master" in str(exc)
            unavailable_reason = (
                "ETF 비용·수익률 마스터가 서버에 준비되지 않았습니다."
                if missing_master
                else "ETF 입력 데이터 검증에 실패했습니다."
            )
            return ChatResponse(
                intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
                answer=(
                    f"{account_label} 계좌용 {unavailable_reason} "
                    "포트폴리오 결과를 만들지 않았습니다."
                ),
                data_mode="unavailable",
                limitations=[
                    f"{account_label} 계좌의 누락값을 추정하거나 수익률을 "
                    "계산하지 않았습니다."
                ],
            )

        engine_source = SourceEvidence(
            evidence_id="engine:educational_portfolio",
            label="교육용 연금 포트폴리오 규칙 엔진",
            locator=(f"engine://{evaluation.engine_name}/{evaluation.engine_version}"),
            publisher="연금 코파일럿 규칙 엔진",
            as_of=repository.as_of,
            data_boundary=DataBoundary.ENGINE,
        )
        cma_chip = evaluation.planning_return.sources[0]
        cma_source = SourceEvidence(
            evidence_id="policy:cma",
            label=cma_chip.label,
            locator=cma_chip.reference,
            publisher="J.P. Morgan Asset Management",
            as_of=cma_chip.as_of,
            data_boundary=DataBoundary.ENGINE,
        )
        sources = [engine_source, cma_source]
        displayed_risk_target = _one_decimal(
            evaluation.final_general_risk_target_percent
        )
        numeric = [
            NumericEvidence(
                label="수령 개시까지 운용기간",
                value=Decimal(evaluation.planning_horizon_years),
                unit="년",
                evidence_id=engine_source.evidence_id,
                basis="수령 개시 나이에서 현재 나이를 차감한 엔진 계산",
            ),
            NumericEvidence(
                label="일반 위험자산 목표비중",
                value=displayed_risk_target,
                unit="%",
                evidence_id=engine_source.evidence_id,
                basis="계좌 한도·성향·손실감내력을 반영한 엔진 계산",
            ),
        ]
        numeric.extend(
            NumericEvidence(
                label=f"{_SLEEVE_LABELS[target.sleeve]} 목표비중",
                value=_one_decimal(target.target_percent),
                unit="%",
                evidence_id=engine_source.evidence_id,
                basis=f"{target.role} 엔진 슬리브 배분",
            )
            for target in evaluation.target_sleeves
        )
        rebalancing_threshold = _one_decimal(
            evaluation.rebalancing.drift_threshold_percent_points
        )
        numeric.append(
            NumericEvidence(
                label="리밸런싱 이탈 기준",
                value=rebalancing_threshold,
                unit="%",
                evidence_id=engine_source.evidence_id,
                basis="규칙 엔진의 목표비중 이탈 허용 기준",
            )
        )
        planning = evaluation.planning_return
        planning_text = "검증된 계획수익률 범위를 산출하지 못했습니다."
        if (
            planning.conservative_planning_return_percent is not None
            and planning.base_planning_return_percent is not None
        ):
            conservative = _one_decimal(planning.conservative_planning_return_percent)
            base = _one_decimal(planning.base_planning_return_percent)
            numeric.extend(
                [
                    NumericEvidence(
                        label="보수 계획수익률",
                        value=conservative,
                        unit="%",
                        evidence_id=engine_source.evidence_id,
                        basis="CMA·비용·불확실성 할인을 반영한 엔진 계산",
                    ),
                    NumericEvidence(
                        label="기준 계획수익률",
                        value=base,
                        unit="%",
                        evidence_id=engine_source.evidence_id,
                        basis="CMA와 비용을 반영한 엔진 계산",
                    ),
                ]
            )
            planning_text = (
                "CMA 기반 연간 계획수익률 범위는 보수 약 "
                f"{_decimal_text(conservative)}%에서 기준 약 "
                f"{_decimal_text(base)}%입니다. "
                "미래 예측값이 아니라 매년 재검토하는 장기 배분 가정입니다."
            )
        profile_label = _RISK_PROFILE_LABELS[
            evaluation.evaluated_input.risk_profile.value
        ]
        strategy_content = (
            f"{_strategy_summary(evaluation)}\n\n"
            f"목표 포트폴리오\n{_target_portfolio_summary(evaluation)}\n\n"
            f"운용 원칙\n{_rebalancing_summary(evaluation)}"
        )
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{profile_label} 투자전략",
                content=strategy_content,
                evidence_ids=[engine_source.evidence_id],
            ),
            AnswerSection(
                kind=SectionKind.FACT,
                title="장기 계획수익률",
                content=planning_text,
                evidence_ids=[
                    engine_source.evidence_id,
                    cma_source.evidence_id,
                ],
            ),
        ]
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                "완료된 설문 결과에 맞춰 투자스타일별 상세 전략과 "
                "장기 계획수익률을 정리했습니다."
            ),
            data_mode="engine_educational_planning",
            sources=sources,
            numeric_evidence=numeric,
            sections=sections,
            educational_portfolio_evaluation=evaluation,
            educational_portfolio_evaluations=[evaluation],
            limitations=[
                "설명은 규칙 엔진 결과 코드와 수치만 정해진 문장으로 변환합니다.",
                "CMA는 10~15년 전략배분 기준이며 매년 재검토합니다.",
                "상품 선택·주문·자동 리밸런싱은 수행하지 않습니다.",
            ],
        )

    def _educational_portfolios(
        self, requests: list[EducationalPortfolioInput]
    ) -> ChatResponse:
        responses = [self._educational_portfolio(request) for request in requests]
        if len(responses) == 1:
            return responses[0]
        if any(
            response.educational_portfolio_evaluation is None for response in responses
        ):
            unavailable = [
                response.answer
                for response in responses
                if response.educational_portfolio_evaluation is None
            ]
            limitations = list(
                dict.fromkeys(
                    limitation
                    for response in responses
                    for limitation in response.limitations
                )
            )
            limitations.append("계좌별 규칙을 섞거나 누락값을 추정하지 않았습니다.")
            return ChatResponse(
                intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
                answer=(
                    "복수 계좌 포트폴리오를 만들지 않았습니다.\n"
                    + "\n".join(f"- {item}" for item in unavailable)
                ),
                data_mode="unavailable",
                limitations=limitations,
            )

        account_names = "와 ".join(
            _ACCOUNT_TYPE_LABELS[request.account_type] for request in requests
        )
        first_request = requests[0]
        profile_label = _RISK_PROFILE_LABELS[first_request.risk_profile.value]
        survey_source = SourceEvidence(
            evidence_id="user:completed_survey_profile",
            label="완료된 MVP 투자성향 설문",
            locator="request://survey_profile",
            data_boundary=DataBoundary.USER_INPUT,
        )
        sources: dict[str, SourceEvidence] = {survey_source.evidence_id: survey_source}
        numeric: list[NumericEvidence] = [
            NumericEvidence(
                label="현재 나이",
                value=Decimal(first_request.age),
                unit="세",
                evidence_id=survey_source.evidence_id,
                basis="완료된 MVP 설문 입력",
            ),
            NumericEvidence(
                label="연금수령 개시 나이",
                value=Decimal(first_request.retirement_start_age),
                unit="세",
                evidence_id=survey_source.evidence_id,
                basis="완료된 MVP 설문 입력",
            ),
            NumericEvidence(
                label="손실감내율",
                value=first_request.loss_tolerance_percent,
                unit="%",
                evidence_id=survey_source.evidence_id,
                basis="완료된 MVP 설문 입력",
            ),
        ]
        sections: list[AnswerSection] = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="적용한 MVP 설문 조건",
                content=(
                    f"현재 나이 {first_request.age}세, 연금수령 개시 "
                    f"{first_request.retirement_start_age}세, 투자성향 "
                    f"{profile_label}, 손실감내율 약 "
                    f"{_decimal_text(first_request.loss_tolerance_percent)}%를 "
                    f"적용했습니다. 보유 계좌는 {account_names}이며 계좌별 "
                    "규칙을 각각 계산합니다."
                ),
                evidence_ids=[survey_source.evidence_id],
            )
        ]
        evaluations: list[EducationalPortfolioEvaluation] = []
        limitations: list[str] = []
        for request, response in zip(requests, responses, strict=True):
            account_label = _ACCOUNT_TYPE_LABELS[request.account_type]
            evidence_ids = {
                source.evidence_id: (
                    f"{source.evidence_id}:{request.account_type.value}"
                )
                for source in response.sources
            }
            for source in response.sources:
                remapped = source.model_copy(
                    update={
                        "evidence_id": evidence_ids[source.evidence_id],
                        "label": f"{source.label} ({account_label})",
                    }
                )
                sources[remapped.evidence_id] = remapped
            numeric.extend(
                item.model_copy(
                    update={
                        "label": f"{account_label} · {item.label}",
                        "evidence_id": evidence_ids[item.evidence_id],
                    }
                )
                for item in response.numeric_evidence
            )
            sections.extend(
                section.model_copy(
                    update={
                        "title": f"{account_label} · {section.title}",
                        "evidence_ids": [
                            evidence_ids[evidence_id]
                            for evidence_id in section.evidence_ids
                        ],
                    }
                )
                for section in response.sections
            )
            assert response.educational_portfolio_evaluation is not None
            evaluations.append(response.educational_portfolio_evaluation)
            limitations.extend(response.limitations)

        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                f"{account_names}의 계좌 규칙을 각각 적용해 ETF 포트폴리오와 "
                "장기 계획수익률을 정리했습니다."
            ),
            data_mode="engine_multi_account_planning",
            sources=list(sources.values()),
            numeric_evidence=numeric,
            sections=sections,
            educational_portfolio_evaluation=evaluations[0],
            educational_portfolio_evaluations=evaluations,
            limitations=list(dict.fromkeys(limitations)),
        )

    def _scenario_response(self, scenario_code: str) -> ChatResponse:
        scenario = self._scenarios.get(scenario_code)
        if scenario is None:
            return self._scenario_selection_response(
                limitation=f"알 수 없는 목시나리오 코드: {scenario_code}"
            )
        evaluation = evaluate_mock_scenario(scenario)
        sources = [
            SourceEvidence(
                evidence_id="mock:scenario",
                label=evaluation.source.label,
                locator=evaluation.source.reference,
                as_of=evaluation.source.as_of,
                data_boundary=DataBoundary.MOCK,
            ),
            SourceEvidence(
                evidence_id="engine:scenario",
                label="목계좌 통합 집계 엔진",
                locator=f"engine://{evaluation.engine_name}/{evaluation.engine_version}",
                as_of=evaluation.source.as_of,
                data_boundary=DataBoundary.ENGINE,
            ),
        ]
        account_lines: list[str] = []
        numeric = [
            NumericEvidence(
                label="목시나리오 총자산",
                value=evaluation.total_amount_krw,
                unit="KRW",
                evidence_id="engine:scenario",
                basis="목계좌 합산",
            )
        ]
        for result in evaluation.account_evaluations:
            account_code = result.evaluated_input.account_type.value
            account_name = _ACCOUNT_TYPE_LABELS[account_code]
            if result.limit_percent is None:
                account_lines.append(
                    f"{account_name} 계좌는 담을 수 있는 상품을 별도로 확인합니다"
                )
            else:
                status_text = (
                    "기준 안에 있습니다" if result.within_limit else "기준을 넘었습니다"
                )
                account_lines.append(
                    f"{account_name} 계좌의 위험자산 비중은 {status_text}"
                )
            numeric.append(
                NumericEvidence(
                    label=f"{account_name} 일반 위험자산 비중",
                    value=result.general_risky_ratio_percent,
                    unit="%",
                    evidence_id="engine:scenario",
                    basis="규칙 엔진 계산",
                )
            )
        for item in evaluation.asset_allocations:
            asset_name = _ASSET_CLASS_LABELS[item.asset_class_code]
            numeric.append(
                NumericEvidence(
                    label=f"{asset_name} 통합 자산 비중",
                    value=item.allocation_percent,
                    unit="%",
                    evidence_id="engine:scenario",
                    basis="목계좌 통합 집계 엔진 계산",
                )
            )
        duplicate_text = (
            ", ".join(
                _ASSET_CLASS_LABELS[asset]
                for asset in evaluation.duplicated_asset_classes
            )
            if evaluation.duplicated_asset_classes
            else None
        )
        account_summary = ". ".join(account_lines)
        duplicate_summary = (
            f"여러 계좌에 {duplicate_text}이 겹쳐 있는 점을 먼저 확인해 보세요."
            if duplicate_text
            else "계좌 간 같은 자산군의 중복은 확인되지 않았습니다."
        )
        answer = (
            f"좋아요, 하나씩 같이 볼게요. {account_summary}. "
            f"자산별 비중은 아래 그래프로 확인해 보세요. {duplicate_summary}"
        )
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=answer,
            data_mode="mock_scenario",
            sections=[
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="계좌별 확인",
                    content=account_summary,
                    evidence_ids=["engine:scenario"],
                ),
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="자산 구성 그래프 안내",
                    content=duplicate_summary,
                    evidence_ids=["mock:scenario", "engine:scenario"],
                ),
            ],
            sources=sources,
            numeric_evidence=numeric,
            engine_results=evaluation.account_evaluations,
            scenario_evaluation=evaluation,
            limitations=["모든 계좌와 보유자산은 발표용 목데이터입니다."],
        )

    def _scenario_selection_response(
        self, limitation: str | None = None
    ) -> ChatResponse:
        names = ", ".join(item.code for item in self._scenarios.list())
        limitations = [limitation] if limitation else []
        limitations.append("진단할 scenario_code를 요청에 지정해 주세요.")
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=f"사용 가능한 목시나리오는 {names}입니다.",
            data_mode="mock_scenario_selection",
            limitations=limitations,
        )

    def _disclosure_response(
        self, request: ChatRequest, account_type: AccountType
    ) -> ChatResponse:
        if self._disclosures is None:
            return ChatResponse(
                intent=ChatIntent.PROVIDER_DISCLOSURE,
                answer=(
                    "원격 Supabase 실공시 적재가 확인되지 않아 회사·사업자 수치를 "
                    "표시하지 않았습니다. fixture를 실데이터로 대신하지 않습니다."
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
                answer="조건에 맞는 최신 실공시 행을 찾지 못했습니다.",
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
            current = (
                "공시값 없음"
                if row.earn_rate_current_pct is None
                else f"{_decimal_text(row.earn_rate_current_pct)}%"
            )
            three_year = (
                "공시값 없음"
                if row.avg_earn_rate_3y_pct is None
                else f"{_decimal_text(row.avg_earn_rate_3y_pct)}%"
            )
            lines.append(
                f"{row.company_name}: 당기 과거 수익률 {current}, "
                f"3년 연환산 {three_year}"
            )
            for label, value in (
                ("당기 과거 수익률", row.earn_rate_current_pct),
                ("3년 연환산 수익률", row.avg_earn_rate_3y_pct),
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
            answer=" / ".join(lines),
            data_mode="official_disclosure",
            sections=[
                AnswerSection(
                    kind=SectionKind.FACT,
                    title="회사·사업자 과거 공시",
                    content=" / ".join(lines),
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
    ) -> ChatResponse:
        if self._news is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "저장된 뉴스 메타데이터가 없어 최신 뉴스 답변을 "
                    "생성하지 않았습니다."
                ),
                data_mode="unavailable",
                limitations=["NAVER 뉴스 수집과 DATABASE_URL이 필요합니다."],
            )
        is_market_news = search_query == "market" or search_query.startswith("market:")
        region = search_query.partition(":")[2] or None
        market_limit = min(max_results, 3)
        if is_market_news and exclude_item_ids:
            matches = self._news.recent_market_news(
                region=region,
                days=5,
                limit=market_limit,
                exclude_item_ids=exclude_item_ids,
            )
        elif is_market_news:
            matches = self._news.recent_market_news(
                region=region, days=5, limit=market_limit
            )
        else:
            matches = self._news.latest_news(search_query, limit=request.max_results)
        if not matches:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "최근 닷새간 요약이 완료된 증시 뉴스를 찾지 못했습니다."
                    if is_market_news
                    else "해당 검색어로 저장된 뉴스 메타데이터를 찾지 못했습니다."
                ),
                data_mode="news_summary" if is_market_news else "news_metadata",
                limitations=["기사 본문을 임의로 생성하지 않습니다."],
            )
        sources = [
            SourceEvidence(
                evidence_id=f"news:{item.item_id}",
                label=item.title,
                locator=item.original_url,
                publisher=item.publisher or "외부 뉴스 원문",
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
            limitations.append("증시 뉴스는 한 번에 최대 세 건까지 제공합니다.")
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer="\n\n".join(lines),
            data_mode="news_summary" if is_market_news else "news_metadata",
            news_items=[
                ChatNewsItem(
                    evidence_id=f"news:{item.item_id}",
                    title=item.title,
                    publisher=item.publisher,
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
            conversation_context=ConversationContext(
                news=NewsConversationContext(
                    news_item_ids=[item.item_id for item in matches],
                    market_region=(
                        MarketRegion(region) if region is not None else MarketRegion.ALL
                    ),
                    shown_at=datetime.now(UTC),
                )
            ),
        )

    def _news_follow_up_response(
        self, request: ChatRequest, follow_up: NewsFollowUp
    ) -> ChatResponse:
        context = request.conversation_context
        news_context = context.news if context is not None else None
        if news_context is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer="현재 세션에서 먼저 표시된 증시뉴스가 없습니다.",
                data_mode="news_follow_up",
                limitations=["먼저 증시뉴스를 요청해 주세요."],
            )
        if follow_up.action == NewsFollowUpAction.CLARIFY:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "현재 세션에는 뉴스 "
                    f"{len(news_context.news_item_ids)}건이 있습니다. "
                    "첫 번째, 두 번째처럼 확인할 기사를 지정해 주세요."
                ),
                data_mode="news_follow_up",
                limitations=["여러 기사 중 대상을 임의로 선택하지 않습니다."],
                conversation_context=ConversationContext(news=news_context),
            )
        if self._news is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer="저장된 뉴스 데이터에 연결할 수 없습니다.",
                data_mode="unavailable",
                limitations=["DATABASE_URL과 저장된 뉴스 데이터가 필요합니다."],
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
                    "세션에서 참조한 뉴스가 현재 저장소에 없어 내용을 다시 불러오지 "
                    "못했습니다. 최신 증시뉴스를 다시 요청해 주세요."
                ),
                data_mode="unavailable",
                limitations=["삭제되거나 만료된 뉴스 내용을 임의로 복원하지 않습니다."],
                conversation_context=ConversationContext(news=news_context),
            )

        sources = [
            SourceEvidence(
                evidence_id=f"news:{item.item_id}",
                label=item.title,
                locator=item.original_url,
                publisher=item.publisher or "외부 뉴스 원문",
                as_of=item.published_at,
                data_boundary=DataBoundary.NEWS_SUMMARY,
            )
            for _, item in ordered
        ]
        if follow_up.action == NewsFollowUpAction.SOURCE:
            def published_date(item: NewsMatch) -> str:
                return (
                    item.published_at.date().isoformat()
                    if item.published_at
                    else "확인되지 않음"
                )

            lines = [
                (
                    f"{index + 1}번째 뉴스 — {item.title}\n"
                    f"발행일: {published_date(item)}\n"
                    f"원문 링크: {item.original_url}"
                )
                for index, item in ordered
            ]
            title = "뉴스 출처와 발행일"
        else:
            lines = [_news_summary_block(item, index) for index, item in ordered]
            title = (
                "세션 뉴스 비교"
                if follow_up.action == NewsFollowUpAction.COMPARE
                else "선택한 뉴스 다시 보기"
            )
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
                    publisher=item.publisher,
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
                "이 세션에서 앞서 보여드린 뉴스만 다시 조회했습니다.",
                "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 합니다.",
            ],
            conversation_context=ConversationContext(news=updated_news_context),
        )

    @staticmethod
    def _scenario_code(message: str) -> str | None:
        return next(
            (code for keyword, code in SCENARIO_KEYWORDS.items() if keyword in message),
            None,
        )
