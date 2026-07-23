"""Response presentation, context, capabilities, and follow-up cards."""

from ..cards import build_suggested_follow_ups
from ..models import (
    ChatCapabilities,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    ChatVisualization,
    ConversationContext,
    DataBoundary,
    ReferentItem,
    ReferentList,
    VisualizationDatum,
    VisualizationDatumRole,
    VisualizationKind,
)
from ..query_planner import QueryPlan
from ..scenarios import ScenarioRepository
from ._shared import (
    _ACCOUNT_TYPE_LABELS,
    _ASSET_CLASS_LABELS,
    _SLEEVE_LABELS,
    _STRESS_SCENARIO_LABELS,
    _one_decimal,
)


def build_capabilities(*, scenarios: ScenarioRepository) -> ChatCapabilities:
    return ChatCapabilities(
        supported=[
            "DC형·IRP·연금저축 계좌 규칙 근거 Q&A",
            "목계좌 시나리오 위험자산 한도와 통합 자산군 진단",
            "연령·성향·수령개시연령별 교육용 포트폴리오 위험·계획가정",
            "ETF 테마 1~20의 구조·기회·위험 설명",
            "연금저축·IRP 당해연도 납입액 세액공제 간이 계산",
            "연금저축·IRP 연금외수령 16.5% 간이 추정",
            "근거·기준일·실데이터/목데이터 경계 표시",
            "한국은행·KOSIS·FRED 공식 거시지표 근거 조회",
            "실시간 NAVER 뉴스 이벤트·ETF 테마 분류",
        ],
        conditional=[
            "Supabase 실적재 후 회사·사업자 과거 공시 비교",
            "NAVER 증시뉴스 적재 후 매체·3줄 요약·원문 링크 조회",
            "투자성향·계좌 적격성·KIS 구성종목 근거가 갖춰진 테마 ETF 비교",
        ],
        unsupported=[
            "검증 범위 밖 테마와 적격성 미확인 상품 비교",
            "LLM의 미래 수익률·목표가 직접 예측",
            "주문·자동운용",
        ],
        scenario_codes=[item.code for item in scenarios.list()],
    )


def attach_visualizations(response: ChatResponse) -> ChatResponse:
    """Attach only views backed by the response's existing engine evidence."""

    visualizations: list[ChatVisualization] = []
    if response.scenario_evaluation is not None:
        evaluation = response.scenario_evaluation
        visualizations.append(
            ChatVisualization(
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
        )

    tax_credit = (
        response.pension_tax_result.tax_credit
        if response.pension_tax_result is not None
        else None
    )
    if tax_credit is not None and tax_credit.rate_determined:
        rate = tax_credit.rate_scenarios[0]
        visualizations.append(
            ChatVisualization(
                kind=VisualizationKind.TAX_SUMMARY,
                title="세액공제 요약",
                description="",
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
                    label="법정 세액공제액",
                    value=rate.income_tax_credit_krw,
                    unit="KRW",
                    role=VisualizationDatumRole.VALUE,
                ),
                VisualizationDatum(
                    label="지방세 포함 예상 절세효과",
                    value=rate.estimated_total_tax_reduction_effect_krw,
                    unit="KRW",
                    role=VisualizationDatumRole.VALUE,
                ),
                VisualizationDatum(
                    label="적용 세액공제율 (지방소득세 포함)",
                    value=rate.local_inclusive_display_rate_percent,
                    unit="%",
                    role=VisualizationDatumRole.VALUE,
                ),
                ],
            )
        )

    risk_items = [
        item
        for item in response.numeric_evidence
        if "위험자산 비중" in item.label or "위험자산 한도" in item.label
    ]
    if risk_items:
        visualizations.append(
            ChatVisualization(
                kind=VisualizationKind.RISK_CAP,
                title="위험자산 기준",
                description="현재 비중과 계좌 기준을 한눈에 비교해 보세요.",
                data_boundary=(
                    DataBoundary.ENGINE
                    if any(
                        item.evidence_id.startswith("engine:")
                        for item in risk_items
                    )
                    else DataBoundary.VERIFIED_KNOWLEDGE
                ),
                evidence_ids=list(
                    dict.fromkeys(item.evidence_id for item in risk_items)
                ),
                items=[
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
                ],
            )
        )

    for evaluation in response.educational_portfolio_evaluations:
        account_label = _ACCOUNT_TYPE_LABELS[
            evaluation.evaluated_input.account_type
        ]
        sleeve_label = _SLEEVE_LABELS[evaluation.target_sleeves[0].sleeve]
        evidence_id = next(
            item.evidence_id
            for item in response.numeric_evidence
            if item.evidence_id.startswith("engine:educational_portfolio")
            and item.label.endswith(f"{sleeve_label} 목표비중")
            and (
                len(response.educational_portfolio_evaluations) == 1
                or item.label.startswith(f"{account_label} · ")
            )
        )
        visualizations.append(
            ChatVisualization(
                kind=VisualizationKind.SLEEVE_ALLOCATION,
                title=f"{account_label} 목표 자산배분",
                description="규칙 엔진이 계산한 5개 슬리브 목표비중이에요.",
                data_boundary=DataBoundary.ENGINE,
                evidence_ids=[evidence_id],
                items=[
                    VisualizationDatum(
                        label=_SLEEVE_LABELS[target.sleeve],
                        value=_one_decimal(target.target_percent),
                        unit="%",
                        role=VisualizationDatumRole.SEGMENT,
                    )
                    for target in evaluation.target_sleeves
                ],
            )
        )
        stress_items = evaluation.portfolio_risk.stress_scenarios
        if stress_items:
            visualizations.append(
                ChatVisualization(
                    kind=VisualizationKind.STRESS_SCENARIOS,
                    title=f"{account_label} 스트레스 점검",
                    description="규칙 엔진의 스트레스 시나리오별 손실 추정치예요.",
                    data_boundary=DataBoundary.ENGINE,
                    evidence_ids=[evidence_id],
                    items=[
                        VisualizationDatum(
                            label=_STRESS_SCENARIO_LABELS.get(
                                stress.scenario_code,
                                "기타 시장 충격",
                            ),
                            value=_one_decimal(stress.estimated_loss_percent),
                            unit="%",
                            role=VisualizationDatumRole.VALUE,
                        )
                        for stress in stress_items
                    ],
                )
            )

    if response.intent == ChatIntent.PROVIDER_DISCLOSURE:
        disclosure_items = [
            VisualizationDatum(
                label=item.label,
                value=item.value,
                unit=item.unit,
                role=VisualizationDatumRole.VALUE,
            )
            for item in response.numeric_evidence
        ]
        if disclosure_items:
            visualizations.append(
                ChatVisualization(
                    kind=VisualizationKind.DISCLOSURE_COMPARISON,
                    title="사업자 공시 비교",
                    description="회사별 과거 수익률과 공시된 수수료율을 비교해요.",
                    data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
                    evidence_ids=list(
                        dict.fromkeys(
                            item.evidence_id
                            for item in response.numeric_evidence
                        )
                    ),
                    items=disclosure_items,
                )
            )

    return response.model_copy(update={"visualizations": visualizations})


def with_context(
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
            response_context.scenario_code
            if response_context is not None
            else None
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
    etf_theme_context = (
        response_context.etf_theme
        if response_context is not None and response_context.etf_theme is not None
        else previous.etf_theme
        if previous is not None
        else None
    )
    referents = _response_referents(response, plan)
    if response.intent == ChatIntent.ETF_THEME:
        account_type = None
        survey_profile = None
        selected_risk_profile = None
    return response.model_copy(
        update={
            "conversation_context": ConversationContext(
                account_type=account_type,
                scenario_code=scenario_code,
                last_intent=response.intent,
                survey_profile=survey_profile,
                selected_risk_profile=selected_risk_profile,
                news=news_context,
                etf_theme=etf_theme_context,
                referents=referents,
            )
        }
    )


def _response_referents(
    response: ChatResponse, plan: QueryPlan
) -> ReferentList | None:
    if response.intent != ChatIntent.ACCOUNT_RULE:
        return None
    account_types = plan.account_types
    if plan.account_rule_topic is not None and (
        plan.account_rule_topic.value == "pension_account_overview"
    ):
        account_types = tuple(_ACCOUNT_TYPE_LABELS)
    if len(account_types) < 2:
        return None
    return ReferentList(
        intent=ChatIntent.ACCOUNT_RULE,
        topic=(
            plan.account_rule_topic.value
            if plan.account_rule_topic is not None
            else None
        ),
        items=[
            ReferentItem(
                label=_ACCOUNT_TYPE_LABELS[account_type],
                ref=account_type.value,
            )
            for account_type in account_types
        ],
    )


def finalize_response(
    response: ChatResponse,
    request: ChatRequest,
    plan: QueryPlan,
) -> ChatResponse:
    response = with_context(attach_visualizations(response), request, plan)
    return response.model_copy(
        update={
            "suggested_follow_ups": (
                response.suggested_follow_ups
                or build_suggested_follow_ups(response)
            )
        }
    )
