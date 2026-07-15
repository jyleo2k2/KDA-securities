"""Rule-based investor profile scoring (아키텍처.md §2 module 1).

The questionnaire and score bands below are provisional placeholders.
TODO: 확인 필요 — 금융투자협회 표준투자권유준칙의 확정 문항·배점이 정해지면
QUESTIONS/BAND_UPPER_BOUNDS_PERCENT를 교체하고 RULE_VERSION을 올린다.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import RiskProfile, SourceChip

ENGINE_NAME = "investor_profile"
ENGINE_VERSION = "2026-07-15.1"
RULE_VERSION = "2026-07-15-provisional"
MIN_ANSWER_SCORE = 1
MAX_ANSWER_SCORE = 5
PERCENT_QUANTUM = Decimal("0.01")
PROFILE_SOURCE = SourceChip(
    label="아키텍처 §2 모듈 1 (잠정 기준)",
    reference="docs/30_스펙/아키텍처.md#2-규칙-엔진-6모듈--계산판단의-단일-소스",
    as_of=date(2026, 7, 15),
)


class ProfileQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    topic: str


QUESTIONS: tuple[ProfileQuestion, ...] = (
    ProfileQuestion(code="investment_horizon", topic="투자 예정 기간"),
    ProfileQuestion(code="investment_experience", topic="투자 경험"),
    ProfileQuestion(code="financial_knowledge", topic="금융상품 지식 수준"),
    ProfileQuestion(code="risky_asset_share", topic="현재 위험자산 비중"),
    ProfileQuestion(code="loss_tolerance", topic="감내 가능한 손실 수준"),
    ProfileQuestion(code="income_stability", topic="소득 안정성"),
)
QUESTION_CODES = frozenset(question.code for question in QUESTIONS)

# Upper bounds (exclusive) of score_percent per band; None marks the top band.
BAND_UPPER_BOUNDS_PERCENT: dict[RiskProfile, Decimal | None] = {
    RiskProfile.STABLE: Decimal("20"),
    RiskProfile.STABLE_SEEKING: Decimal("40"),
    RiskProfile.RISK_NEUTRAL: Decimal("60"),
    RiskProfile.ACTIVE: Decimal("80"),
    RiskProfile.AGGRESSIVE: None,
}


class SurveyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_code: str = Field(min_length=1)
    selected_score: int = Field(ge=MIN_ANSWER_SCORE, le=MAX_ANSWER_SCORE)


class ProfileSurveyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[SurveyAnswer] = Field(min_length=1)

    @model_validator(mode="after")
    def require_exactly_one_answer_per_question(self) -> "ProfileSurveyInput":
        answered = [answer.question_code for answer in self.answers]
        if len(answered) != len(set(answered)):
            raise ValueError("duplicate answers for the same question are not allowed")
        if set(answered) != QUESTION_CODES:
            raise ValueError(
                "answers must cover every profile question exactly once"
            )
        return self


class ProfileEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    rule_version: str
    provisional: bool
    total_score: int
    min_score: int
    max_score: int
    score_percent: Decimal
    risk_profile: RiskProfile
    band_upper_bounds_percent: dict[RiskProfile, Decimal | None]
    evidence: list[SourceChip]


def evaluate_profile(survey: ProfileSurveyInput) -> ProfileEvaluation:
    """Score the survey into 금투협 5단계 without any LLM involvement."""

    total_score = sum(answer.selected_score for answer in survey.answers)
    min_score = len(QUESTIONS) * MIN_ANSWER_SCORE
    max_score = len(QUESTIONS) * MAX_ANSWER_SCORE
    exact_percent = (
        Decimal(total_score - min_score)
        * Decimal("100")
        / Decimal(max_score - min_score)
    )

    risk_profile = RiskProfile.AGGRESSIVE
    for band, upper_bound in BAND_UPPER_BOUNDS_PERCENT.items():
        if upper_bound is None or exact_percent < upper_bound:
            risk_profile = band
            break

    return ProfileEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        rule_version=RULE_VERSION,
        provisional=True,
        total_score=total_score,
        min_score=min_score,
        max_score=max_score,
        score_percent=exact_percent.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP),
        risk_profile=risk_profile,
        band_upper_bounds_percent=BAND_UPPER_BOUNDS_PERCENT,
        evidence=[PROFILE_SOURCE],
    )
