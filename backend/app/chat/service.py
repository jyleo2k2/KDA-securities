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
    ScenarioPortfolioInput,
    WithdrawalCalculationStatus,
    build_educational_portfolio,
    evaluate_mock_scenario,
    evaluate_risk_cap,
    select_theme_etf_candidates,
)
from ..etf_theme_repository import EtfThemeRepository
from ..macro_evidence import (
    MacroEvidenceRepository,
    MacroEvidenceSnapshot,
    MacroEvidenceUnavailable,
    MacroMetric,
)
from ..retrieval.knowledge_policy import (
    contains_sensitive_personal_data,
    contains_unsafe_rag_content,
)
from ..retrieval.repository import KnowledgeMatch, KnowledgeSearch, NewsMatch
from .cards import build_suggested_follow_ups
from .disclosures import ProviderDisclosure
from .models import (
    AnswerBlock,
    AnswerBlockKind,
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
from .narrator import contains_unsafe_financial_claim
from .pension_account_overview import (
    build_deferred_pension_topic_response,
    build_pension_account_overview_response,
)
from .pension_tax_parser import resolve_pension_tax_inputs
from .query_planner import AccountRuleTopic, BlockedReason, QueryPlan, plan_question
from .routing import IntentRouter, NewsFollowUp, NewsFollowUpAction
from .scenarios import ScenarioRepository
from .tools import (
    PENSION_TAX_CLOSING_NOTICE,
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)

logger = logging.getLogger(__name__)


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

    def recent_market_news(
        self,
        *,
        region: str | None = None,
        days: int = 5,
        limit: int = 3,
        exclude_item_ids: tuple[str, ...] = (),
        preferred_topics: tuple[str, ...] = (),
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
    r"|(?:현재|보유).{0,20}(?:ETF|포트폴리오|리밸런싱|운용\s*전략)"
)
_ASSET_CLASS_LABELS = {
    "deposit": "원리금보장형 자산",
    "cash": "현금성 자산",
    "bond": "채권형 자산",
    "domestic_equity": "국내 주식형 자산",
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
    summary = "\n".join(item.summary_lines)
    return f"{label} 뉴스 — {headline}\n{summary}\n원문 링크: {item.original_url}"


def _news_comparison_block(item: NewsMatch, index: int) -> str:
    published = (
        item.published_at.date().isoformat()
        if item.published_at is not None
        else "확인되지 않음"
    )
    summary_lines = list(item.summary_lines)
    return "\n".join(
        (
            f"{index + 1}번째 기사",
            f"제목: {item.title}",
            f"발행일: {published}",
            f"핵심 1: {summary_lines[0]}",
            f"핵심 2: {summary_lines[1]}",
            f"핵심 3: {summary_lines[2]}",
            f"원문 링크: {item.original_url}",
        )
    )


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _one_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _scenario_holdings_summary(
    scenario: ScenarioPortfolioInput,
) -> tuple[str, list[NumericEvidence]]:
    """Return account-level holdings without turning mock data into an order."""

    lines: list[str] = []
    evidence: list[NumericEvidence] = []
    for account in scenario.accounts:
        total = sum(
            (holding.amount_krw for holding in account.holdings), Decimal("0")
        )
        entries: list[str] = []
        for holding in account.holdings:
            weight = (
                _one_decimal(holding.amount_krw / total * Decimal("100"))
                if total != 0
                else Decimal("0")
            )
            display_name = holding.instrument_name
            if holding.etf_isu_code is not None:
                display_name += f" ({holding.etf_isu_code})"
            entries.append(f"{display_name} {_decimal_text(weight)}%")
            evidence.append(
                NumericEvidence(
                    label=(
                        f"{account.label} {holding.instrument_name} 보유 비중"
                    ),
                    value=weight,
                    unit="%",
                    evidence_id="mock:scenario",
                    basis="목시나리오 보유 금액 / 계좌별 보유 금액",
                )
            )
        lines.append(f"{account.label}: " + " · ".join(entries))
    return "\n".join(lines), evidence


def _scenario_rebalancing_summary(duplicated_asset_classes: list[str]) -> str:
    if duplicated_asset_classes:
        duplicated = " · ".join(
            _ASSET_CLASS_LABELS[asset] for asset in duplicated_asset_classes
        )
        return (
            f"여러 계좌에 {duplicated}이(가) 겹쳐 있어 리밸런싱 점검이 "
            "필요해요. 다만 이 예시에는 성향별 목표비중과 추가 납입액이 "
            "없어서 매수·매도 수량은 계산하지 않았어요."
        )
    return (
        "계좌 사이에 겹친 자산군은 없어요. 다만 성향별 목표비중과 추가 납입액이 "
        "없어서 리밸런싱 필요 여부를 확정하거나 매수·매도 수량을 계산하지 않았어요."
    )


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
_NUMBERED_HEADING = re.compile(r"^\s*\d+(?:-\d+)?\.\s+")
_MARKDOWN_LINK = re.compile(r"\[([^]]+)]\([^)]+\)")
_MARKDOWN_HEADING = re.compile(r"^(#+)\s+")
_SENSITIVE_KNOWLEDGE_PROMPT = re.compile(
    r"(?:계좌\s*번호|주민\s*등록\s*번호|비밀\s*번호|OTP|인증\s*번호)"
    r".{0,30}?(?:입력|알려|보내|제공)",
    re.I,
)
_PROMPT_NEGATION = re.compile(r"^\s*(?:하?지\s*마|하?지\s*않|금지)")


def _knowledge_topic(
    message: str, plan: QueryPlan
) -> tuple[str, str, str | None, str | None, str | None]:
    """Return retrieval hints only; every rule remains in approved documents."""

    if re.search(r"공제\s*율|절감\s*률|환급\s*률", message):
        return (
            "tax_rate",
            "연금계좌 세액공제 공제율 공식 안내",
            "연금계좌 세액공제",
            "3. 공제율",
            None,
        )
    if re.search(r"세액\s*공제", message) and "한도" in message:
        return (
            "tax_limit",
            "연금계좌 세액공제 납입 한도 공식 안내",
            "연금계좌 세액공제",
            "2. 납입 한도",
            None,
        )
    if "중도인출" in message and re.search(r"사유|요건|조건|가능", message):
        return (
            "withdrawal_requirements",
            "IRP DC형 중도인출 요건 사유 확인 기준",
            "퇴직연금 수령·중도인출",
            "2. 중도인출은 일반 인출이 아니다",
            None,
        )
    if re.search(r"연금\s*외\s*수령|중도\s*해지", message):
        return (
            "non_pension_tax",
            "연금외수령 중도해지 과세 구조 국세청 공식 안내",
            "연금수령 과세",
            "국세청 안내의 주요 세율",
            None,
        )
    if re.search(r"연금(?:\s*계좌)?\s*수령", message) and re.search(
        r"개시|요건|조건|몇\s*살", message
    ):
        return (
            "receipt_start",
            "IRP 연금 수령 개시 요건 확인 기준",
            "퇴직연금 수령·중도인출",
            "1. IRP 연금 수령의 기본 요건",
            None,
        )
    if re.search(r"연금(?:\s*계좌)?\s*수령", message) and re.search(
        r"과세|세금|세율", message
    ):
        return (
            "receipt_tax",
            "연금수령 과세 자금 원천 수령 방식 확인",
            "연금수령 과세",
            "국세청 안내의 주요 세율",
            None,
        )
    if "위험자산" in message:
        return (
            "risk_cap",
            "DC형 IRP 연금저축 위험자산 한도 핵심 비교",
            "연금 기초",
            "4-2. 세 계좌의 비세금 핵심 비교",
            None,
        )
    if re.search(r"차이|비교|각각|개요", message):
        return (
            "overview",
            "DC형 IRP 연금저축 세 계좌 비세금 핵심 비교",
            "연금 기초",
            "4-2. 세 계좌의 비세금 핵심 비교",
            "| 항목 |",
        )
    definition = re.search(
        r"(?<![A-Za-z])(?:IRP|DC)(?![A-Za-z])\s*(?:란|은|는)\s*(?:뭐|무엇)?"
        r"|(?:연금저축|IRP|DC).{0,6}어떤\s*계좌"
        r"|어떤\s*계좌.{0,6}(?:연금저축|IRP|DC)",
        message,
        re.I,
    )
    if len(plan.account_types) == 1 and definition is not None:
        account_type = plan.account_types[0]
        heading = (
            "4. 3층 — 개인연금 (연금저축)"
            if account_type == AccountType.PENSION_SAVINGS
            else "3. 2층 — 퇴직연금 (DB · DC · IRP)"
        )
        return (
            "definition",
            f"{_ACCOUNT_TYPE_LABELS[account_type]} 계좌 정의",
            "연금 기초",
            heading,
            None,
        )
    return "general", "", None, None, None


def _knowledge_content_is_unsafe(content: str) -> bool:
    if (
        contains_sensitive_personal_data(content)
        or contains_unsafe_rag_content(content)
        or contains_unsafe_financial_claim(content)
    ):
        return True
    return any(
        _PROMPT_NEGATION.search(content[match.end() : match.end() + 16]) is None
        for match in _SENSITIVE_KNOWLEDGE_PROMPT.finditer(content)
    )


def _select_knowledge_match(
    matches: list[KnowledgeMatch],
    *,
    title: str | None,
    heading: str | None,
    required: str | None,
) -> KnowledgeMatch | None:
    """Preserve retrieval order and apply only a topic-document threshold."""

    for match in matches:
        if _knowledge_content_is_unsafe(match.content):
            continue
        if title is not None and title not in match.title:
            continue
        if heading is not None and heading not in match.content:
            continue
        if required is not None and required not in match.content:
            continue
        return match
    return None


def _plain_knowledge_excerpt(content: str, *, heading: str | None) -> str:
    """Render one complete retrieved section as plain text and bullets."""

    raw_lines = content.splitlines()
    start = 0
    if heading is not None:
        start = next((i for i, line in enumerate(raw_lines) if heading in line), -1)
        if start < 0:
            return ""
    section: list[str] = []
    start_heading = raw_lines[start].strip()
    start_markdown_heading = _MARKDOWN_HEADING.match(start_heading)
    start_heading_level = (
        len(start_markdown_heading.group(1))
        if start_markdown_heading is not None
        else None
    )
    for line in raw_lines[start:]:
        stripped = line.strip()
        markdown_heading = _MARKDOWN_HEADING.match(stripped)
        if (
            section
            and start_heading_level is not None
            and markdown_heading is not None
            and len(markdown_heading.group(1)) <= start_heading_level
        ):
            break
        if section and _NUMBERED_HEADING.match(stripped):
            if stripped == start_heading:
                continue
            break
        if section and heading is not None and stripped == start_heading:
            break
        section.append(line)

    plain: list[str] = []
    table_header: list[str] | None = None
    for raw_line in section:
        line = raw_line.strip().lstrip("> ").strip()
        line = _MARKDOWN_LINK.sub(r"\1", line)
        line = line.replace("**", "").replace("`", "").lstrip("# ")
        if not line or line == "---":
            continue
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            if table_header is None:
                table_header = cells
                continue
            label, *values = cells
            details = "; ".join(
                f"{column}: {value}"
                for column, value in zip(table_header[1:], values, strict=False)
            )
            plain.append(f"- {label}: {details}")
        elif table_header is not None:
            break
        elif _NUMBERED_HEADING.match(line):
            plain.append(line)
        elif line.startswith(("-", "•")):
            plain.append(f"- {line.lstrip('-• ').strip()}")
        elif plain and plain[-1].startswith("- "):
            plain[-1] = f"{plain[-1]} {line}"
        else:
            plain.append(f"- {line}")
    bounded: list[str] = []
    for line in plain:
        candidate = "\n".join((*bounded, line))
        if len(candidate) > 850:
            break
        bounded.append(line)
    return "\n".join(bounded)


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
_AGE_STYLE_PORTFOLIO_GUIDE = re.compile(
    r"(?:나이|연령)\s*대?별|20\s*대.{0,30}50\s*대"
)
_STYLE_COMPARISON = re.compile(r"투자\s*(?:성향|스타일)\s*별")
_RETIREMENT_START_AGE = re.compile(
    r"(?:연금\s*)?(?:수령|은퇴)(?:\s*개시)?(?:\s*(?:시점)?(?:은|을|를))?"
    r"\s*(\d{2,3})\s*세"
    r"|(\d{2,3})\s*세(?:부터)?(?:로)?\s*(?:연금\s*)?(?:수령|은퇴)"
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
    "long_term_growth_core": "주식 ETF를 장기 성장 핵심자산으로 둬요.",
    "inflation_and_diversification": (
        "실물자산은 물가 상승에 대비하고 자산을 나누는 역할을 해요."
    ),
    "capped_tactical_satellite": (
        "전술자산은 비중 한도가 있는 보조자산으로만 활용해요."
    ),
    "drawdown_buffer": "채권은 가격 하락 충격을 줄이는 역할을 해요.",
    "liquidity_and_rebalancing_reserve": (
        "현금은 필요할 때 바로 쓰고 비중을 다시 맞출 여유를 줘요."
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


def _requests_age_style_portfolio_guide(message: str) -> bool:
    return (
        _AGE_STYLE_PORTFOLIO_GUIDE.search(message) is not None
        and _STYLE_COMPARISON.search(message) is not None
        and _RISK_PROFILE_PORTFOLIO_REQUEST.search(message) is not None
    )


def _mentioned_retirement_start_age(message: str) -> int | None:
    match = _RETIREMENT_START_AGE.search(message)
    if match is None:
        return None
    return int(match.group(1) or match.group(2))


def _strategy_summary(evaluation: EducationalPortfolioEvaluation) -> str:
    profile = _RISK_PROFILE_LABELS[evaluation.evaluated_input.risk_profile.value]
    strategy = _STRATEGY_LABELS[evaluation.strategy_label]
    role_sentences = [
        _ROLE_SENTENCES[target.role] for target in evaluation.target_sleeves
    ]
    return (
        f"{evaluation.planning_horizon_years}년의 장기 운용기간을 고려한 "
        f"{profile} {strategy}이에요. " + " ".join(role_sentences)
    )


def _target_portfolio_summary(
    evaluation: EducationalPortfolioEvaluation,
) -> str:
    candidates_by_sleeve: dict[str, list[str]] = {}
    for candidate in evaluation.candidates:
        candidates_by_sleeve.setdefault(candidate.sleeve, []).append(
            candidate.isu_name
        )
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
        + f"\n일반 위험자산 목표비중은 전체의 약 {risk_target}%예요."
    )


def _rebalancing_summary(evaluation: EducationalPortfolioEvaluation) -> str:
    rebalancing = evaluation.rebalancing
    threshold = _decimal_text(
        _one_decimal(rebalancing.drift_threshold_percent_points)
    )
    parts = [
        f"목표비중에서 {threshold}%포인트를 초과해 벗어난 자산군은 "
        "리밸런싱(자산 비중을 목표에 맞게 다시 조정하는 일) 점검 대상이에요."
    ]
    if rebalancing.contribution_first:
        parts.append("매도보다 새 납입금을 부족한 자산에 먼저 나눠요.")
    if not rebalancing.sell_instruction_produced:
        parts.append("자동 매도 지시는 만들지 않아요.")
    if rebalancing.status == "not_requested":
        parts.append("보유자산 입력이 없어 현재 차이는 계산하지 않았어요.")
    else:
        review = [
            _SLEEVE_LABELS[item.sleeve]
            for item in rebalancing.sleeves
            if item.status != "within_drift_band"
        ]
        if review:
            parts.append(f"현재 입력에서는 {' · '.join(review)}을(를) 점검해요.")
        else:
            parts.append("현재 입력에서는 모든 자산군이 허용 범위 안이에요.")
        if rebalancing.status == "partial_unclassified_holdings":
            parts.append("분류되지 않은 보유자산은 따로 확인해야 해요.")
    parts.extend(
        [
            "분기마다 목표비중 이탈을 점검해요.",
            "매년 나이·투자성향·연금 수령 시점과 계획가정을 다시 확인해요.",
        ]
    )
    return " ".join(parts)


def _knowledge_evidence_id(match: KnowledgeMatch) -> str:
    # Local-fallback ids are not DB chunk ids; a distinct namespace keeps them
    # out of the chunk-FK persistence path (source chip is still shown). Answer
    # sections and source chips must use this same id or validation fails.
    prefix = "local-knowledge" if match.is_local_fallback else "knowledge"
    return f"{prefix}:{match.chunk_id}"


_OFFICIAL_SOURCE_BY_DOCUMENT = {
    "project://docs/20_리서치/연금_기초.md": (
        "퇴직연금제도 안내",
        "https://www.moel.go.kr/retirementpay.do",
        "고용노동부",
    ),
    "project://docs/40_규제/연금계좌_세액공제.md": (
        "연금계좌 세액공제 안내",
        "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7875",
        "국세청",
    ),
    "project://docs/40_규제/퇴직연금_수령_중도인출.md": (
        "IRP·DC형 중도인출 사유",
        (
            "https://m.easylaw.go.kr/MOB/CsmInfoRetrieve.laf?"
            "ccfNo=2&cciNo=1&cnpClsNo=2&csmSeq=999"
        ),
        "찾기쉬운 생활법령",
    ),
    "project://docs/40_규제/사전지정운용제도_디폴트옵션.md": (
        "디폴트옵션과 위험자산 한도 예외",
        (
            "https://www.moel.go.kr/news/enews/report/"
            "enewsView.do?news_seq=13711"
        ),
        "고용노동부",
    ),
}


def _knowledge_sources(matches: list[KnowledgeMatch]) -> list[SourceEvidence]:
    sources: list[SourceEvidence] = []
    seen_locators: set[str] = set()
    for match in matches:
        official = _OFFICIAL_SOURCE_BY_DOCUMENT.get(match.source_url)
        label, locator, publisher = official or (
            match.title,
            match.source_url,
            "연금 코파일럿 검증 지식",
        )
        if locator in seen_locators:
            continue
        seen_locators.add(locator)
        sources.append(
            SourceEvidence(
                evidence_id=_knowledge_evidence_id(match),
                label=label,
                locator=locator,
                publisher=publisher,
                as_of=match.as_of_date,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            )
        )
    return sources


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
        theme_repository: EtfThemeRepository | None = None,
        macro_evidence: MacroEvidenceRepository | None = None,
        router: IntentRouter | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scenarios = scenarios
        self._disclosures = disclosures
        self._news = news
        self._portfolio_universe_loader = portfolio_universe_loader
        self._theme_repository = theme_repository
        self._macro_evidence = macro_evidence
        self._router = router or IntentRouter()

    def capabilities(self) -> ChatCapabilities:
        return ChatCapabilities(
            supported=[
                "DC형·IRP·연금저축 계좌 규칙 근거 Q&A",
                "목계좌 시나리오 위험자산 한도와 통합 자산군 진단",
                "연령·성향·수령개시연령별 교육용 포트폴리오 위험·계획가정",
                "ETF 테마 1~23의 구조·기회·위험 설명",
                "연금저축·IRP 당해연도 납입액 세액공제 간이 계산",
                "연금저축·IRP 연금외수령 16.5% 간이 추정",
                "근거·기준일·실데이터/목데이터 경계 표시",
                "한국은행·KOSIS·FRED 공식 거시지표 근거 조회",
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
            scenario_codes=[item.code for item in self._scenarios.list()],
        )

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
                    response = self._retirement_age_selection_guide()
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
                    response = self._age_style_portfolio_guide()
                elif _requests_risk_profile_guide(original_request.message):
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
            elif resolved_plan.intent == ChatIntent.ETF_THEME:
                response = self._etf_theme_response(
                    original_request,
                    resolved_plan,
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
                        preferred_topics=preferred_news_topics,
                    )
            elif resolved_plan.intent == ChatIntent.MACRO_EVIDENCE:
                response = self._macro_evidence_response(request)
            elif resolved_plan.intent == ChatIntent.PROVIDER_DISCLOSURE:
                account_type = resolved_plan.account_types[0]
                response = self._disclosure_response(request, account_type)
            elif resolved_plan.intent == ChatIntent.ACCOUNT_RULE:
                if (
                    resolved_plan.account_rule_topic
                    == AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW
                ):
                    response = build_pension_account_overview_response()
                elif resolved_plan.account_rule_topic is not None:
                    response = build_deferred_pension_topic_response(
                        resolved_plan.account_rule_topic
                    )
                else:
                    response = self._account_rule_response(request, resolved_plan)
            else:
                response = self._blocked_response(BlockedReason.UNSUPPORTED)
        response = self._with_context(
            self._attach_visualizations(response), original_request, resolved_plan
        )
        return response.model_copy(
            update={"suggested_follow_ups": build_suggested_follow_ups(response)}
        )

    def _etf_theme_response(
        self,
        request: ChatRequest,
        plan: QueryPlan,
    ) -> ChatResponse:
        if self._theme_repository is None or plan.theme_id is None:
            return ChatResponse(
                intent=ChatIntent.ETF_THEME,
                answer="ETF 테마 카탈로그를 불러오지 못했습니다.",
                data_mode="unavailable",
                limitations=["테마 카탈로그 연결 상태를 확인해야 합니다."],
            )
        theme = self._theme_repository.get(plan.theme_id)
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
                locator=self._theme_repository.catalog_path.as_posix(),
                publisher="연금 코파일럿",
                as_of=self._theme_repository.catalog.as_of_date,
                data_boundary=DataBoundary.ENGINE,
            )
        ]
        sections = [
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title=f"{theme.name} 테마",
                content=theme.plain_summary,
                evidence_ids=[catalog_source_id],
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.CALLOUT,
                        title="분류상 정의",
                        text=theme.definition,
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="무엇을 담나",
                        items=list(theme.exposure_segments),
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="움직임을 살필 요인",
                        items=list(theme.performance_drivers),
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="살펴볼 점",
                        items=list(theme.benefits),
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        title="주요 위험",
                        items=list(theme.risks),
                    ),
                    AnswerBlock(
                        kind=AnswerBlockKind.CALLOUT,
                        title="한 줄 비유",
                        text=theme.one_line_analogy,
                    ),
                ],
            )
        ]
        limitations = [
            "테마 설명은 사용자가 제공한 조사 내용을 서비스 분류체계로 "
            "정리한 것으로 공식 문서 검증 전 초안입니다.",
            "테마 편입은 상품의 미래 성과를 뜻하지 않으며 "
            "수익률을 예측하지 않습니다.",
        ]
        if not plan.requests_theme_candidates:
            return ChatResponse(
                intent=ChatIntent.ETF_THEME,
                answer=f"{theme.name} 테마의 구조와 판단할 위험을 정리했습니다.",
                data_mode="theme_overview",
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
        if self._portfolio_universe_loader is None:
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
        holding_sections: list[AnswerSection] = []
        holding_source_ids: set[str] = set()
        successful_accounts = 0
        for account_type in account_types:
            try:
                universe = self._portfolio_universe_loader(account_type)
            except (FileNotFoundError, ValueError):
                limitations.append(
                    f"{_ACCOUNT_TYPE_LABELS[account_type]} ETF 적격 유니버스를 "
                    "불러오지 못했습니다."
                )
                continue
            evaluation = select_theme_etf_candidates(
                catalog=self._theme_repository.catalog,
                theme=theme,
                products=universe.products,
                kis_products_by_code=(
                    self._theme_repository.kis_products_by_code
                ),
                component_snapshot_date=(
                    self._theme_repository.component_snapshot_date
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
            for candidate in evaluation.candidates:
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
                candidate_rows.append(
                    [
                        _ACCOUNT_TYPE_LABELS[account_type],
                        candidate.isu_name,
                        candidate.isu_code,
                        fee_text,
                    ]
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
                    title="성향·계좌 범위 안의 비교 후보",
                    content=(
                        "계좌 적격성, 투자성향 슬리브와 비수익률 품질지표를 "
                        "통과한 교육용 비교 후보입니다."
                    ),
                    evidence_ids=master_ids,
                    blocks=[
                        AnswerBlock(
                            kind=AnswerBlockKind.TABLE,
                            headers=["계좌", "ETF", "종목코드", "총보수"],
                            rows=candidate_rows,
                        )
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

    @staticmethod
    def _attach_visualizations(response: ChatResponse) -> ChatResponse:
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
                                label=stress.scenario_code,
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
                    f"계산에 필요한 {missing_text}이(가) 빠져 있어요. "
                    "해당 값만 질문에 적거나 연금세액 입력 화면에 "
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
                locator="engine://pension_tax_guidance/2026-07-20.1",
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
            f"{cls._krw(result.total_eligible_contribution_krw)}이에요. "
            "입력한 납입액은 연금저축 "
            f"{cls._krw(result.pension_savings_contribution_krw)}, IRP "
            f"{cls._krw(result.irp_contribution_krw)}, DC 근로자 추가납입 "
            f"{cls._krw(result.dc_employee_additional_contribution_krw)}입니다."
        )
        if result.isa_maturity_transfer_krw > 0:
            base += (
                " ISA 만기자금 전환액은 "
                f"{cls._krw(result.isa_maturity_transfer_krw)}, 추가 한도는 "
                f"{cls._krw(result.isa_additional_credit_limit_krw)}입니다."
            )
        if result.total_excluded_contribution_krw > 0:
            base += (
                " 회사 DC 부담금·퇴직급여 이전액·연금계좌 간 이전액 중 "
                f"{cls._krw(result.total_excluded_contribution_krw)}은 "
                "세액공제 계산에서 제외했습니다."
            )
        if result.rate_determined:
            scenario = result.rate_scenarios[0]
            return (
                f"{base} 소득세법상 세액공제율 "
                f"{_decimal_text(scenario.income_tax_rate_percent)}% 기준 법정 "
                f"세액공제액은 {cls._krw(scenario.income_tax_credit_krw)}, "
                "개인지방소득세 효과를 포함한 예상 절세효과는 "
                f"{cls._krw(scenario.estimated_total_tax_reduction_effect_krw)}입니다. "
                "실제 환급액은 결정세액 등에 따라 달라질 수 있습니다."
            )
        ordered = sorted(
            result.rate_scenarios,
            key=lambda item: item.income_tax_credit_krw,
        )
        return (
            f"{base} 소득정보가 없어 법정 세액공제액은 "
            f"{cls._krw(ordered[0].income_tax_credit_krw)}부터 "
            f"{cls._krw(ordered[-1].income_tax_credit_krw)}까지, "
            "개인지방소득세 효과를 포함한 예상 절세효과는 "
            f"{cls._krw(ordered[0].estimated_total_tax_reduction_effect_krw)}부터 "
            f"{cls._krw(ordered[-1].estimated_total_tax_reduction_effect_krw)}"
            "까지입니다. "
            "실제 환급액은 결정세액 등에 따라 달라질 수 있습니다."
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
                label="DC 근로자 본인 추가납입액",
                value=result.dc_employee_additional_contribution_krw,
                unit="KRW",
                evidence_id="user:pension_tax",
                basis="사용자 입력",
            ),
            NumericEvidence(
                label="세액공제 제외 납입·이전액",
                value=result.total_excluded_contribution_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="회사 DC 부담금·퇴직급여 이전액·연금계좌 간 이전액 제외",
            ),
            NumericEvidence(
                label="합산 세액공제 대상 납입액",
                value=result.total_eligible_contribution_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="2026년 일반 합산 900만원 및 적격 ISA 추가 한도",
            ),
            NumericEvidence(
                label="ISA 전환 추가 세액공제 한도",
                value=result.isa_additional_credit_limit_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="적격 ISA 만기자금 전환액의 10%, 누적 최대 300만원",
            ),
        ]
        for scenario in result.rate_scenarios:
            numeric.extend(
                [
                    NumericEvidence(
                        label=f"{scenario.label} 법정 세액공제율",
                        value=scenario.income_tax_rate_percent,
                        unit="%",
                        evidence_id="rule:pension_tax:credit",
                        basis="소득세법상 세액공제율",
                    ),
                    NumericEvidence(
                        label=f"{scenario.label} 표시율",
                        value=scenario.local_inclusive_display_rate_percent,
                        unit="%",
                        evidence_id="rule:pension_tax:credit",
                        basis="소득세율과 개인지방소득세 효과 포함",
                    ),
                    NumericEvidence(
                        label=f"{scenario.label} 법정 세액공제액",
                        value=scenario.income_tax_credit_krw,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="소득세법상 세액공제율 적용",
                    ),
                    NumericEvidence(
                        label=f"{scenario.label} 지방세 포함 예상 절세효과",
                        value=scenario.estimated_total_tax_reduction_effect_krw,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="법정 세액공제액과 개인지방소득세 효과 합산",
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
                    "세금 부과 방식이 다를 수 있어 예상세액을 계산하지 않았어요. "
                    "먼저 법정 요건과 적용 방식을 확인해야 해요."
                )
            return (
                f"두 계좌 잔액 합계는 {cls._krw(result.total_balance_krw)}이에요. "
                "인출 사유를 먼저 확인해야 해서 기타소득 예상액은 계산하지 않았어요."
            )
        assert result.assumed_other_income_tax_base_krw is not None
        assert result.other_income_rate_percent is not None
        assert result.estimated_max_other_income_withholding_krw is not None
        return (
            f"두 계좌 잔액 합계 {cls._krw(result.total_balance_krw)}에서 "
            "당해연도 납입 과세제외액 "
            f"{cls._krw(result.total_current_year_contribution_excluded_krw)} 등을 "
            "반영한 16.5% 간이 과세대상액은 "
            f"{cls._krw(result.assumed_other_income_tax_base_krw)}이에요. "
            "지방소득세를 포함한 기타소득 원천징수 최대 간이 추정액은 "
            f"{cls._krw(result.estimated_max_other_income_withholding_krw)}이에요."
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
                    "개인 식별정보나 인증정보가 포함된 질문은 처리하지 않아요. "
                    "해당 값을 지운 뒤 제도나 운용 원리만 질문해 주세요."
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
                    "미래 수익률 예측은 제공하지 않아요. 목표가나 수익 보장도 "
                    "안내하지 않아요. 포트폴리오 입력이 있으면 규칙 엔진이 계산한 "
                    "장기 계획가정과 과거 위험지표를 설명해 드려요."
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
                    "상품 선택과 주문은 이용자가 직접 해야 해요. 금융회사 공식 "
                    "채널을 이용해 주세요. 챗봇은 판단 기준과 근거만 설명해 드려요."
                ),
                data_mode="blocked",
                limitations=["주문·자동운용은 지원하지 않습니다."],
            )
        if reason == BlockedReason.PRODUCT_LEVEL_UNAVAILABLE:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "현재 데이터는 연금저축 회사와 퇴직연금 사업자 단위로 모여 "
                    "있어요. 개별 상품 데이터가 아니어서 상품별 비교·추천은 "
                    "제공하지 않아요."
                ),
                data_mode="unavailable",
                limitations=["검증된 개별 상품 식별자와 적격성 데이터가 필요합니다."],
            )
        if reason == BlockedReason.ACCOUNT_SELECTION_REQUIRED:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "공시 수치는 계좌 제도별 항목이 달라 한 번에 섞어 비교하지 "
                    "않아요. DC형, IRP, 연금저축 중 하나를 지정해 주세요."
                ),
                data_mode="blocked",
                limitations=["계좌별 공시 계약을 분리해 조회합니다."],
            )
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "연금계좌 규칙, 가상계좌 진단, 과거 공시와 뉴스 근거를 안내할 수 "
                "있어요. 질문에 계좌 유형이나 진단할 가상 시나리오를 적어 주세요."
            ),
            data_mode="safe_fallback",
            limitations=["범용 투자·세무·법률 상담은 지원하지 않습니다."],
        )

    def _account_rule_response(
        self, request: ChatRequest, plan: QueryPlan
    ) -> ChatResponse:
        topic, suffix, title, heading, required = _knowledge_topic(
            request.message, plan
        )
        query = " ".join(
            item
            for item in (
                request.message,
                suffix,
                *(_ACCOUNT_TYPE_LABELS[item] for item in plan.account_types),
            )
            if item
        )
        matches = self._knowledge.search_knowledge(query, limit=8)
        if not matches:
            return ChatResponse(
                intent=ChatIntent.ACCOUNT_RULE,
                answer="검증된 근거 문서를 찾지 못해 답변을 만들지 않았어요.",
                data_mode="verified_knowledge",
                limitations=["질문을 계좌 유형과 함께 더 구체적으로 입력해 주세요."],
            )
        match = _select_knowledge_match(
            matches,
            title=title,
            heading=heading,
            required=required,
        )
        if match is None:
            return ChatResponse(
                intent=ChatIntent.ACCOUNT_RULE,
                answer=(
                    "검증 근거의 안전성과 질문 주제 적합성을 확인하지 못해 "
                    "답변을 만들지 않았어요."
                ),
                data_mode="verified_knowledge",
                limitations=["공식 근거를 재검토한 뒤 다시 안내해야 합니다."],
            )
        sources = _knowledge_sources([match])
        if (
            AccountType.PENSION_SAVINGS in plan.account_types
            and self._is_eligibility_question(request.message)
        ):
            return ChatResponse(
                intent=ChatIntent.ACCOUNT_RULE,
                answer=(
                    "연금저축의 상품별 적격성은 공식 상품 식별자와 금융회사 "
                    "편입 목록으로 확인해야 해요. 현재 챗봇에는 그 데이터가 "
                    "없어서 개별 상품의 편입 가능 여부를 확정하지 않아요."
                ),
                data_mode="verified_knowledge",
                sources=sources,
                limitations=[
                    "상품별 적격성은 공식 상품 데이터로 별도 확인해야 합니다."
                ],
            )
        excerpt = _plain_knowledge_excerpt(match.content, heading=heading)
        if topic == "tax_rate":
            excerpt = "\n".join(
                line
                for line in excerpt.splitlines()
                if not ("최대" in line and "환급" in line)
            )
        if not excerpt:
            return ChatResponse(
                intent=ChatIntent.ACCOUNT_RULE,
                answer="검증된 근거에서 답변에 쓸 대목을 찾지 못했어요.",
                data_mode="verified_knowledge",
                sources=sources,
                limitations=["질문을 계좌 유형과 함께 더 구체적으로 입력해 주세요."],
            )
        answer = (
            "공식 근거에서 확인한 내용이에요.\n\n"
            f"{excerpt}\n\n"
            "개인 상황에 적용하기 전에는 아래 출처와 기준일을 함께 봐 주세요."
        )
        risk_question = topic == "risk_cap"
        risk_label = (
            "DC형·IRP 위험자산 한도(연금저축 동일 한도 없음)"
            if "DC형·IRP에 적용" in excerpt
            and "연금저축펀드에는 동일한 한도가 없다" in excerpt
            else f"{match.title} 위험자산 한도"
        )
        numeric = [
            NumericEvidence(
                label=(
                    risk_label
                    if risk_question and unit == "%"
                    else f"{match.title} 답변 수치 {index}"
                ),
                value=value,
                unit=unit,
                evidence_id=sources[0].evidence_id,
                basis="검증된 지식 문서에서 직접 발췌",
            )
            for index, (value, unit) in enumerate(
                sorted(extract_numeric_claims(answer)), start=1
            )
        ]

        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer=answer,
            data_mode="verified_knowledge",
            sections=[
                AnswerSection(
                    kind=SectionKind.FACT,
                    title="근거에서 확인한 내용",
                    content=excerpt,
                    evidence_ids=[_knowledge_evidence_id(match)],
                )
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

    @staticmethod
    def _completed_survey_required() -> ChatResponse:
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

    @staticmethod
    def _risk_profile_selection_guide() -> ChatResponse:
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

    @staticmethod
    def _retirement_age_selection_guide() -> ChatResponse:
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

    @staticmethod
    def _age_style_portfolio_guide() -> ChatResponse:
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
                f"설문 결과는 {assessed_label}이에요. {requested_label} ETF "
                "포트폴리오는 설문 성향보다 위험해서 제안하지 않아요. "
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
                    "연결되지 않았어요."
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
                history_as_of=repository.latest_history_as_of,
                score_cache=repository.score_cache,
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

    def _macro_evidence_response(self, request: ChatRequest) -> ChatResponse:
        if self._macro_evidence is None:
            return self._macro_evidence_unavailable()
        try:
            snapshot = self._macro_evidence.latest()
        except MacroEvidenceUnavailable:
            return self._macro_evidence_unavailable()

        metrics = self._select_macro_metrics(request.message, snapshot)
        if not metrics:
            return self._macro_evidence_unavailable()
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

    @staticmethod
    def _select_macro_metrics(
        message: str, snapshot: MacroEvidenceSnapshot
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

    @staticmethod
    def _macro_evidence_unavailable() -> ChatResponse:
        return ChatResponse(
            intent=ChatIntent.MACRO_EVIDENCE,
            answer="공식 거시지표 보고서를 불러오지 못해 수치를 안내하지 않았어요.",
            data_mode="unavailable",
            limitations=["보고서 수집 상태와 경로를 확인한 뒤 다시 조회해 주세요."],
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
        has_limit_breach = False
        risk_term_explained = False
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
            account_subject = {
                AccountType.DC.value: "DC형은",
                AccountType.IRP.value: "IRP는",
                AccountType.PENSION_SAVINGS.value: "연금저축펀드는",
            }[account_code]
            if result.limit_percent is None:
                account_lines.append(
                    f"{account_subject} 비율 제한이 없어서 상품별로 담을 수 "
                    "있는지만 확인하면 돼요"
                )
            else:
                ratio = _decimal_text(result.general_risky_ratio_percent)
                limit = _decimal_text(result.limit_percent)
                limit_status = (
                    f"한도({limit}%) 안이에요"
                    if result.within_limit
                    else f"한도({limit}%)를 넘었어요"
                )
                risk_term = (
                    "위험자산(주식처럼 가격이 오르내릴 수 있는 자산)"
                    if not risk_term_explained
                    else "위험자산"
                )
                account_lines.append(
                    f"{account_subject} {risk_term}이 {ratio}%로 "
                    f"{limit_status}"
                )
                risk_term_explained = True
                has_limit_breach = has_limit_breach or not result.within_limit
            numeric.append(
                NumericEvidence(
                    label=f"{account_name} 일반 위험자산 비중",
                    value=result.general_risky_ratio_percent,
                    unit="%",
                    evidence_id="engine:scenario",
                    basis="규칙 엔진 계산",
                )
            )
            if result.limit_percent is not None:
                numeric.append(
                    NumericEvidence(
                        label=f"{account_name} 일반 위험자산 한도",
                        value=result.limit_percent,
                        unit="%",
                        evidence_id="engine:scenario",
                        basis="규칙 엔진에 적용된 계좌 한도",
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
        if duplicate_text and "현금성 자산" in duplicate_text:
            duplicate_text = duplicate_text.replace(
                "현금성 자산",
                "현금성 자산(예금·CMA처럼 바로 찾을 수 있는 돈)",
            )
        account_summary = ". ".join(account_lines)
        duplicate_summary = (
            f"여러 계좌에 {duplicate_text}이 겹쳐 있어요."
            if duplicate_text
            else "계좌 사이에 겹친 자산군은 없어요."
        )
        holdings_summary, holding_evidence = _scenario_holdings_summary(scenario)
        numeric.extend(holding_evidence)
        rebalancing_summary = _scenario_rebalancing_summary(
            evaluation.duplicated_asset_classes
        )
        conclusion = (
            "한도를 넘은 계좌가 있어요. "
            if has_limit_breach
            else "점검 결과 큰 문제는 없어요. "
        )
        answer = conclusion + f"{account_summary}. {duplicate_summary}"
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
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="보유 항목과 비중",
                    content=holdings_summary,
                    evidence_ids=["mock:scenario"],
                ),
                AnswerSection(
                    kind=SectionKind.LIMITATION,
                    title="리밸런싱 점검",
                    content=rebalancing_summary,
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
        names = ", ".join(item.name for item in self._scenarios.list())
        limitations = [limitation] if limitation else []
        limitations.append("홈 또는 왼쪽 메뉴에서 진단할 가상 고객을 선택해 주세요.")
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=(
                "먼저 진단할 가상 고객을 선택해 주세요. "
                f"현재 선택할 수 있는 고객 유형은 {names}예요."
            ),
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

    @staticmethod
    def _scenario_code(message: str) -> str | None:
        return next(
            (code for keyword, code in SCENARIO_KEYWORDS.items() if keyword in message),
            None,
        )
