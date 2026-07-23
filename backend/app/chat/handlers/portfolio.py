"""Portfolio, ETF-theme, and macro-evidence intent handlers."""

import logging
import re
from decimal import ROUND_HALF_UP, Decimal

from ...engine import (
    AccountType,
    EducationalPortfolioEvaluation,
    EducationalPortfolioInput,
    EducationalRiskProfile,
    build_educational_portfolio,
    evaluate_risk_cap,
    select_theme_etf_candidates,
)
from ...engine.educational_portfolio import rebalancing_cadence
from ...etf_component_repository import EtfComponentSnapshotRepository
from ...etf_product_description_repository import (
    EtfProductDescriptionRepository,
)
from ...etf_theme_repository import (
    CommodityEtfSelectionPolicy,
    EtfThemeRepository,
)
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
from ..etf_product_features import (
    DEFAULT_ETF_PRODUCT_RESEARCH_PATH,
    EtfProductFeatureFacts,
    EtfProductFeatureGenerator,
    deterministic_etf_product_feature,
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
    EtfThemeConversationContext,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from ..query_planner import QueryPlan, ThemeContentTopic
from ._shared import (
    _ACCOUNT_TYPE_LABELS,
    _MACRO_ANALOG_OUTCOME_TERMS,
    _RISK_PROFILE_LABELS,
    _SLEEVE_LABELS,
    _STRATEGY_LABELS,
    _STRESS_SCENARIO_LABELS,
    PortfolioUniverseLoader,
    ThemeProductUniverseLoader,
    _decimal_text,
    _one_decimal,
    _rebalancing_items,
    _source_ids,
    _strategy_summary,
    _target_portfolio_rows,
)

logger = logging.getLogger(__name__)

_HOLDING_SCOPE_TITLES = {
    "actual_portfolio": "실제 보유종목 TOP3",
    "creation_basket": "구성 바스켓 TOP3",
    "index_exposure": "기초지수 노출 TOP3",
    "look_through": "룩스루 기준 기업 노출 TOP3",
}
_HOLDING_SCOPE_BASES = {
    "actual_portfolio": "운용사 공식 보유비중",
    "creation_basket": "운용사 공식 설정·환매 바스켓 비중",
    "index_exposure": "공식 기초지수 편입비중",
    "look_through": "공식 자료를 연결한 룩스루 비중",
}


def _risk_profile_rebalancing_text(profile: EducationalRiskProfile) -> str:
    cadence = rebalancing_cadence(profile)
    return (
        f"점검 주기: {cadence.review_interval_months}개월. "
        f"{cadence.rationale}"
    )


def _product_fee_text(value: Decimal | None) -> str:
    if value is None:
        return "확인 필요"
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}%"


def _product_trading_value_text(value: Decimal | None) -> str:
    if value is None:
        return "확인 필요"
    eok_krw = (value / Decimal("100000000")).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    return f"{eok_krw:,.0f}억원"


def _product_trading_volume_text(value: Decimal | None) -> str:
    if value is None:
        return "확인 필요"
    return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}주"


def _representative_reason_text(reason: str) -> str:
    """Make the representative-company rationale a direct declarative sentence."""

    if reason.endswith("이기 때문입니다."):
        return reason.removesuffix("이기 때문입니다.") + "입니다."
    if reason.endswith("기 때문입니다."):
        stem = reason.removesuffix("기 때문입니다.")
        ending = "은" if stem.endswith(("좋", "크")) else "는"
        return f"{stem}{ending} 점이 대표 사례입니다."
    return reason


def _theme_holdings_response(
    *,
    theme_name: str,
    context: EtfThemeConversationContext,
    component_snapshots: EtfComponentSnapshotRepository | None,
) -> ChatResponse:
    if component_snapshots is None:
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer="ETF 구성종목 데이터베이스에 연결할 수 없습니다.",
            data_mode="unavailable",
            limitations=["검증된 ETF 구성정보 스냅샷이 필요합니다."],
            conversation_context=ConversationContext(etf_theme=context),
        )
    try:
        snapshots = component_snapshots.latest_for(context.candidate_isu_codes)
    except Exception:  # noqa: BLE001 — DB 장애는 후보 재선정으로 감추지 않는다.
        logger.warning("etf_component_snapshot_unavailable")
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer="ETF 구성종목 데이터를 불러오지 못했습니다.",
            data_mode="unavailable",
            limitations=["저장된 공식 ETF 구성정보를 다시 확인해 주세요."],
            conversation_context=ConversationContext(etf_theme=context),
        )

    sections: list[AnswerSection] = []
    sources: list[SourceEvidence] = []
    numeric: list[NumericEvidence] = []
    limitations: list[str] = []
    for code, name in zip(
        context.candidate_isu_codes, context.candidate_names, strict=True
    ):
        snapshot = snapshots.get(code)
        if snapshot is None:
            limitations.append(f"{name}의 최신 구성종목 스냅샷이 없습니다.")
            continue
        if not snapshot.holdings:
            limitations.append(f"{name}의 검증된 구성정보 목록이 비어 있습니다.")
            continue
        as_of = snapshot.as_of_date or snapshot.captured_at
        scope_title = _HOLDING_SCOPE_TITLES.get(
            snapshot.source_kind, "공식 구성정보 TOP3"
        )
        source_id = (
            f"{snapshot.source_code}:components:{code}:"
            f"{as_of.isoformat()}"
        )
        sources.append(
            SourceEvidence(
                evidence_id=source_id,
                label=f"{name} {scope_title}",
                locator=snapshot.source_locator,
                publisher=snapshot.publisher,
                as_of=as_of,
                data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
            )
        )
        rows: list[list[str]] = []
        for holding in snapshot.holdings:
            rows.append(
                [
                    holding.component_name,
                    f"{_decimal_text(holding.weight_percent)}%",
                ]
            )
            numeric.append(
                NumericEvidence(
                    label=f"{name} {holding.component_name} 구성 비중",
                    value=holding.weight_percent,
                    unit="%",
                    evidence_id=source_id,
                    basis=_HOLDING_SCOPE_BASES.get(
                        snapshot.source_kind, snapshot.weight_basis
                    ),
                )
            )
        sections.append(
            AnswerSection(
                kind=SectionKind.FACT,
                title=f"{name} {scope_title}",
                content="",
                evidence_ids=[source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.TABLE,
                        headers=["구성종목", "구성비중"],
                        rows=rows,
                    )
                ],
            )
        )
    return ChatResponse(
        intent=ChatIntent.ETF_THEME,
        answer=(
            f"{theme_name} 테마 ETF {len(sections)}개의 공식 상위 구성정보입니다."
            if sections
            else "직전에 소개한 ETF의 구성종목 스냅샷을 아직 준비하지 못했습니다."
        ),
        data_mode="theme_component_holdings" if sections else "unavailable",
        sections=sections,
        sources=sources,
        numeric_evidence=numeric,
        limitations=limitations,
        conversation_context=ConversationContext(etf_theme=context),
    )


def etf_theme_response(
    request: ChatRequest,
    plan: QueryPlan,
    *,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
    theme_product_universe_loader: ThemeProductUniverseLoader | None,
    theme_repository: EtfThemeRepository | None,
    product_descriptions: EtfProductDescriptionRepository | None,
    product_feature_generator: EtfProductFeatureGenerator | None,
    component_snapshots: EtfComponentSnapshotRepository | None,
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
    commodity_policy = theme_repository.commodity_selection_policy(theme.theme_id)
    prior_theme = (
        request.conversation_context.etf_theme
        if request.conversation_context is not None
        else None
    )
    if (
        plan.requests_theme_holdings
        and prior_theme is not None
        and prior_theme.theme_id == theme.theme_id
    ):
        if commodity_policy is not None:
            return _commodity_exposure_response(
                theme_name=theme.name,
                context=prior_theme,
                policy=commodity_policy,
            )
        return _theme_holdings_response(
            theme_name=theme.name,
            context=prior_theme,
            component_snapshots=component_snapshots,
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
        except Exception:  # noqa: BLE001 — 검증 DB 장애 시 카탈로그 답변 유지
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
                            f"{_representative_reason_text(company.representative_reason)}\n\n"
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

    if commodity_policy is None and (
        portfolio_universe_loader is None
        and theme_product_universe_loader is None
    ):
        limitations.append("통합 ETF 상품 데이터를 불러올 수 없습니다.")
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=f"{theme.name} 테마 설명만 제공했습니다.",
            data_mode="unavailable",
            sections=sections,
            sources=sources,
            limitations=limitations,
        )

    numeric: list[NumericEvidence] = []
    candidate_blocks: list[AnswerBlock] = []
    candidate_context_codes: list[str] = []
    candidate_context_names: list[str] = []
    product_description_source_id: str | None = None
    product_feature_source_id: str | None = None
    commodity_source_id: str | None = None
    allowed_product_codes = theme_repository.allowed_product_codes(theme.theme_id)
    if (
        allowed_product_codes is not None
        and theme_repository.product_policy is not None
    ):
        sources.append(
            SourceEvidence(
                evidence_id="policy:theme_product_classification",
                label="검토된 ETF 테마 상품 분류표",
                locator=str(
                    theme_repository.product_policy_path
                    or theme_repository.product_policy.source_document
                ),
                publisher="연금 코파일럿 팀",
                as_of=theme_repository.product_policy.as_of_date,
                data_boundary=DataBoundary.ENGINE,
            )
        )
    if commodity_policy is not None:
        commodity_source_id = "policy:gold_commodities_selection"
        sources.append(
            SourceEvidence(
                evidence_id=commodity_source_id,
                label="승인된 금·원자재 ETF 거래량·운용보수 비교",
                locator=commodity_policy.source_url,
                publisher="연금 코파일럿 팀",
                as_of=commodity_policy.as_of_date,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            )
        )

    loaded_universes = []
    common_products_by_code: dict[str, dict[str, object]] = {}
    if theme_product_universe_loader is not None:
        requested_codes = (
            tuple(sorted(allowed_product_codes))
            if allowed_product_codes is not None
            else None
        )
        if requested_codes is not None and not requested_codes:
            limitations.append("검토된 ETF 테마 상품 분류표가 비어 있습니다.")
        else:
            try:
                universe = theme_product_universe_loader(requested_codes)
            except (FileNotFoundError, ValueError):
                limitations.append("통합 ETF 상품 데이터를 불러오지 못했습니다.")
            else:
                loaded_universes.append(universe)
                for product in universe.products:
                    if not isinstance(product, dict):
                        continue
                    code = str(product.get("isu_code") or "")
                    if code:
                        common_products_by_code.setdefault(code, product)
    elif portfolio_universe_loader is not None:
        for account_type in AccountType:
            try:
                universe = portfolio_universe_loader(account_type)
            except (FileNotFoundError, ValueError):
                limitations.append(
                    f"{_ACCOUNT_TYPE_LABELS[account_type]} ETF 적격 유니버스를 "
                    "불러오지 못했습니다."
                )
                continue
            loaded_universes.append(universe)
            for product in universe.products:
                if not isinstance(product, dict):
                    continue
                code = str(product.get("isu_code") or "")
                if code:
                    common_products_by_code.setdefault(code, product)

    if commodity_policy is not None:
        for product in commodity_policy.products:
            common_products_by_code[str(product["isu_code"])] = product

    common_products = list(common_products_by_code.values())
    if not common_products:
        limitations.append("통합 ETF 상품 데이터가 비어 있습니다.")
        return ChatResponse(
            intent=ChatIntent.ETF_THEME,
            answer=f"{theme.name} 테마 설명만 제공했습니다.",
            data_mode="unavailable",
            sections=sections,
            sources=sources,
            limitations=list(dict.fromkeys(limitations)),
        )

    common_as_of = (
        max(item.as_of for item in loaded_universes)
        if loaded_universes
        else commodity_policy.as_of_date
    )
    if common_products:
        evaluation = select_theme_etf_candidates(
            catalog=theme_repository.catalog,
            theme=theme,
            products=common_products,
            kis_products_by_code=(
                theme_repository.kis_products_by_code
            ),
            component_snapshot_date=(
                theme_repository.component_snapshot_date
            ),
            limit=plan.max_results,
            allowed_isu_codes=allowed_product_codes,
            ordered_candidate_groups=(
                commodity_policy.ordered_candidate_groups
                if commodity_policy is not None
                else None
            ),
        )
        if evaluation.status != "ok":
            limitations.extend(evaluation.limitations)
            limitations.append(
                "투자성향·보유 계좌를 반영한 매수 추천이 아니라 거래대금·총보수 "
                "기준의 정보성 비교 후보입니다."
            )
            return ChatResponse(
                intent=ChatIntent.ETF_THEME,
                answer=(
                    f"{theme.name} 테마에서 거래대금과 총보수를 확인할 수 있는 "
                    "ETF 상품이 현재 부족합니다."
                    if allowed_product_codes is not None
                    else f"{theme.name} 테마 설명만 제공했습니다."
                ),
                data_mode="theme_overview_only",
                sections=sections,
                sources=sources,
                limitations=list(dict.fromkeys(limitations)),
                conversation_context=ConversationContext(
                    last_intent=ChatIntent.ETF_THEME
                ),
            )
        master_source_id = "engine:theme_candidates:common"
        sources.append(
            SourceEvidence(
                evidence_id=master_source_id,
                label="ETF 통합 상품 데이터",
                locator="engine://etf-theme/common-universe",
                publisher="연금 코파일럿 규칙 엔진",
                as_of=common_as_of,
                data_boundary=DataBoundary.ENGINE,
            )
        )
        remaining = plan.max_results - len(candidate_blocks)
        selected_candidates = evaluation.candidates[:remaining]
        products_by_code = {
            str(product.get("isu_code") or ""): product
            for product in common_products
            if isinstance(product, dict)
        }
        descriptions = {
            candidate.isu_code: (
                product_descriptions.get(candidate.isu_name)
                if product_descriptions is not None
                else None
            )
            for candidate in selected_candidates
        }
        feature_facts: dict[str, EtfProductFeatureFacts] = {}
        for candidate in selected_candidates:
            product = products_by_code.get(candidate.isu_code, {})
            metrics = product.get("implementation_metrics")
            classification = product.get("classification")
            if not isinstance(metrics, dict):
                metrics = {}
            if not isinstance(classification, dict):
                classification = {}
            description = descriptions[candidate.isu_code]
            feature_facts[candidate.isu_code] = EtfProductFeatureFacts(
                isu_code=candidate.isu_code,
                product_name=candidate.isu_name,
                theme_name=theme.name,
                approved_description=(
                    description.one_line_description if description else None
                ),
                benchmark_name=(
                    str(metrics["benchmark_name"]).strip()
                    if metrics.get("benchmark_name")
                    else None
                ),
                classification=classification,
                top_holding_names=tuple(
                    holding.component_name for holding in candidate.top_holdings[:5]
                ),
            )
        generated_features: dict[str, str] = {}
        if product_feature_generator is not None and feature_facts:
            try:
                generated_features = product_feature_generator.generate(
                    tuple(feature_facts.values())
                )
            except Exception:  # noqa: BLE001 — 카드 전체는 결정론 폴백으로 유지
                logger.warning("etf_product_feature_generator_unavailable")

        for candidate in selected_candidates:
            if len(candidate_blocks) >= plan.max_results:
                break
            rank = len(candidate_blocks) + 1
            candidate_evidence_id = commodity_source_id or master_source_id
            fee_text = _product_fee_text(candidate.fee_percent)
            if candidate.fee_percent is not None:
                displayed_fee = candidate.fee_percent.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                numeric.append(
                    NumericEvidence(
                        label=f"{candidate.isu_name} 총보수",
                        value=candidate.fee_percent,
                        unit="%",
                        evidence_id=candidate_evidence_id,
                        basis=(
                            commodity_policy.metric_basis
                            if commodity_policy is not None
                            else "ETF 통합 실데이터 마스터"
                        ),
                    )
                )
                if displayed_fee != candidate.fee_percent:
                    numeric.append(
                        NumericEvidence(
                            label=f"{candidate.isu_name} 표시 운용보수",
                            value=displayed_fee,
                            unit="%",
                            evidence_id=candidate_evidence_id,
                            basis="원본 총보수를 소수점 둘째 자리로 반올림",
                        )
                    )
            trading_value_text = _product_trading_value_text(
                candidate.median_daily_trading_value_krw
            )
            trading_volume_text = _product_trading_volume_text(
                candidate.average_daily_trading_volume
            )
            if (
                commodity_policy is not None
                and candidate.average_daily_trading_volume is not None
            ):
                numeric.append(
                    NumericEvidence(
                        label=f"{candidate.isu_name} 최근 일평균 거래량",
                        value=candidate.average_daily_trading_volume,
                        unit="주",
                        evidence_id=candidate_evidence_id,
                        basis=commodity_policy.metric_basis,
                    )
                )
            elif candidate.median_daily_trading_value_krw is not None:
                displayed_trading_value = (
                    candidate.median_daily_trading_value_krw
                    / Decimal("100000000")
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal(
                    "100000000"
                )
                numeric.append(
                    NumericEvidence(
                        label=f"{candidate.isu_name} 일별 거래대금 중앙값",
                        value=candidate.median_daily_trading_value_krw,
                        unit="KRW",
                        evidence_id=candidate_evidence_id,
                        basis="ETF 통합 실데이터 마스터의 관측기간 중앙값",
                    )
                )
                if (
                    displayed_trading_value
                    != candidate.median_daily_trading_value_krw
                ):
                    numeric.append(
                        NumericEvidence(
                            label=f"{candidate.isu_name} 표시 하루 평균 거래대금",
                            value=displayed_trading_value,
                            unit="KRW",
                            evidence_id=candidate_evidence_id,
                            basis="관측기간 중앙값을 억원 단위로 반올림",
                        )
                    )
            description = descriptions[candidate.isu_code]
            if description is not None and product_description_source_id is None:
                product_description_source_id = "verified:etf_product_descriptions"
                sources.append(
                    SourceEvidence(
                        evidence_id=product_description_source_id,
                        label="승인 ETF 상품 설명 카탈로그",
                        locator=str(
                            product_descriptions.source_path
                            or "approved-etf-product-database"
                        ),
                        publisher="연금 코파일럿 팀",
                        as_of=description.as_of_date,
                        data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                    )
                )
            feature_text = generated_features.get(
                candidate.isu_code,
                deterministic_etf_product_feature(
                    feature_facts[candidate.isu_code]
                ),
            )
            if generated_features and product_feature_source_id is None:
                product_feature_source_id = "verified:etf_product_feature_evidence"
                sources.append(
                    SourceEvidence(
                        evidence_id=product_feature_source_id,
                        label="ETF 상품 설명 통합 원문·공식 설명",
                        locator=DEFAULT_ETF_PRODUCT_RESEARCH_PATH.as_posix(),
                        publisher="연금 코파일럿 팀",
                        as_of=common_as_of,
                        data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                    )
                )
            candidate_blocks.append(
                AnswerBlock(
                    kind=AnswerBlockKind.CALLOUT,
                    title=f"{rank}. {candidate.isu_name}",
                    text=(
                        f"연간 수수료율(운용보수): {fee_text}\n\n"
                        + (
                            f"최근 일평균 거래량: {trading_volume_text}\n\n"
                            if commodity_policy is not None
                            else f"하루 평균 거래대금: {trading_value_text}\n\n"
                        )
                        + f"상품 특징: {feature_text}"
                    ),
                )
            )
            candidate_context_codes.append(candidate.isu_code)
            candidate_context_names.append(candidate.isu_name)

    if candidate_blocks:
        master_ids = [
            source.evidence_id
            for source in sources
            if source.evidence_id.startswith("engine:theme_candidates:")
            or source.evidence_id
            in {
                "policy:theme_product_classification",
                "policy:gold_commodities_selection",
            }
        ]
        if product_description_source_id is not None:
            master_ids.append(product_description_source_id)
        if product_feature_source_id is not None:
            master_ids.append(product_feature_source_id)
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마 ETF상품",
                content="",
                evidence_ids=master_ids,
                blocks=candidate_blocks,
            )
        ]
    else:
        limitations.append(
            "통합 상품 데이터에서 제시 가능한 테마 ETF 비교 후보가 "
            "없습니다."
        )

    limitations.append(
        "투자성향·보유 계좌를 반영한 매수 추천이 아니라 "
        + (
            "금·은·구리별 거래량·운용보수 기준의 정보성 비교 후보입니다."
            if commodity_policy is not None
            else "거래대금·총보수 기준의 정보성 비교 후보입니다."
        )
    )
    candidate_context = (
        EtfThemeConversationContext(
            theme_id=theme.theme_id,
            candidate_isu_codes=candidate_context_codes,
            candidate_names=candidate_context_names,
        )
        if candidate_context_codes
        else None
    )
    if plan.requests_theme_holdings and candidate_context is not None:
        if commodity_policy is not None:
            return _commodity_exposure_response(
                theme_name=theme.name,
                context=candidate_context,
                policy=commodity_policy,
            )
        return _theme_holdings_response(
            theme_name=theme.name,
            context=candidate_context,
            component_snapshots=component_snapshots,
        )

    return ChatResponse(
        intent=ChatIntent.ETF_THEME,
        answer=(
            (
                f"{theme.name} 테마에서 금·은·구리별로 거래량과 운용보수를 "
                "비교해 선정한 ETF 3개입니다."
                if commodity_policy is not None
                else f"{theme.name} 테마에서 거래가 가장 활발하고 "
                "수수료가 저렴한 ETF 3개를 보여드리겠습니다."
            )
            if candidate_blocks
            else f"{theme.name} 테마 설명만 제공했습니다."
        ),
        data_mode=(
            "theme_candidates" if candidate_blocks else "theme_overview_only"
        ),
        sections=sections,
        sources=sources,
        numeric_evidence=numeric,
        limitations=list(dict.fromkeys(limitations)),
        conversation_context=ConversationContext(
            last_intent=ChatIntent.ETF_THEME,
            etf_theme=candidate_context,
        ),
    )


def _commodity_exposure_response(
    *,
    theme_name: str,
    context: EtfThemeConversationContext,
    policy: CommodityEtfSelectionPolicy,
) -> ChatResponse:
    source_id = "policy:gold_commodities_physical_exposure"
    source = SourceEvidence(
        evidence_id=source_id,
        label="승인된 금·원자재 ETF 조사 대화",
        locator=policy.source_url,
        publisher="연금 코파일럿 팀",
        as_of=policy.as_of_date,
        data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
    )
    sections: list[AnswerSection] = []
    numeric: list[NumericEvidence] = []
    limitations: list[str] = []
    for code, name in zip(
        context.candidate_isu_codes, context.candidate_names, strict=True
    ):
        exposure_label = policy.exposure_label(code)
        if exposure_label is None:
            limitations.append(f"{name}의 승인된 실물가격 노출 구분이 없습니다.")
            continue
        sections.append(
            AnswerSection(
                kind=SectionKind.FACT,
                title=f"{name} 실물가격 노출",
                content="",
                evidence_ids=[source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.TABLE,
                        headers=["실물가격 노출", "노출비중"],
                        rows=[[exposure_label, "100%"]],
                    )
                ],
            )
        )
        numeric.append(
            NumericEvidence(
                label=f"{name} {exposure_label} 노출비중",
                value=Decimal("100"),
                unit="%",
                evidence_id=source_id,
                basis="승인된 공유 대화의 실물가격 추종 분류",
            )
        )
    limitations.append(
        "100%는 이 답변에서 사용하는 실물가격 추종 노출 구분이며, "
        "일반 주식형 ETF의 보유종목 TOP3 표가 아닙니다."
    )
    return ChatResponse(
        intent=ChatIntent.ETF_THEME,
        answer=(
            f"직전에 소개한 {theme_name} ETF 3개의 실물가격 노출은 "
            "각각 금 현물 100%, 은 현물 100%, 구리 실물 100%입니다."
        ),
        data_mode="theme_physical_commodity_exposure",
        sections=sections,
        sources=[source],
        numeric_evidence=numeric,
        limitations=limitations,
        conversation_context=ConversationContext(etf_theme=context),
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
            f"{_ACCOUNT_TYPE_LABELS[evaluation.evaluated_input.account_type]} 예시 "
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
        limitations=["입력한 포트폴리오를 기준으로 계산했습니다."],
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
    stable_rebalancing = _risk_profile_rebalancing_text(
        EducationalRiskProfile.STABLE
    )
    stable_seeking_rebalancing = _risk_profile_rebalancing_text(
        EducationalRiskProfile.STABLE_SEEKING
    )
    neutral_rebalancing = _risk_profile_rebalancing_text(
        EducationalRiskProfile.RISK_NEUTRAL
    )
    active_rebalancing = _risk_profile_rebalancing_text(
        EducationalRiskProfile.ACTIVE
    )
    aggressive_rebalancing = _risk_profile_rebalancing_text(
        EducationalRiskProfile.AGGRESSIVE
    )
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
                    "수익을 좇아 자산 구성을 자주 바꾸지 않아요.\n"
                    + stable_rebalancing
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
                    "납입금을 채권·현금 등 부족한 방어자산에 먼저 배분해요.\n"
                    + stable_seeking_rebalancing
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
                    "리밸런싱으로 목표 구성을 꾸준히 유지해요.\n"
                    + neutral_rebalancing
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
                    "추격 매수하지 않고 부족한 핵심자산부터 채워요.\n"
                    + active_rebalancing
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
                    "채운 뒤, 허용 범위 안에서만 전술자산을 운용해요.\n"
                    + aggressive_rebalancing
                ),
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="공통 실행 원칙",
                content=(
                    "ETF 후보는 과거 수익률 순위가 아니라 비용, 거래대금, "
                    "순자산, 괴리율, 추적오차, 관측기간으로 비교해요. 성향별 "
                    "점검 주기에 맞춰 목표비중 이탈을 확인해요. 새 납입금은 "
                    "부족한 자산군에 먼저 배분해요. 매년 나이와 설문 투자성향, "
                    "손실 감내 수준, 연금 수령 시점을 다시 확인해 목표 구성을 갱신해요."
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
        label="연금 포트폴리오 규칙 엔진",
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
            basis=f"{_SLEEVE_LABELS[target.sleeve]} 목표 비중을 정한 규칙 엔진 배분",
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
    numeric.append(
        NumericEvidence(
            label="리밸런싱 정기 점검 주기",
            value=Decimal(evaluation.rebalancing.cadence.review_interval_months),
            unit="개월",
            evidence_id=engine_source.evidence_id,
            basis="투자성향별 변동성·전술자산 비중을 반영한 규칙 엔진 점검 정책",
        )
    )
    numeric.extend(
        NumericEvidence(
            label=(
                _STRESS_SCENARIO_LABELS.get(
                    stress.scenario_code,
                    "기타 시장 충격",
                )
                + " 스트레스 손실 추정치"
            ),
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
        f"{_decimal_text(base)}%예요. J.P. Morgan의 LTCMA 장기 "
        "자본시장 가정과 ETF 운용비용을 반영해 산출한 "
        "계획가정이며, 미래 예측값이 아니라 매년 다시 살펴봐요."
        )
    profile_label = _RISK_PROFILE_LABELS[
        evaluation.evaluated_input.risk_profile.value
    ]
    strategy_label = _STRATEGY_LABELS[evaluation.strategy_label]
    sections = [
        AnswerSection(
            kind=SectionKind.SERVICE_EXPLANATION,
            title=f"{profile_label}의 {strategy_label}",
            content=_strategy_summary(evaluation),
            evidence_ids=[engine_source.evidence_id],
        ),
        AnswerSection(
            kind=SectionKind.SERVICE_EXPLANATION,
            title="목표 자산배분",
            content=(
                f"이 전략에 따르면 {profile_label} 연금투자전략의 목표 "
                "자산배분은 아래와 같아요."
            ),
            evidence_ids=[engine_source.evidence_id],
            blocks=[
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    title="목표 포트폴리오",
                    headers=["자산군", "목표비중", "엔진 편입 후보"],
                    rows=_target_portfolio_rows(evaluation),
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    title="운용 원칙",
                    items=_rebalancing_items(evaluation),
                ),
            ],
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
        AnswerSection(
            kind=SectionKind.SERVICE_EXPLANATION,
            title="ETF 섹터 알아보기",
            content=(
                "전체적인 자산배분의 틀은 이렇게 가져가고, 각 자산 분류를 "
                "어떤 테마 ETF로 채울지는 ETF 섹터 알아보기에서 탐색해 "
                "보세요. 구체 종목의 매수 추천은 하지 않아요."
            ),
            evidence_ids=[engine_source.evidence_id],
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
        "리밸런싱 이탈 기준": 4,
    }
    numeric.sort(
        key=lambda item: numeric_priority.get(
            item.label,
            6
            if item.label.endswith(" 목표비중")
            else 6
            if item.label.endswith(" 스트레스 손실 추정치")
            else 7,
        )
    )
    display_evaluation = evaluation.model_copy(
        update={
            "strategy_label": _STRATEGY_LABELS.get(
                evaluation.strategy_label,
                "연금 자산배분 전략",
            )
        }
    )
    return ChatResponse(
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        answer=(
            f"설문 결과는 {profile_label}이며, 가장 적합한 연금투자전략은 "
            f"{strategy_label}입니다."
        ),
        data_mode="engine_educational_planning",
        sources=sources,
        numeric_evidence=numeric,
        sections=sections,
        educational_portfolio_evaluation=display_evaluation,
        educational_portfolio_evaluations=[display_evaluation],
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
