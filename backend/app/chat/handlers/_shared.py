"""Shared contracts and deterministic helpers for chat intent handlers."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from ...engine import (
    AccountType,
    EducationalPortfolioEvaluation,
    EducationalRiskProfile,
    ScenarioPortfolioInput,
)
from ...retrieval.knowledge_policy import (
    contains_sensitive_personal_data,
    contains_unsafe_rag_content,
)
from ...retrieval.repository import KnowledgeMatch, NewsMatch
from ..disclosures import ProviderDisclosure
from ..live_news import (
    LiveMarketNewsSnapshot,
)
from ..models import (
    ChatIntent,
    ChatRequest,
    DataBoundary,
    NumericEvidence,
    SourceEvidence,
)
from ..narrator import contains_unsafe_financial_claim
from ..query_planner import (
    QueryPlan,
)

_MACRO_ANALOG_OUTCOME_TERMS = re.compile(
    r"유사\s*국면|과거\s*국면|최대\s*낙폭|"
    r"(?:3|6|12)\s*(?:·|/|,|개월)",
    re.I,
)


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

    def summarized_news_by_canonical_urls(
        self, canonical_urls: tuple[str, ...]
    ) -> dict[str, NewsMatch]: ...


class LiveNewsSearch(Protocol):
    def fetch_market_news(
        self,
        *,
        region: str | None,
        limit: int,
    ) -> LiveMarketNewsSnapshot: ...


class PortfolioUniverse(Protocol):
    products: list[dict[str, Any]]
    histories: dict[str, dict[date, Decimal]]
    history_sources: dict[str, str]
    as_of: date


class PortfolioUniverseLoader(Protocol):
    def __call__(self, account_type: AccountType) -> PortfolioUniverse: ...


class ThemeProductUniverse(Protocol):
    products: list[dict[str, Any]]
    as_of: date


class ThemeProductUniverseLoader(Protocol):
    def __call__(
        self,
        isu_codes: tuple[str, ...] | None,
    ) -> ThemeProductUniverse: ...


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


def is_selected_scenario_diagnosis_request(
    request: ChatRequest,
    plan: QueryPlan,
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


def _krw_text(value: Decimal) -> str:
    return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}원"


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
_RISK_PROFILE_COMPARISON = re.compile(
    r"각각|비교|차이|다섯\s*(?:가지|개)|5\s*(?:가지|개)"
)
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
_STRATEGY_EXPLANATIONS = {
    "capital_preservation_core": (
        "높은 수익을 추구하기보다 연금자산의 큰 손실을 줄이고 안정적으로 "
        "유지하는 데 목적이 있어요.",
        "학교 가는 길에 비가 올까 봐 우산, 우비, 여벌 옷까지 챙기는 "
        "사람과 비슷해요. 많이 빨리 가는 것보다 비를 맞지 않고 안전하게 "
        "가는 것이 더 중요해요.",
    ),
    "defensive_diversified_core": (
        "방어자산을 중심에 두되 장기 성장과 물가상승에 대응하기 위해 "
        "주식과 실물자산을 조금 더 적극적으로 편입해요.",
        "안정형이 우산과 우비를 모두 챙기는 사람이라면, 안정추구형은 "
        "우산을 챙기되 날씨가 좋으면 조금 더 멀리 걸어가 보는 사람에 "
        "가까워요.",
    ),
    "balanced_core_satellite": (
        "광범위한 주식 ETF를 장기 성장의 코어로 두고 특정 테마 ETF는 "
        "5% 이내의 위성자산으로 제한하는 구조예요.",
        "큰 기본 식사에 작은 반찬을 더하는 전략이에요. 코어는 주식시장의 "
        "기본 뼈대이고, 위성은 조금만 담는 특별 반찬이에요.",
    ),
    "growth_core_satellite": (
        "장기 성장자산의 비중을 확대하면서도 채권과 현금을 완전히 없애지 "
        "않는 구조예요.",
        "기본 주식 투자를 크게 하고 작은 도전도 조금 늘리는 전략이에요. "
        "위험중립형보다 성장 가능성을 더 중요하게 생각하는 대신, 시장이 "
        "떨어질 때 손실도 더 클 수 있어요.",
    ),
    "barbell_growth_tactical": (
        "주식과 전술자산의 성장축을 크게 두면서 반대편에 최소한의 채권과 "
        "현금 방어축을 별도로 유지해요.",
        "바벨은 양쪽 끝에 무게가 달린 긴 막대예요. 중간 성격의 자산을 "
        "많이 두기보다 성장 쪽과 안전 쪽의 역할을 분명히 나눠 두는 "
        "방식이에요.",
    ),
}
_SLEEVE_LABELS = {
    "core_equity": "주식",
    "real_assets": "실물자산",
    "tactical": "전술자산",
    "fixed_income": "채권",
    "cash": "현금",
}
_STRESS_SCENARIO_LABELS = {
    "equity_drawdown": "주식시장 급락",
    "rate_inflation_shock": "금리·물가 충격",
    "stagflation": "스태그플레이션",
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


def _requests_risk_profile_portfolio_guide(message: str) -> bool:
    mentioned_profiles = {
        profile
        for pattern, profile in _RISK_PROFILE_PATTERNS
        if pattern.search(message)
    }
    compares_named_profiles = (
        len(mentioned_profiles) >= 2
        and _RISK_PROFILE_COMPARISON.search(message) is not None
    )
    compares_all_styles = (
        _STYLE_COMPARISON.search(message) is not None
        and _RISK_PROFILE_PORTFOLIO_REQUEST.search(message) is not None
    )
    return compares_named_profiles or compares_all_styles


def _mentioned_retirement_start_age(message: str) -> int | None:
    match = _RETIREMENT_START_AGE.search(message)
    if match is None:
        return None
    return int(match.group(1) or match.group(2))


def _strategy_summary(evaluation: EducationalPortfolioEvaluation) -> str:
    profile = _RISK_PROFILE_LABELS[evaluation.evaluated_input.risk_profile.value]
    strategy = _STRATEGY_LABELS[evaluation.strategy_label]
    explanation, analogy = _STRATEGY_EXPLANATIONS[evaluation.strategy_label]
    return (
        f"{profile}의 {strategy}이에요. {explanation}\n\n"
        f"쉽게 말하면: {analogy}"
    )


def _target_portfolio_rows(
    evaluation: EducationalPortfolioEvaluation,
) -> list[list[str]]:
    candidates_by_sleeve: dict[str, list[str]] = {}
    for candidate in evaluation.candidates:
        candidates_by_sleeve.setdefault(candidate.sleeve, []).append(
            candidate.isu_name
        )
    rows = []
    for target in evaluation.target_sleeves:
        label = _SLEEVE_LABELS[target.sleeve]
        percent = _decimal_text(_one_decimal(target.target_percent))
        names = " · ".join(candidates_by_sleeve.get(target.sleeve, []))
        rows.append([label, f"{percent}%", names])
    return rows


def _rebalancing_items(evaluation: EducationalPortfolioEvaluation) -> list[str]:
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
    return parts


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
