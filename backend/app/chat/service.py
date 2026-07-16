import re
from datetime import date
from decimal import Decimal
from typing import Protocol

from ..engine import (
    AccountType,
    NonPensionWithdrawalEvaluation,
    PensionTaxCreditEvaluation,
    PensionTaxToolResult,
    WithdrawalCalculationStatus,
    evaluate_mock_scenario,
    evaluate_risk_cap,
)
from ..retrieval.repository import KnowledgeMatch, NewsMatch
from .disclosures import ProviderDisclosure
from .models import (
    AnswerSection,
    ChatCapabilities,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    ChatVisualization,
    ConversationContext,
    DataBoundary,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
    VisualizationDatum,
    VisualizationDatumRole,
    VisualizationKind,
    extract_numeric_claims,
)
from .pension_tax_parser import resolve_pension_tax_inputs
from .query_planner import BlockedReason, QueryPlan, plan_question
from .routing import IntentRouter
from .scenarios import LocalScenarioRepository
from .tools import (
    PENSION_TAX_CLOSING_NOTICE,
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)


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


SCENARIO_KEYWORDS = {
    "방치": "dc_dormant",
    "세액공제": "tax_contribution_uninvested",
    "미운용": "tax_contribution_uninvested",
    "중복": "overlap_risk_concentration",
    "편중": "overlap_risk_concentration",
}
VERIFIED_AS_OF = date(2026, 7, 13)

_ACCOUNT_TYPE_LABELS = {
    "dc": "DC",
    "irp": "IRP",
    "pension_savings": "연금저축펀드",
}
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


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _knowledge_sources(matches: list[KnowledgeMatch]) -> list[SourceEvidence]:
    return [
        SourceEvidence(
            evidence_id=f"knowledge:{match.chunk_id}",
            label=match.title,
            locator=match.source_url,
            publisher="연금 코파일럿 검증 지식",
            as_of=VERIFIED_AS_OF,
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
        scenarios: LocalScenarioRepository,
        disclosures: DisclosureSearch | None = None,
        news: NewsSearch | None = None,
        router: IntentRouter | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scenarios = scenarios
        self._disclosures = disclosures
        self._news = news
        self._router = router or IntentRouter()

    def capabilities(self) -> ChatCapabilities:
        return ChatCapabilities(
            supported=[
                "DC형·IRP·연금저축 계좌 규칙 근거 Q&A",
                "목계좌 시나리오 위험자산 한도와 통합 자산군 진단",
                "연금저축·IRP 당해연도 납입액 세액공제 간이 계산",
                "연금저축·IRP 연금외수령 16.5% 간이 추정",
                "근거·기준일·실데이터/목데이터 경계 표시",
            ],
            conditional=[
                "Supabase 실적재 후 회사·사업자 과거 공시 비교",
                "NAVER 뉴스 적재 후 최신 뉴스 메타데이터 조회",
            ],
            unsupported=[
                "DC·IRP 개별 상품 비교",
                "미래 수익률·목표가 예측",
                "주문·자동운용",
            ],
            scenario_codes=[item.code for item in self._scenarios.list()],
        )

    def plan(self, request: ChatRequest) -> QueryPlan:
        direct_plan = plan_question(
            request.message, default_max_results=request.max_results
        )
        if direct_plan.blocked_reason != BlockedReason.UNSUPPORTED:
            return direct_plan
        contextual_message = self._router.contextual_message(request)
        if contextual_message == request.message:
            return direct_plan
        return plan_question(
            contextual_message, default_max_results=request.max_results
        )

    def ask(
        self, request: ChatRequest, *, plan: QueryPlan | None = None
    ) -> ChatResponse:
        original_request = request
        resolved_plan = plan or self.plan(request)
        if resolved_plan.blocked_reason is not None and not (
            resolved_plan.blocked_reason == BlockedReason.UNSUPPORTED
            and (request.portfolio is not None or request.scenario_code is not None)
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
            elif resolved_plan.intent == ChatIntent.PENSION_TAX:
                response = self._pension_tax_response(request, resolved_plan)
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
                response = self._news_response(
                    request, search_query=resolved_plan.news_query
                )
            elif resolved_plan.intent == ChatIntent.PROVIDER_DISCLOSURE:
                account_type = resolved_plan.account_types[0]
                response = self._disclosure_response(request, account_type)
            elif resolved_plan.intent == ChatIntent.ACCOUNT_RULE:
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
        account_type = (
            plan.account_types[0]
            if len(plan.account_types) == 1
            else request.portfolio.account_type
            if request.portfolio is not None
            else previous.account_type
            if previous is not None
            else None
        )
        scenario_code = (
            request.scenario_code
            or (previous.scenario_code if previous is not None else None)
        )
        return response.model_copy(
            update={
                "conversation_context": ConversationContext(
                    account_type=account_type,
                    scenario_code=scenario_code,
                    last_intent=response.intent,
                )
            }
        )

    def _pension_tax_response(
        self, request: ChatRequest, plan: QueryPlan
    ) -> ChatResponse:
        resolved_inputs = resolve_pension_tax_inputs(
            request.message, request.pension_tax
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
            tax_credit = calculate_pension_tax_credit_tool(
                resolved_inputs.tax_credit
            )
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

        return ChatResponse(
            intent=ChatIntent.PENSION_TAX,
            answer=" ".join(answer_parts) + f"\n{PENSION_TAX_CLOSING_NOTICE}",
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
            *(
                result.tax_credit.evidence
                if result.tax_credit is not None
                else []
            ),
            *(
                result.withdrawal.evidence
                if result.withdrawal is not None
                else []
            ),
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
    def _withdrawal_text(
        cls, result: NonPensionWithdrawalEvaluation
    ) -> str:
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
                answer="미래 수익률은 제공하지 않습니다.",
                data_mode="blocked",
                limitations=["미래 수익 예측은 MVP 범위 밖입니다."],
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
                    "기준 안에 있습니다"
                    if result.within_limit
                    else "기준을 넘었습니다"
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
        self, request: ChatRequest, *, search_query: str
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
        is_pension_news = search_query == "연금"
        matches = (
            self._news.random_recent_news(search_query, days=5, limit=3)
            if is_pension_news
            else self._news.latest_news(search_query, limit=request.max_results)
        )
        if not matches:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "최근 닷새간 저장된 연금 뉴스 메타데이터를 찾지 못했습니다."
                    if is_pension_news
                    else "해당 검색어로 저장된 뉴스 메타데이터를 찾지 못했습니다."
                ),
                data_mode="news_metadata",
                limitations=["기사 본문을 임의로 생성하지 않습니다."],
            )
        sources = [
            SourceEvidence(
                evidence_id=f"news:{item.item_id}",
                label=item.title,
                locator=item.original_url,
                publisher="외부 뉴스 원문",
                as_of=item.published_at,
                data_boundary=DataBoundary.NEWS_METADATA,
            )
            for item in matches
        ]
        lines = [_news_metadata_line(item) for item in matches]
        limitations = [
            "기사 본문이 아닌 제목·요약·원문 링크 메타데이터입니다.",
            "뉴스 사실과 외부 의견은 원문에서 다시 확인해야 합니다.",
        ]
        if is_pension_news and len(matches) < 3:
            limitations.append(
                "최근 닷새간 저장된 기사가 세 건 미만이라 조회된 기사만 제공합니다."
            )
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=" / ".join(lines),
            data_mode="news_metadata",
            sections=[
                AnswerSection(
                    kind=SectionKind.EXTERNAL_OPINION,
                    title=(
                        "최근 닷새 연금 뉴스 메타데이터"
                        if is_pension_news
                        else "뉴스 검색 메타데이터"
                    ),
                    content=" / ".join(lines),
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            limitations=limitations,
        )

    @staticmethod
    def _scenario_code(message: str) -> str | None:
        return next(
            (code for keyword, code in SCENARIO_KEYWORDS.items() if keyword in message),
            None,
        )
