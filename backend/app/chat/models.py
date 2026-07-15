import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..engine import PortfolioInput, RiskCapEvaluation, ScenarioEvaluation


class ChatIntent(StrEnum):
    ACCOUNT_RULE = "account_rule"
    MOCK_PORTFOLIO = "mock_portfolio"
    PROVIDER_DISCLOSURE = "provider_disclosure"
    NEWS = "news"
    OUT_OF_SCOPE = "out_of_scope"


class DataBoundary(StrEnum):
    VERIFIED_KNOWLEDGE = "verified_knowledge"
    OFFICIAL_DISCLOSURE = "official_disclosure"
    NEWS_METADATA = "news_metadata"
    MOCK = "mock"
    ENGINE = "engine"
    UNAVAILABLE = "unavailable"


class SectionKind(StrEnum):
    FACT = "fact"
    EXTERNAL_OPINION = "external_opinion"
    SERVICE_EXPLANATION = "service_explanation"
    LIMITATION = "limitation"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=2, max_length=1000)
    scenario_code: str | None = Field(default=None, min_length=1)
    portfolio: PortfolioInput | None = None
    max_results: int = Field(default=3, ge=1, le=5)

    @field_validator("message")
    @classmethod
    def reject_sensitive_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if re.search(r"\b\d{6}-?[1-8]\d{6}\b", normalized):
            raise ValueError("주민등록번호 형태의 개인정보는 입력할 수 없습니다")
        return normalized


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


class AnswerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SectionKind
    title: str
    content: str
    evidence_ids: list[str] = Field(default_factory=list)


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
    sections: list[AnswerSection] = Field(default_factory=list)
    sources: list[SourceEvidence] = Field(default_factory=list)
    numeric_evidence: list[NumericEvidence] = Field(default_factory=list)
    engine_results: list[RiskCapEvaluation] = Field(default_factory=list)
    scenario_evaluation: ScenarioEvaluation | None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify_evidence_links(self) -> "ChatResponse":
        source_ids = {source.evidence_id for source in self.sources}
        referenced_ids = {
            evidence_id
            for section in self.sections
            for evidence_id in section.evidence_ids
        }
        referenced_ids.update(item.evidence_id for item in self.numeric_evidence)
        missing = referenced_ids - source_ids
        if missing:
            raise ValueError(f"answer evidence is missing sources: {sorted(missing)}")
        text = " ".join([self.answer, *(section.content for section in self.sections)])
        if re.search(r"\d", text) and not self.sources:
            raise ValueError("answers containing numbers require at least one source")
        return self


class ScenarioSummary(BaseModel):
    code: str
    name: str
    description: str
    risk_profile: str
    investment_horizon_years: int


class ChatCapabilities(BaseModel):
    supported: list[str]
    conditional: list[str]
    unsupported: list[str]
    scenario_codes: list[str]
