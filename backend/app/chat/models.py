import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..engine import (
    AccountType,
    EducationalPortfolioEvaluation,
    EducationalPortfolioInput,
    EducationalRiskProfile,
    MacroRegimeEtfOutcomeEvaluation,
    PensionTaxScenarioInput,
    PensionTaxToolResult,
    PortfolioInput,
    RiskCapEvaluation,
    ScenarioEvaluation,
)

_NUMBER_WITH_UNIT = re.compile(
    r"(?<![0-9A-Za-z_])(?P<sign>[+\-−])?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>백\s*만\s*원|천\s*만\s*원|억\s*원|만\s*원|천\s*원|"
    r"원|KRW|퍼센트|프로|%)"
    r"(?![0-9A-Za-z_])",
    re.I,
)
_LEGAL_FRACTION = re.compile(
    r"(?P<denominator>\d[\d,]*)\s*분의\s*(?P<numerator>\d[\d,]*(?:\.\d+)?)"
)
_CURRENCY_MULTIPLIERS = {
    "원": Decimal("1"),
    "천원": Decimal("1000"),
    "만원": Decimal("10000"),
    "천만원": Decimal("10000000"),
    "백만원": Decimal("1000000"),
    "억원": Decimal("100000000"),
    "krw": Decimal("1"),
}
_UNIT_ALIASES = {
    "%": "%",
    "퍼센트": "%",
    "프로": "%",
}


def _normalize_numeric_value(
    value: Decimal, unit: str
) -> tuple[Decimal, str]:
    compact_unit = re.sub(r"\s+", "", unit).casefold()
    multiplier = _CURRENCY_MULTIPLIERS.get(compact_unit)
    if multiplier is not None:
        return value * multiplier, "KRW"
    return value, _UNIT_ALIASES.get(compact_unit, compact_unit)


def extract_numeric_claims(text: str) -> set[tuple[Decimal, str]]:
    """Return normalized percentage and KRW claims from generated text."""

    claims: set[tuple[Decimal, str]] = set()
    # 법령 원문의 "100분의 15"는 재서술문의 "15%"와 같은 주장이다.
    # narrator의 숫자 가드와 같은 규칙을 써야 두 층이 어긋나지 않는다.
    for match in _LEGAL_FRACTION.finditer(text):
        denominator = Decimal(match.group("denominator").replace(",", ""))
        numerator = Decimal(match.group("numerator").replace(",", ""))
        if denominator:
            claims.add((numerator / denominator * 100, "%"))
    for match in _NUMBER_WITH_UNIT.finditer(_LEGAL_FRACTION.sub(" ", text)):
        raw_number = match.group("number").replace(",", "")
        raw_sign = match.group("sign")
        sign = "-" if raw_sign in {"-", "−"} else ""
        try:
            value = Decimal(sign + raw_number)
        except InvalidOperation:
            continue
        claims.add(_normalize_numeric_value(value, match.group("unit")))
    return claims


def numeric_evidence_claim(item: "NumericEvidence") -> tuple[Decimal, str]:
    return _normalize_numeric_value(item.value, item.unit)


class ChatIntent(StrEnum):
    ACCOUNT_RULE = "account_rule"
    MOCK_PORTFOLIO = "mock_portfolio"
    PROVIDER_DISCLOSURE = "provider_disclosure"
    NEWS = "news"
    PENSION_TAX = "pension_tax"
    EDUCATIONAL_PORTFOLIO = "educational_portfolio"
    ETF_THEME = "etf_theme"
    ETF_DISTRIBUTION = "etf_distribution"
    MACRO_EVIDENCE = "macro_evidence"
    GLOSSARY = "glossary"
    OUT_OF_SCOPE = "out_of_scope"


class DataBoundary(StrEnum):
    VERIFIED_KNOWLEDGE = "verified_knowledge"
    OFFICIAL_DISCLOSURE = "official_disclosure"
    OFFICIAL_STATISTICS = "official_statistics"
    NEWS_METADATA = "news_metadata"
    NEWS_SUMMARY = "news_summary"
    MOCK = "mock"
    ENGINE = "engine"
    USER_INPUT = "user_input"
    UNAVAILABLE = "unavailable"


class SectionKind(StrEnum):
    FACT = "fact"
    EXTERNAL_OPINION = "external_opinion"
    SERVICE_EXPLANATION = "service_explanation"
    LIMITATION = "limitation"


class AnswerBlockKind(StrEnum):
    CALLOUT = "callout"
    PARAGRAPH = "paragraph"
    BULLETS = "bullets"
    TABLE = "table"
    FORMULA = "formula"


class VisualizationKind(StrEnum):
    ASSET_ALLOCATION = "asset_allocation"
    RISK_CAP = "risk_cap"
    TAX_SUMMARY = "tax_summary"
    SLEEVE_ALLOCATION = "sleeve_allocation"
    STRESS_SCENARIOS = "stress_scenarios"
    DISCLOSURE_COMPARISON = "disclosure_comparison"
    ACCUMULATION_PROJECTION = "accumulation_projection"


class VisualizationDatumRole(StrEnum):
    SEGMENT = "segment"
    CURRENT = "current"
    LIMIT = "limit"
    VALUE = "value"


class CompletedSurveyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType
    account_types: list[AccountType] = Field(default_factory=list, max_length=3)
    current_age: int = Field(ge=20, le=54)
    retirement_start_age: int = Field(ge=55, le=60)
    risk_profile: EducationalRiskProfile
    loss_tolerance_percent: Decimal = Field(
        ge=Decimal("1"),
        le=Decimal("50"),
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def retirement_must_follow_current_age(self) -> "CompletedSurveyProfile":
        if self.retirement_start_age <= self.current_age:
            raise ValueError("retirement_start_age must be greater than current_age")
        if len(set(self.account_types)) != len(self.account_types):
            raise ValueError("account_types must not contain duplicates")
        if self.account_types and self.account_type not in self.account_types:
            raise ValueError("account_type must be included in account_types")
        return self

    def portfolio_account_types(self) -> tuple[AccountType, ...]:
        return tuple(self.account_types or [self.account_type])


class MarketRegion(StrEnum):
    ALL = "all"
    KR = "kr"
    US = "us"


class NewsConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_item_ids: list[str] = Field(min_length=1, max_length=3)
    focus_news_item_id: str | None = None
    market_region: MarketRegion = MarketRegion.ALL
    shown_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_news_item_ids(self) -> "NewsConversationContext":
        normalized_ids = [item_id.strip() for item_id in self.news_item_ids]
        if any(not item_id for item_id in normalized_ids):
            raise ValueError("news_item_ids must not contain blanks")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("news_item_ids must not contain duplicates")
        if (
            self.focus_news_item_id is not None
            and self.focus_news_item_id not in normalized_ids
        ):
            raise ValueError("focus_news_item_id must be included in news_item_ids")
        self.news_item_ids = normalized_ids
        return self


class EtfThemeConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str = Field(min_length=1)
    candidate_isu_codes: list[str] = Field(min_length=1, max_length=3)
    candidate_names: list[str] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_candidate_isu_codes(self) -> "EtfThemeConversationContext":
        codes = [code.strip() for code in self.candidate_isu_codes]
        if any(not code for code in codes):
            raise ValueError("candidate_isu_codes must not contain blanks")
        if len(set(codes)) != len(codes):
            raise ValueError("candidate_isu_codes must not contain duplicates")
        if len(self.candidate_names) != len(codes):
            raise ValueError("candidate_names must match candidate_isu_codes")
        if any(not name.strip() for name in self.candidate_names):
            raise ValueError("candidate_names must not contain blanks")
        self.candidate_isu_codes = codes
        return self


class ReferentItem(BaseModel):
    """One ordered item from the immediately preceding response."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    ref: str = Field(min_length=1)


class ReferentList(BaseModel):
    """Small, deterministic follow-up target list; it is replaced every turn."""

    model_config = ConfigDict(extra="forbid")

    intent: ChatIntent
    topic: str | None = Field(default=None, min_length=1)
    items: list[ReferentItem] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validate_items(self) -> "ReferentList":
        normalized_items = [
            ReferentItem(label=item.label.strip(), ref=item.ref.strip())
            for item in self.items
        ]
        if any(not item.label or not item.ref for item in normalized_items):
            raise ValueError("referent items must not contain blanks")
        if len({item.ref for item in normalized_items}) != len(normalized_items):
            raise ValueError("referent items must not contain duplicate refs")
        self.items = normalized_items
        return self


class ConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType | None = None
    scenario_code: str | None = Field(default=None, min_length=1)
    last_intent: ChatIntent | None = None
    survey_profile: CompletedSurveyProfile | None = None
    selected_risk_profile: EducationalRiskProfile | None = None
    news: NewsConversationContext | None = None
    etf_theme: EtfThemeConversationContext | None = None
    referents: ReferentList | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=2, max_length=1000)
    scenario_code: str | None = Field(default=None, min_length=1)
    portfolio: PortfolioInput | None = None
    educational_portfolio: EducationalPortfolioInput | None = None
    survey_profile: CompletedSurveyProfile | None = None
    pension_tax: PensionTaxScenarioInput | None = None
    max_results: int = Field(default=3, ge=1, le=5)
    conversation_context: ConversationContext | None = None

    @model_validator(mode="after")
    def allow_one_structured_calculation(self) -> "ChatRequest":
        structured = (
            self.portfolio,
            self.educational_portfolio,
            self.pension_tax,
        )
        if sum(item is not None for item in structured) > 1:
            raise ValueError("only one structured calculation input is allowed")
        return self


class SourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    label: str
    locator: str
    data_boundary: DataBoundary
    publisher: str | None = None
    as_of: date | datetime | None = None


class NumericEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: Decimal
    unit: str
    evidence_id: str
    basis: str


class AnswerBlock(BaseModel):
    """Optional rich content for answers that need more than one paragraph."""

    model_config = ConfigDict(extra="forbid")

    kind: AnswerBlockKind
    title: str | None = None
    text: str | None = None
    items: list[str] = Field(default_factory=list)
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_block_shape(self) -> "AnswerBlock":
        if self.kind in {
            AnswerBlockKind.CALLOUT,
            AnswerBlockKind.PARAGRAPH,
            AnswerBlockKind.FORMULA,
        } and not (self.text and self.text.strip()):
            raise ValueError(f"{self.kind.value} block requires text")
        if self.kind == AnswerBlockKind.BULLETS and not self.items:
            raise ValueError("bullets block requires at least one item")
        if self.kind == AnswerBlockKind.TABLE:
            if not self.headers or not self.rows:
                raise ValueError("table block requires headers and rows")
            if any(len(row) != len(self.headers) for row in self.rows):
                raise ValueError("table rows must match the header width")
        return self

    def plain_text(self) -> str:
        parts = [self.title or "", self.text or "", *self.items, *self.headers]
        parts.extend(cell for row in self.rows for cell in row)
        return "\n".join(part for part in parts if part)


class AnswerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SectionKind
    title: str
    content: str
    evidence_ids: list[str] = Field(default_factory=list)
    blocks: list[AnswerBlock] = Field(default_factory=list)

    def plain_text(self) -> str:
        return "\n".join(
            part
            for part in (
                self.content,
                *(block.plain_text() for block in self.blocks),
            )
            if part
        )


class ChatNewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    title: str
    description: str | None = None
    summary_lines: list[str] = Field(default_factory=list)
    original_url: str
    published_at: datetime | None = None

    @model_validator(mode="after")
    def validate_summary_lines(self) -> "ChatNewsItem":
        if len(self.summary_lines) not in {0, 3}:
            raise ValueError("news summary must contain exactly three lines")
        if any(not line.strip() for line in self.summary_lines):
            raise ValueError("news summary lines must not be blank")
        return self


class SuggestedFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    follow_up_id: str
    label: str
    message: str


class VisualizationDatum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: Decimal
    unit: str
    role: VisualizationDatumRole


class VisualizationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    label: str
    value: Decimal


class VisualizationSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    unit: str
    points: list[VisualizationPoint] = Field(default_factory=list)


class ChatVisualization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: VisualizationKind
    title: str
    description: str
    data_boundary: DataBoundary
    evidence_ids: list[str] = Field(default_factory=list)
    items: list[VisualizationDatum] = Field(min_length=1)
    series: list[VisualizationSeries] = Field(default_factory=list)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: ChatIntent
    answer: str
    data_mode: str
    narration_mode: str = "deterministic"
    model_name: str | None = None
    # Claude 내레이터의 thinking 요약(검증 답변을 어떻게 풀어썼는지의 근거 설명).
    # 새 숫자가 감지되면 본문과 달리 이 필드만 생략한다.
    narration_reasoning: str | None = None
    salutation: str | None = Field(default=None, max_length=60)
    sections: list[AnswerSection] = Field(default_factory=list)
    news_items: list[ChatNewsItem] = Field(default_factory=list)
    visualizations: list[ChatVisualization] = Field(default_factory=list)
    suggested_follow_ups: list[SuggestedFollowUp] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)
    numeric_evidence: list[NumericEvidence] = Field(default_factory=list)
    engine_results: list[RiskCapEvaluation] = Field(default_factory=list)
    scenario_evaluation: ScenarioEvaluation | None = None
    pension_tax_result: PensionTaxToolResult | None = None
    educational_portfolio_evaluation: EducationalPortfolioEvaluation | None = None
    educational_portfolio_evaluations: list[EducationalPortfolioEvaluation] = Field(
        default_factory=list
    )
    macro_regime_etf_outcomes: MacroRegimeEtfOutcomeEvaluation | None = None
    limitations: list[str] = Field(default_factory=list)
    conversation_context: ConversationContext | None = None

    @model_validator(mode="after")
    def verify_evidence_links(self) -> "ChatResponse":
        source_ids = {source.evidence_id for source in self.sources}
        referenced_ids = {
            evidence_id
            for section in self.sections
            for evidence_id in section.evidence_ids
        }
        referenced_ids.update(
            evidence_id
            for visualization in self.visualizations
            for evidence_id in visualization.evidence_ids
        )
        referenced_ids.update(item.evidence_id for item in self.news_items)
        referenced_ids.update(item.evidence_id for item in self.numeric_evidence)
        missing = referenced_ids - source_ids
        if missing:
            raise ValueError(f"answer evidence is missing sources: {sorted(missing)}")
        answer_claims = extract_numeric_claims(self.answer)
        section_claims: list[tuple[AnswerSection, set[tuple[Decimal, str]]]] = []
        source_by_id = {source.evidence_id: source for source in self.sources}
        for section in self.sections:
            is_verified_excerpt = (
                section.kind == SectionKind.FACT
                and section.evidence_ids
                and all(
                    source_by_id[evidence_id].data_boundary
                    == DataBoundary.VERIFIED_KNOWLEDGE
                    for evidence_id in section.evidence_ids
                )
            )
            # Verified RAG excerpts are verbatim, source-linked evidence rather
            # than generated claims. Do not duplicate every excerpt value as a UI card.
            if not is_verified_excerpt:
                section_claims.append(
                    (section, extract_numeric_claims(section.plain_text()))
                )
        numeric_claims = answer_claims.union(
            *(claims for _, claims in section_claims)
        )
        visualization_claims = {
            _normalize_numeric_value(item.value, item.unit)
            for visualization in self.visualizations
            for item in visualization.items
        }
        if numeric_claims and not self.sources:
            raise ValueError("answers containing numbers require at least one source")
        if self.intent != ChatIntent.NEWS:
            all_supported_claims = {
                numeric_evidence_claim(item) for item in self.numeric_evidence
            }
            unsupported_claims = (
                answer_claims | visualization_claims
            ) - all_supported_claims
            for section, claims in section_claims:
                section_supported_claims = {
                    numeric_evidence_claim(item)
                    for item in self.numeric_evidence
                    if item.evidence_id in section.evidence_ids
                }
                unsupported_claims.update(claims - section_supported_claims)
            if unsupported_claims:
                formatted = sorted(
                    f"{value.normalize()} {unit}"
                    for value, unit in unsupported_claims
                )
                raise ValueError(
                    "numeric claims require matching NumericEvidence: "
                    f"{formatted}"
                )
        return self


class ScenarioSummary(BaseModel):
    code: str
    name: str
    description: str
    age_band: str
    risk_profile: str
    investment_horizon_years: int


class ChatCapabilities(BaseModel):
    supported: list[str]
    conditional: list[str]
    unsupported: list[str]
    scenario_codes: list[str]
