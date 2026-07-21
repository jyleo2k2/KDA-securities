"""Portfolio, ETF-theme, and macro-evidence intent handlers."""

import logging
import re
from decimal import Decimal

from ...engine import (
    EducationalPortfolioEvaluation,
    EducationalPortfolioInput,
    EducationalRiskProfile,
    build_educational_portfolio,
    evaluate_risk_cap,
    select_theme_etf_candidates,
)
from ...etf_theme_repository import EtfThemeRepository
from ...etf_theme_verification_repository import (
    EtfThemeVerificationReader,
    etf_theme_content_sha256,
)
from ...macro_evidence import (
    MacroEvidenceRepository,
    MacroEvidenceSnapshot,
    MacroEvidenceUnavailable,
    MacroMetric,
    attach_etf_outcomes,
)
from ..models import (
    AnswerBlock,
    AnswerBlockKind,
    AnswerSection,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    DataBoundary,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from ..query_planner import QueryPlan, ThemeContentTopic
from ._shared import (
    _ACCOUNT_TYPE_LABELS,
    _MACRO_ANALOG_OUTCOME_TERMS,
    _RISK_PROFILE_LABELS,
    _RISK_PROFILE_RANKS,
    _SLEEVE_LABELS,
    PortfolioUniverseLoader,
    _decimal_text,
    _krw_text,
    _one_decimal,
    _rebalancing_summary,
    _selected_risk_profile,
    _source_ids,
    _strategy_summary,
    _target_portfolio_summary,
)

logger = logging.getLogger(__name__)


def etf_theme_response(
    request: ChatRequest,
    plan: QueryPlan,
    *,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
    theme_repository: EtfThemeRepository | None,
    theme_verification: EtfThemeVerificationReader | None,
) -> ChatResponse:
    if theme_repository is None or plan.theme_id is None:
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer="ETF 테마 카탈로그를 불러오지 못했습니다.",
            data_mode="unavailable",
            limitations=["테마 카탈로그 연결 상태를 확인해야 합니다."],
        )
    theme = theme_repository.get(plan.theme_id)
    if theme is None:
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer="요청한 ETF 테마를 현재 카탈로그에서 찾지 못했습니다.",
            data_mode="unavailable",
        )

    catalog_source_id = "policy:etf_theme_catalog"
    sources = [
        SourceEvidence(
            evidence_id=catalog_source_id,
            label="ETF 테마 서비스 카탈로그",
            locator=theme_repository.catalog_path.as_posix(),
            publisher="연금 코파일럿",
            as_of=theme_repository.catalog.as_of_date,
            data_boundary=DataBoundary.ENGINE,
        )
    ]
    topic = plan.theme_content_topic or ThemeContentTopic.OVERVIEW
    verified_source_ids: list[str] = []
    if theme_verification is not None:
        try:
            verified_evidence = theme_verification.verified_evidence(
                catalog_version=theme_repository.catalog.catalog_version,
                theme_id=theme.theme_id,
                topic=topic.value,
                content_sha256=etf_theme_content_sha256(theme, topic.value),
            )
        except Exception:  # noqa: BLE001 — 검증 DB 장애는 초안 표기로 축소
            logger.warning(
                "etf_theme_verification_unavailable theme=%s topic=%s",
                theme.theme_id,
                topic.value,
            )
            verified_evidence = ()
        for evidence in verified_evidence:
            verified_source_ids.append(evidence.evidence_id)
            sources.append(
                SourceEvidence(
                    evidence_id=evidence.evidence_id,
                    label=evidence.label,
                    locator=evidence.locator,
                    publisher=evidence.publisher,
                    as_of=evidence.as_of,
                    data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                )
            )
    company_source_ids: list[str] = []
    if topic == ThemeContentTopic.REPRESENTATIVE_COMPANIES:
        for index, company in enumerate(theme.representative_companies, start=1):
            source_id = f"company:{theme.theme_id}:{index}"
            company_source_ids.append(source_id)
            sources.append(
                SourceEvidence(
                    evidence_id=source_id,
                    label=f"{company.name} 공식 홈페이지",
                    locator=company.source_url,
                    publisher=company.name,
                    as_of=company.as_of_date,
                    data_boundary=DataBoundary.ENGINE,
                )
            )

    if topic == ThemeContentTopic.REPRESENTATIVE_COMPANIES:
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마 대표기업 3곳",
                content="테마의 서로 다른 역할을 이해하기 위한 대표 사례입니다.",
                evidence_ids=verified_source_ids or company_source_ids,
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.CALLOUT,
                        title=company.name,
                        text=(
                            f"테마에서의 역할: {company.theme_role} "
                            f"{company.representative_reason}\n\n"
                            f"쉽게 말하면: {company.plain_description}"
                        ),
                    )
                    for company in theme.representative_companies
                ],
            )
        ]
        answer = f"{theme.name} 테마를 이해하기 위한 대표기업 3곳입니다."
        data_mode = "theme_representative_companies"
    elif topic == ThemeContentTopic.INVESTMENT_CONSIDERATIONS:
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마 ETF 장단점",
                content=(
                    f"{theme.name} 테마 ETF를 볼 때 기대할 수 있는 이점과 "
                    "손실 가능성을 키울 수 있는 위험을 쉬운 말로 "
                    "같이 확인해 보세요."
                ),
                evidence_ids=verified_source_ids or [catalog_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="투자할 때의 이점 3가지",
                        items=list(theme.benefits),
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="주의할 위험 3가지",
                        items=list(theme.risks),
                    ),
                ],
            )
        ]
        answer = (
            f"{theme.name} 테마 ETF에 투자할 때의 이점 3개와 "
            "위험 3개를 쉽게 정리했습니다."
        )
        data_mode = "theme_investment_considerations"
    elif topic == ThemeContentTopic.PERFORMANCE_DRIVERS:
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마 성과의 관찰 요인",
                content=(
                    "각 요인이 해당 산업의 주문·매출·비용·가동률에 어떻게 "
                    "연결되는지 함께 설명합니다. 미래 수익률 예측이 아니라 "
                    "현재 사업 환경을 점검하는 기준입니다."
                ),
                evidence_ids=verified_source_ids or [catalog_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="성과를 평가할 관찰 요인 3가지",
                        items=list(theme.performance_drivers),
                    )
                ],
            )
        ]
        answer = (
            f"{theme.name} 테마에서 확인할 성과 관찰 요인 3개와 "
            "각각이 중요한 이유를 정리했습니다."
        )
        data_mode = "theme_performance_drivers"
    elif topic == ThemeContentTopic.RISKS:
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마의 주요 위험",
                content=(
                    "테마 편입 전에 변동성과 손실 가능성을 키울 수 있는 "
                    "고유 위험을 먼저 확인하세요."
                ),
                evidence_ids=verified_source_ids or [catalog_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="주의할 위험 3가지",
                        items=list(theme.risks),
                    )
                ],
            )
        ]
        answer = f"{theme.name} 테마의 주요 위험 3개를 정리했습니다."
        data_mode = "theme_risks"
    else:
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마란?",
                content=theme.plain_summary,
                evidence_ids=verified_source_ids or [catalog_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.CALLOUT,
                        title="분류상 정의",
                        text=theme.definition,
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="어떤 기업·분야를 담나",
                        items=list(theme.exposure_segments),
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.CALLOUT,
                        title="한 줄 비유",
                        text=theme.one_line_analogy,
                    ),
                ],
            )
        ]
        answer = f"{theme.name} 테마를 초보자도 이해하기 쉽게 설명했습니다."
        data_mode = "theme_overview"
    limitations = []
    if not verified_source_ids:
        limitations.append(
            "테마 설명은 사용자가 제공한 조사 내용을 서비스 분류체계로 "
            "정리한 것으로 공식 문서 검증 전 초안입니다."
        )
    limitations.append(
        "테마 편입은 상품의 미래 성과를 뜻하지 않으며 "
        "수익률을 예측하지 않습니다."
    )
    if topic == ThemeContentTopic.REPRESENTATIVE_COMPANIES:
        limitations.append(
            "대표기업은 테마 이해를 위한 사례이며 특정 ETF의 실제 편입종목이나 "
            "매수 추천을 뜻하지 않습니다."
        )
    if not plan.requests_theme_candidates:
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=answer,
            data_mode=data_mode,
            sections=sections,
            sources=sources,
            limitations=limitations,
        )

    survey = request.survey_profile or (
        request.conversation_context.survey_profile
        if request.conversation_context is not None
        else None
    )
    if survey is None:
        limitations.append(
            "투자성향과 보유 계좌가 확인되기 전에는 ETF 후보를 제시하지 않습니다."
        )
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=(
                f"{theme.name} 테마 설명은 제공할 수 있지만 ETF 후보 비교에는 "
                "완료된 투자성향 설문과 계좌 유형이 필요합니다."
            ),
            data_mode="survey_required",
            sections=sections,
            sources=sources,
            limitations=limitations,
        )

    previous_selection = (
        request.conversation_context.selected_risk_profile
        if request.conversation_context is not None
        else None
    )
    selected_profile = (
        _selected_risk_profile(request.message)
        or previous_selection
        or survey.risk_profile
    )
    if (
        _RISK_PROFILE_RANKS[selected_profile]
        > _RISK_PROFILE_RANKS[survey.risk_profile]
    ):
        limitations.append(
            "완료된 설문 결과보다 위험한 투자성향의 테마 ETF 후보는 "
            "제시하지 않습니다."
        )
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=f"{theme.name} 테마 설명만 제공했습니다.",
            data_mode="profile_guardrail",
            sections=sections,
            sources=sources,
            limitations=limitations,
        )

    allowed_accounts = survey.portfolio_account_types()
    requested_accounts = plan.account_types or allowed_accounts
    account_types = tuple(
        account for account in requested_accounts if account in allowed_accounts
    )
    if not account_types:
        limitations.append(
            "질문에 지정한 계좌가 완료된 설문 프로필의 보유 계좌에 없습니다."
        )
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=f"{theme.name} 테마 설명만 제공했습니다.",
            data_mode="account_profile_mismatch",
            sections=sections,
            sources=sources,
            limitations=limitations,
        )
    if portfolio_universe_loader is None:
        limitations.append("계좌별 ETF 적격 유니버스를 불러올 수 없습니다.")
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=f"{theme.name} 테마 설명만 제공했습니다.",
            data_mode="unavailable",
            sections=sections,
            sources=sources,
            limitations=limitations,
        )

    numeric: list[NumericEvidence] = []
    candidate_rows: list[list[str]] = []
    candidate_blocks: list[AnswerBlock] = []
    holding_sections: list[AnswerSection] = []
    holding_source_ids: set[str] = set()
    successful_accounts = 0
    for account_type in account_types:
        try:
            universe = portfolio_universe_loader(account_type)
        except (FileNotFoundError, ValueError):
            limitations.append(
                f"{_ACCOUNT_TYPE_LABELS[account_type]} ETF 적격 유니버스를 "
                "불러오지 못했습니다."
            )
            continue
        evaluation = select_theme_etf_candidates(
            catalog=theme_repository.catalog,
            theme=theme,
            products=universe.products,
            kis_products_by_code=(
                theme_repository.kis_products_by_code
            ),
            component_snapshot_date=(
                theme_repository.component_snapshot_date
            ),
            request=EducationalPortfolioInput(
                account_type=account_type,
                age=survey.current_age,
                retirement_start_age=survey.retirement_start_age,
                risk_profile=selected_profile,
                loss_tolerance_percent=survey.loss_tolerance_percent,
            ),
            limit=plan.max_results,
        )
        if evaluation.status != "ok":
            limitations.extend(evaluation.limitations)
            continue
        successful_accounts += 1
        master_source_id = f"engine:theme_candidates:{account_type.value}"
        sources.append(
            SourceEvidence(
                evidence_id=master_source_id,
                label=(
                    f"{_ACCOUNT_TYPE_LABELS[account_type]} "
                    "계좌별 ETF 적격 유니버스"
                ),
                locator=str(getattr(universe, "source_path", "local-cache")),
                publisher="연금 코파일럿 규칙 엔진",
                as_of=universe.as_of,
                data_boundary=DataBoundary.ENGINE,
            )
        )
        for rank, candidate in enumerate(evaluation.candidates, start=1):
            fee_text = "확인 필요"
            if candidate.fee_percent is not None:
                fee_text = f"{_decimal_text(candidate.fee_percent)}%"
                numeric.append(
                    NumericEvidence(
                        label=f"{candidate.isu_name} 총보수",
                        value=candidate.fee_percent,
                        unit="%",
                        evidence_id=master_source_id,
                        basis="계좌별 ETF 실데이터 마스터",
                    )
                )
            trading_value_text = "확인 필요"
            if candidate.median_daily_trading_value_krw is not None:
                trading_value_text = _krw_text(
                    candidate.median_daily_trading_value_krw
                )
                numeric.append(
                    NumericEvidence(
                        label=f"{candidate.isu_name} 일별 거래대금 중앙값",
                        value=candidate.median_daily_trading_value_krw,
                        unit="KRW",
                        evidence_id=master_source_id,
                        basis="계좌별 ETF 실데이터 마스터의 관측기간 중앙값",
                    )
                )
            candidate_rows.append(
                [
                    _ACCOUNT_TYPE_LABELS[account_type],
                    candidate.isu_name,
                    candidate.isu_code,
                    trading_value_text,
                    fee_text,
                ]
            )
            candidate_blocks.append(
                AnswerBlock(
                    kind=AnswerBlockKind.CALLOUT,
                    title=(
                        f"{_ACCOUNT_TYPE_LABELS[account_type]} {rank}. "
                        f"{candidate.isu_name}"
                    ),
                    text=(
                        f"이 계좌에서 편입 가능한 {theme.name} 테마 비교 "
                        f"후보예요. 일별 거래대금 중앙값은 "
                        f"{trading_value_text}, 총보수는 {fee_text}예요. "
                        "거래대금은 거래 편의를, 총보수는 보유 비용을 "
                        "비교하는 지표이며 미래 수익률을 뜻하지 않아요."
                    ),
                )
            )
            if not plan.requests_theme_holdings or not candidate.top_holdings:
                continue
            kis_source_id = f"kis:components:{candidate.isu_code}"
            if kis_source_id in holding_source_ids:
                continue
            holding_source_ids.add(kis_source_id)
            sources.append(
                SourceEvidence(
                    evidence_id=kis_source_id,
                    label=f"{candidate.isu_name} 구성종목",
                    locator=(
                        "https://openapi.koreainvestment.com:9443/uapi/etfetn/"
                        "v1/quotations/inquire-component-stock-price"
                    ),
                    publisher="한국투자증권 Open Trading API",
                    as_of=candidate.component_snapshot_date,
                    data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
                )
            )
            holding_rows: list[list[str]] = []
            for holding in candidate.top_holdings[:5]:
                holding_rows.append(
                    [
                        holding.component_name,
                        holding.component_code or "-",
                        f"{_decimal_text(holding.weight_percent)}%",
                    ]
                )
                numeric.append(
                    NumericEvidence(
                        label=(
                            f"{candidate.isu_name} "
                            f"{holding.component_name} 구성 비중"
                        ),
                        value=holding.weight_percent,
                        unit="%",
                        evidence_id=kis_source_id,
                        basis="KIS etf_cnfg_issu_rlim 원문 필드",
                    )
                )
            holding_sections.append(
                AnswerSection(
                    kind=SectionKind.FACT,
                    title=f"{candidate.isu_name} 주요 구성종목",
                    content="한국투자증권이 제공한 기준일 스냅샷입니다.",
                    evidence_ids=[kis_source_id],
                    blocks=[
                        AnswerBlock(
                            kind=AnswerBlockKind.TABLE,
                            headers=["구성종목", "종목코드", "비중"],
                            rows=holding_rows,
                        )
                    ],
                )
            )

    if candidate_rows:
        master_ids = [
            source.evidence_id
            for source in sources
            if source.evidence_id.startswith("engine:theme_candidates:")
        ]
        sections.append(
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마 ETF상품",
                content=(
                    "계좌 적격성과 투자성향 범위를 먼저 적용한 뒤, "
                    "일별 거래대금 중앙값이 높은 순서로 정렬했어요. "
                    "거래대금이 같으면 총보수가 낮은 상품이 앞서요."
                ),
                evidence_ids=master_ids,
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.TABLE,
                        headers=[
                            "계좌",
                            "ETF",
                            "종목코드",
                            "일별 거래대금 중앙값",
                            "총보수",
                        ],
                        rows=candidate_rows,
                    ),
                    *candidate_blocks,
                ],
            )
        )
        sections.extend(holding_sections)
    else:
        limitations.append(
            "현재 성향·계좌 범위와 적재 데이터에서 제시 가능한 "
            "테마 ETF 후보가 없습니다."
        )
    if plan.requests_theme_holdings and not holding_sections:
        limitations.append(
            "최신 한국투자증권 구성종목 스냅샷이 없어 요청한 비중을 "
            "표시하지 않았습니다."
        )

    return ChatResponse(
        intent=ChatIntent.ETF_THEME,
        answer=(
            f"{theme.name} 테마를 설명하고 성향·계좌 기준을 통과한 "
            "교육용 ETF 비교 결과를 정리했습니다."
            if candidate_rows
            else f"{theme.name} 테마 설명만 제공했습니다."
        ),
        data_mode=(
            "theme_candidates" if successful_accounts else "theme_overview_only"
        ),
        sections=sections,
        sources=sources,
        numeric_evidence=numeric,
        limitations=list(dict.fromkeys(limitations)),
        conversation_context=ConversationContext(
            account_type=survey.account_type,
            last_intent=ChatIntent.ETF_THEME,
            survey_profile=survey,
            selected_risk_profile=selected_profile,
        ),
    )


def custom_portfolio(request: ChatRequest) -> ChatResponse:
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
            f"연금저축 예시 포트폴리오의 위험자산 비중은 {ratio}%예요. "
            "DC형·IRP의 비율 한도는 적용하지 않아요. 상품별로 담을 수 "
            "있는지는 따로 확인해야 해요."
        )
    else:
        limit = _decimal_text(evaluation.limit_percent)
        limit_status = (
            f"한도({limit}%) 안이에요"
            if evaluation.within_limit
            else f"한도({limit}%)를 넘었어요"
        )
        answer = (
            f"{evaluation.evaluated_input.account_type.value.upper()} 예시 "
            f"포트폴리오는 위험자산이 {ratio}%로 {limit_status}. "
            "위험자산은 주식처럼 가격이 오르내릴 수 있는 자산이에요. "
            "상품별 편입 가능 여부도 확인해야 해요."
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


def completed_survey_required() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            "완료된 투자성향 설문 결과가 없어요. 프로필에서 설문을 마친 뒤 "
            "투자전략을 다시 요청해 주세요."
        ),
        data_mode="survey_required",
        limitations=[
            "챗봇 대화에서는 나이와 수령 나이를 다시 수집하지 않습니다.",
            "설문 결과가 연결되기 전에는 규칙 엔진을 호출하지 않습니다.",
        ],
    )


def risk_profile_selection_guide() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            "투자성향은 안정형, 안정추구형, 위험중립형, 적극투자형, "
            "공격투자형의 다섯 유형으로 나눠요. 원하는 유형을 하나 "
            "선택해 말해 주세요."
        ),
        data_mode="risk_profile_selection",
        sections=[
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="투자성향 선택",
                content=(
                    "안정형: 원금 보전과 낮은 가격 변동을 우선해요.\n"
                    "안정추구형: 채권 중심으로 운용하되 제한적으로 "
                    "위험자산을 활용해요.\n"
                    "위험중립형: 성장성과 안정성의 균형을 추구해요.\n"
                    "적극투자형: 주식 비중을 높여 장기 성장을 추구해요.\n"
                    "공격투자형: 높은 변동성을 감수하고 성장·전술자산을 "
                    "적극적으로 활용해요.\n\n"
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


def risk_profile_portfolio_guide() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            "다섯 투자성향은 같은 ETF를 단순히 비중만 바꾸는 방식이 아니라, "
            "성장자산의 역할과 방어자산의 수준, 전술자산의 허용 범위를 "
            "다르게 설계해요. 실제 비중과 후보 ETF는 완료된 설문과 계좌 "
            "규칙을 반영해 기존 규칙 엔진이 계산해요."
        ),
        data_mode="risk_profile_portfolio_guide",
        sections=[
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="안정형 연금운용 전략",
                content=(
                    "전략: 자본보전 중심 전략으로 큰 손실을 피하고 유동성을 "
                    "확보하는 데 우선순위를 둬요.\n"
                    "설계: 채권과 현금을 핵심으로 두고, 분산 주식·실물자산은 "
                    "설문에서 확인된 손실 감내 범위 안에서 보조로만 활용해요. "
                    "전술자산은 편입하지 않는 것을 기본으로 해요.\n"
                    "운용: 정기 납입은 방어자산을 중심으로 이어가고, 단기 "
                    "수익을 좇아 자산 구성을 자주 바꾸지 않아요."
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="안정추구형 연금운용 전략",
                content=(
                    "전략: 방어적 분산 전략으로 안정성을 중심에 두면서 제한된 "
                    "성장 기회를 함께 활용해요.\n"
                    "설계: 채권을 핵심으로 두고 넓게 분산한 주식과 실물자산을 "
                    "보조로 더하며, 현금은 리밸런싱 여유자금으로 유지해요.\n"
                    "운용: 위험자산이 목표보다 커지면 추가 매수를 멈추고, 새 "
                    "납입금을 채권·현금 등 부족한 방어자산에 먼저 배분해요."
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="위험중립형 연금운용 전략",
                content=(
                    "전략: 코어·위성 전략으로 장기 성장과 하락 방어의 균형을 "
                    "추구해요.\n"
                    "설계: 넓게 분산한 주식과 채권을 두 핵심축으로 두고, "
                    "실물자산은 물가 대응과 분산을 위한 위성자산으로 활용해요.\n"
                    "운용: 시장 전망에 따라 한쪽으로 몰기보다 정기 납입과 "
                    "리밸런싱으로 목표 구성을 꾸준히 유지해요."
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="적극투자형 연금운용 전략",
                content=(
                    "전략: 성장 코어·위성 전략으로 장기 성장자산을 중심에 "
                    "두되 하락 충격을 흡수할 장치를 남겨요.\n"
                    "설계: 넓게 분산한 주식 ETF를 핵심으로 두고 채권을 완충재로, "
                    "실물자산과 전술자산은 상한이 있는 보조자산으로 활용해요.\n"
                    "운용: 하락기에도 정기 납입 원칙을 유지하되, 전술자산을 "
                    "추격 매수하지 않고 부족한 핵심자산부터 채워요."
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="공격투자형 연금운용 전략",
                content=(
                    "전략: 바벨형 성장·전술 전략으로 분산 성장자산과 최소 "
                    "방어자산을 양쪽 축에 두고 높은 변동성을 감수해요.\n"
                    "설계: 주식 성장 코어를 가장 중요하게 두되 채권·현금 "
                    "완충재를 없애지 않으며, 전술자산은 별도 상한을 둬 집중을 "
                    "막아요.\n"
                    "운용: 테마를 수익률 순으로 쫓지 않고 분산 성장 코어를 먼저 "
                    "채운 뒤, 허용 범위 안에서만 전술자산을 운용해요."
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="공통 실행 원칙",
                content=(
                    "ETF 후보는 과거 수익률 순위가 아니라 비용, 거래대금, "
                    "순자산, 괴리율, 추적오차, 관측기간으로 비교해요. 분기마다 "
                    "목표비중 이탈을 점검하고 새 납입금은 부족한 자산군에 먼저 "
                    "배분해요. 매년 나이, 설문 투자성향, 손실 감내 수준, 연금 "
                    "수령 시점을 다시 확인해 목표 구성을 갱신해요."
                ),
            ),
        ],
        limitations=[
            "DC·IRP는 일반 위험자산 70% 한도를 계좌별로 적용합니다.",
            "개인 비중과 ETF 후보는 완료된 설문보다 위험하지 않은 범위에서 "
            "규칙 엔진이 계산합니다.",
            "미래 수익률을 예측하거나 보장하지 않으며 상품 주문과 자동 "
            "리밸런싱은 수행하지 않습니다.",
        ],
    )


def retirement_age_selection_guide() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            "연금 수령 개시 시점은 만 55세부터 60세 사이에서 선택해 주세요. "
            "선택한 나이까지의 운용기간으로 포트폴리오와 장기 계획수익률을 "
            "다시 계산해요."
        ),
        data_mode="retirement_age_selection",
        limitations=[
            "계획수익률은 미래 수익 예측이나 보장값이 아닙니다.",
            "실제 연금 수령 가능 여부와 세금은 계좌 조건을 별도로 확인합니다.",
        ],
    )


def age_style_portfolio_guide() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            "연령대의 운용 초점과 투자성향별 설계를 함께 적용해요. "
            "나이는 운용기간과 방어 필요성을, 투자성향은 위험자산 활용 "
            "정도를 정하는 기준이에요."
        ),
        data_mode="age_style_portfolio_guide",
        sections=[
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="연령대별 운용 초점",
                content=(
                    "20대: 긴 운용기간을 활용해 정기 납입과 넓은 분산을 "
                    "우선해요.\n"
                    "30대: 성장자산을 유지하면서 납입 여력과 생활목표를 "
                    "함께 점검해요.\n"
                    "40대: 계좌 간 중복과 집중위험을 줄이고 방어자산을 "
                    "점진적으로 보강해요.\n"
                    "50대: 연금 수령 시점에 맞춰 하락위험·유동성·인출 "
                    "준비를 우선해요.\n\n"
                    "연금 수령 개시는 만 55~60세에서 직접 선택하며, 선택한 "
                    "시점까지의 운용기간으로 설계를 다시 계산해요."
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="투자스타일별 포트폴리오 설계",
                content=(
                    "안정형: 원리금보장·단기채·현금성 자산을 중심으로 "
                    "변동성을 낮춰요.\n"
                    "안정추구형: 채권을 중심에 두고 분산 주식·실물자산을 "
                    "제한적으로 더해요.\n"
                    "위험중립형: 주식과 채권을 균형 있게 두고 실물자산을 "
                    "보조로 활용해요.\n"
                    "적극투자형: 분산 주식 ETF를 성장 핵심으로 두고 채권을 "
                    "하락 완충재로 유지해요.\n"
                    "공격투자형: 성장자산 비중을 높이되 전술자산은 상한을 "
                    "두고 최소 방어자산을 유지해요.\n\n"
                    "운용 후에는 분기마다 목표비중 이탈을 점검하고, 매년 "
                    "나이·투자성향·수령 시점과 계획가정을 다시 확인해요. "
                    "새 납입금은 부족한 자산군에 먼저 배분해요."
                ),
            ),
        ],
        limitations=[
            "DC·IRP는 일반 위험자산 70% 한도를 계좌별로 적용합니다.",
            "개인 포트폴리오 비중과 ETF 후보는 완료된 설문 결과를 넘지 "
            "않는 범위에서 규칙 엔진이 계산합니다.",
            "상품 주문이나 자동 리밸런싱은 수행하지 않습니다.",
        ],
    )


def risk_profile_guardrail(
    assessed_profile: EducationalRiskProfile,
    requested_profile: EducationalRiskProfile,
) -> ChatResponse:
    assessed_label = _RISK_PROFILE_LABELS[assessed_profile.value]
    requested_label = _RISK_PROFILE_LABELS[requested_profile.value]
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            f"설문 결과는 {assessed_label}이에요. {requested_label} ETF "
            "포트폴리오는 설문 성향보다 위험해서 제안하지 않아요. "
            f"{assessed_label} 또는 더 보수적인 투자성향을 선택해 주세요."
        ),
        data_mode="profile_guardrail",
        limitations=[
            "설문에서 확인된 투자성향보다 위험한 상품 구성은 제안하지 않습니다."
        ],
    )


def educational_portfolio(
    request: EducationalPortfolioInput,
    *,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
    macro_evidence: MacroEvidenceRepository | None,
) -> ChatResponse:
    account_label = _ACCOUNT_TYPE_LABELS[request.account_type]
    if portfolio_universe_loader is None:
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                f"{account_label} 계좌용 교육 포트폴리오 데이터 저장소가 "
                "연결되지 않았어요."
            ),
            data_mode="unavailable",
            limitations=[
                f"{account_label} 계좌 결과를 임의 수치로 대신 계산하지 않았습니다."
            ],
        )
    try:
        repository = portfolio_universe_loader(request.account_type)
        evaluation = build_educational_portfolio(
            request,
            products=repository.products,
            histories=repository.histories,
            history_sources=repository.history_sources,
            source_as_of=repository.as_of,
            history_as_of=getattr(
                repository, "latest_history_as_of", repository.as_of
            ),
            score_cache=getattr(repository, "score_cache", None),
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        logger.warning(
            "Educational portfolio data unavailable for account=%s: %s",
            request.account_type.value,
            exc,
        )
        missing_master = (
            isinstance(exc, FileNotFoundError)
            and "no cost-return master" in str(exc)
        )
        unavailable_reason = (
            "ETF 비용·수익률 기준 데이터가 서버에 준비되지 않았어요."
            if missing_master
            else "ETF 입력 데이터 검증에 실패했어요."
        )
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                f"{account_label} 계좌용 {unavailable_reason} "
                "포트폴리오 결과를 만들지 않았어요."
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
        locator=(
            f"engine://{evaluation.engine_name}/{evaluation.engine_version}"
        ),
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
        )
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
    numeric.extend(
        NumericEvidence(
            label=f"{stress.scenario_code} 스트레스 손실 추정치",
            value=_one_decimal(stress.estimated_loss_percent),
            unit="%",
            evidence_id=engine_source.evidence_id,
            basis="규칙 엔진의 포트폴리오 스트레스 시나리오",
        )
        for stress in evaluation.portfolio_risk.stress_scenarios
    )
    planning = evaluation.planning_return
    planning_text = "검증된 계획수익률 범위를 계산하지 못했어요."
    if (
        planning.conservative_planning_return_percent is not None
        and planning.base_planning_return_percent is not None
    ):
        conservative = _one_decimal(
            planning.conservative_planning_return_percent
        )
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
            f"{_decimal_text(base)}%예요. 미래 예측값이 아니라 매년 다시 "
            "살펴보는 장기 자산배분 가정이에요."
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
    macro_outcomes = None
    macro_outcome_limitations: list[str] = []
    if request.current_holdings and macro_evidence is not None:
        try:
            macro_snapshot = macro_evidence.analog_regimes()
            enriched_snapshot = attach_etf_outcomes(
                macro_snapshot,
                repository=repository,
                isu_codes=[
                    holding.isu_code for holding in request.current_holdings
                ],
            )
            macro_outcomes = enriched_snapshot.etf_outcomes
        except (MacroEvidenceUnavailable, FileNotFoundError, ValueError) as exc:
            logger.warning("Historical ETF outcome evidence unavailable: %s", exc)
            macro_outcome_limitations.append(
                "과거 유사국면 이후 ETF 총수익률 근거를 불러오지 못했습니다."
            )
    numeric_priority = {
        "일반 위험자산 목표비중": 0,
        "보수 계획수익률": 1,
        "기준 계획수익률": 2,
        "수령 개시까지 운용기간": 3,
        "리밸런싱 이탈 기준": 5,
    }
    numeric.sort(
        key=lambda item: numeric_priority.get(
            item.label,
            4
            if item.label.endswith(" 목표비중")
            else 6
            if item.label.endswith(" 스트레스 손실 추정치")
            else 7,
        )
    )
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            "설문 결과에 맞는 투자전략과 장기 계획수익률을 정리했어요. "
            "계좌별 목표비중과 운용 원칙은 아래에서 볼 수 있어요."
        ),
        data_mode="engine_educational_planning",
        sources=sources,
        numeric_evidence=numeric,
        sections=sections,
        educational_portfolio_evaluation=evaluation,
        educational_portfolio_evaluations=[evaluation],
        macro_regime_etf_outcomes=macro_outcomes,
        limitations=[
            "설명은 규칙 엔진 결과 코드와 수치만 정해진 문장으로 변환합니다.",
            "CMA는 10~15년 전략배분 기준이며 매년 재검토합니다.",
            "상품 선택·주문·자동 리밸런싱은 수행하지 않습니다.",
            *macro_outcome_limitations,
        ],
    )


def educational_portfolios(
    requests: list[EducationalPortfolioInput],
    *,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
    macro_evidence: MacroEvidenceRepository | None,
) -> ChatResponse:
    responses = [educational_portfolio(
            request,
            portfolio_universe_loader=portfolio_universe_loader,
            macro_evidence=macro_evidence,
        ) for request in requests]
    if len(responses) == 1:
        return responses[0]
    if any(
        response.educational_portfolio_evaluation is None
        for response in responses
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
        limitations.append(
            "계좌별 규칙을 섞거나 누락값을 추정하지 않았습니다."
        )
        return ChatResponse(
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            answer=(
                "여러 계좌의 포트폴리오를 만들지 못했어요.\n"
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
    sources: dict[str, SourceEvidence] = {
        survey_source.evidence_id: survey_source
    }
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
                f"적용했어요. 보유 계좌는 {account_names}이며 계좌별 규칙을 "
                "각각 계산해요."
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
            f"{account_names}의 계좌 규칙을 각각 적용했어요. 계좌별 ETF "
            "포트폴리오와 장기 계획수익률은 아래에서 볼 수 있어요."
        ),
        data_mode="engine_multi_account_planning",
        sources=list(sources.values()),
        numeric_evidence=numeric,
        sections=sections,
        educational_portfolio_evaluation=evaluations[0],
        educational_portfolio_evaluations=evaluations,
        limitations=list(dict.fromkeys(limitations)),
    )


def macro_evidence_response(
    request: ChatRequest,
    *,
    macro_evidence: MacroEvidenceRepository | None,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
) -> ChatResponse:
    if macro_evidence is None:
        return macro_evidence_unavailable()
    if _MACRO_ANALOG_OUTCOME_TERMS.search(request.message):
        portfolio_request = request.educational_portfolio
        if portfolio_request is None or not portfolio_request.current_holdings:
            return ChatResponse(
                intent=ChatIntent.MACRO_EVIDENCE,
                answer=(
                    "현재 보유 ETF를 먼저 입력하면 각 과거 유사국면 이후의 "
                    "실제 총수익률과 최대낙폭을 보여드릴게요."
                ),
                data_mode="etf_selection_required",
                limitations=[
                    "ETF 코드 없이 임의 상품을 선택하거나 성과 수치를 "
                    "만들지 않습니다."
                ],
            )
        if portfolio_universe_loader is None:
            return macro_evidence_unavailable()
        try:
            repository = portfolio_universe_loader(
                portfolio_request.account_type
            )
            snapshot = attach_etf_outcomes(
                macro_evidence.analog_regimes(),
                repository=repository,
                isu_codes=[
                    holding.isu_code
                    for holding in portfolio_request.current_holdings
                ],
            )
        except (MacroEvidenceUnavailable, FileNotFoundError, ValueError):
            return macro_evidence_unavailable()
        return ChatResponse(
            intent=ChatIntent.MACRO_EVIDENCE,
            answer=(
                "입력한 ETF의 과거 유사국면 이후 실제 성과를 정리했어요. "
                "미래 예측이나 리밸런싱 신호로 사용하지 않아요."
            ),
            data_mode="historical_macro_regime_etf_outcomes",
            macro_regime_etf_outcomes=snapshot.etf_outcomes,
            limitations=[
                "총수익지수의 과거 관측값만 사용하며 미래 성과를 "
                "의미하지 않습니다.",
                "ETF 상장 전이거나 구간 경계 관측이 부족하면 해당 "
                "기간을 비워 둡니다.",
            ],
        )
    try:
        snapshot = macro_evidence.latest()
    except MacroEvidenceUnavailable:
        return macro_evidence_unavailable()

    metrics = select_macro_metrics(request.message, snapshot)
    if not metrics:
        return macro_evidence_unavailable()
    sources = [
        SourceEvidence(
            evidence_id=f"macro:{metric.metric_id}",
            label=metric.source_label,
            locator=metric.source_url,
            data_boundary=DataBoundary.OFFICIAL_STATISTICS,
            publisher=metric.publisher,
            as_of=metric.observed_at,
        )
        for metric in metrics
    ]
    numeric_evidence = [
        NumericEvidence(
            label=metric.label,
            value=metric.value,
            unit=metric.unit,
            evidence_id=f"macro:{metric.metric_id}",
            basis=metric.basis,
        )
        for metric in metrics
    ]
    lines = [
        (
            f"{metric.label}은(는) {_decimal_text(metric.value)}"
            f"{metric.unit}예요 (관측일 {metric.observed_at.isoformat()})."
        )
        for metric in metrics
    ]
    answer = "\n".join(lines)
    limitation = (
        "이 값은 공식 과거·현재 관측치이며 미래 전망이 아니에요. "
        "계획수익률, 자산배분 비중 또는 리밸런싱 신호에 직접 사용하지 않아요."
    )
    return ChatResponse(
        intent=ChatIntent.MACRO_EVIDENCE,
        answer=f"{answer}\n\n{limitation}",
        data_mode="official_macro_observations",
        sections=[
            AnswerSection(
                kind=SectionKind.FACT,
                title="공식 거시지표 관측값",
                content=answer,
                evidence_ids=_source_ids(sources),
            ),
            AnswerSection(
                kind=SectionKind.LIMITATION,
                title="알고리즘 연결 경계",
                content=limitation,
            ),
        ],
        sources=sources,
        numeric_evidence=numeric_evidence,
        limitations=[
            snapshot.algorithm_usage.reason,
            "보고서 정책 버전: " + snapshot.policy_version,
        ],
    )


def select_macro_metrics(
    message: str,
    snapshot: MacroEvidenceSnapshot,
) -> list[MacroMetric]:
    by_id = {metric.metric_id: metric for metric in snapshot.metrics}
    if re.search(r"거시\s*(?:환경|지표)", message, re.I):
        selected = tuple(by_id)
    elif re.search(r"기대\s*수명|장수", message, re.I):
        selected = (
            "kr_life_expectancy_65_a1",
            "kr_life_expectancy_65_a2",
        )
    elif re.search(
        r"미국|연준|연방\s*기금|FRED|국채|기대\s*인플레이션",
        message,
        re.I,
    ):
        selected = (
            "us_federal_funds_rate",
            "us_cpi_yoy",
            "us_treasury_10y",
            "us_breakeven_inflation_10y",
        )
    elif re.search(
        r"한국|기준\s*금리|소비자\s*물가|물가\s*상승률",
        message,
        re.I,
    ):
        selected = ("kr_base_rate", "kr_cpi_yoy")
    else:
        selected = tuple(by_id)
    return [by_id[metric_id] for metric_id in selected if metric_id in by_id]


def macro_evidence_unavailable() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.MACRO_EVIDENCE,
        answer="공식 거시지표 보고서를 불러오지 못해 수치를 안내하지 않았어요.",
        data_mode="unavailable",
        limitations=["보고서 수집 상태와 경로를 확인한 뒤 다시 조회해 주세요."],
    )
