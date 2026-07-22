# ruff: noqa: E501
"""Rule-based investor-profile scoring for the login investor-information form.

The login form keeps its existing contextual questions and adds the missing
Shinhan personal-general questionnaire fields.  Only the Shinhan scoring
fields contribute to the 56-point profile result; contextual and pension
planning fields are persisted with a zero score.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import RiskProfile, SourceChip

ENGINE_NAME = "investor_profile"
ENGINE_VERSION = "2026-07-22.1"
RULE_VERSION = "shinhan-personal-general-login-union-2026-07-22"
PERCENT_QUANTUM = Decimal("0.01")
PROFILE_SOURCE = SourceChip(
    label="신한증권 개인 일반투자자정보 확인서 배점표",
    reference="docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md#1-개인용--일반투자자-투자자정보-확인서-설문-문항--배점",
    as_of=date(2021, 5, 20),
)


class ProfileOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str
    label: str
    score: int = Field(ge=0, le=7)
    loss_tolerance_percent: Decimal | None = None


class ProfileQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    topic: str
    multi: bool = False
    options: tuple[ProfileOption, ...]


def _options(*values: tuple[str, str, int]) -> tuple[ProfileOption, ...]:
    return tuple(
        ProfileOption(value=value, label=label, score=score)
        for value, label, score in values
    )


def _question(
    code: str,
    topic: str,
    *,
    options: tuple[ProfileOption, ...],
    multi: bool = False,
) -> ProfileQuestion:
    return ProfileQuestion(code=code, topic=topic, options=options, multi=multi)


QUESTIONS: tuple[ProfileQuestion, ...] = (
    _question(
        "age_band",
        "연령대",
        options=_options(
            ("under_19", "만19세 미만", 0),
            ("19_to_40", "만19세~만40세", 0),
            ("41_to_50", "만41세~만50세", 0),
            ("51_to_64", "만51세~만64세", 0),
            ("65_to_79", "만65세~만79세", 0),
            ("80_plus", "만80세 이상", 0),
        ),
    ),
    _question(
        "total_net_assets",
        "총 자산규모(순자산)",
        options=_options(
            ("under_100m", "1억원 미만", 1),
            ("100m_to_500m", "1억원 이상~5억원 미만", 2),
            ("500m_to_1b", "5억원 이상~10억원 미만", 3),
            ("1b_to_2b", "10억원 이상~20억원 미만", 4),
            ("over_2b", "20억원 이상", 5),
        ),
    ),
    _question(
        "annual_income",
        "연간 소득 현황",
        options=_options(
            ("under_20m", "2천만원 미만", 1),
            ("20m_to_50m", "2천만원 이상~5천만원 미만", 2),
            ("50m_to_70m", "5천만원 이상~7천만원 미만", 3),
            ("70m_to_100m", "7천만원 이상~1억원 미만", 4),
            ("over_100m", "1억원 이상", 5),
        ),
    ),
    _question(
        "financial_asset_share",
        "전체 자산 중 금융자산 비중",
        options=_options(
            ("under_10", "10% 미만", 0),
            ("10_to_20", "10% ~ 20% 미만", 0),
            ("20_to_30", "20% ~ 30% 미만", 0),
            ("30_to_50", "30% ~ 50% 미만", 0),
            ("over_50", "50% 이상", 0),
        ),
    ),
    _question(
        "investment_product_share",
        "총자산 대비 투자성 상품 비중",
        options=_options(
            ("under_10", "0~9%", 1),
            ("10_to_20", "10~19%", 2),
            ("20_to_30", "20~29%", 3),
            ("30_to_50", "30~49%", 4),
            ("over_50", "50% 이상", 5),
        ),
    ),
    _question(
        "loan_product_share",
        "총자산 대비 대출성 상품 비중",
        options=_options(
            ("under_10", "0~9%", 1),
            ("10_to_20", "10~19%", 2),
            ("20_to_30", "20~29%", 3),
            ("30_to_50", "30~49%", 4),
            ("over_50", "50% 이상", 5),
        ),
    ),
    _question(
        "investment_experience_product",
        "투자경험이 있는 금융투자상품",
        multi=True,
        options=_options(
            ("very_low", "예금, CMA, MMF, RP, 국공채 등", 1),
            ("low", "채권형펀드, 원금보장형 ELB/DLB, 금융채 등", 3),
            ("medium", "혼합형펀드, 원금부분보장형 ELS/DLS, 일반회사채", 4),
            ("high", "주식, 주식형펀드, 원금비보장형 ELS/DLS, 고위험회사채", 5),
            ("very_high", "파생상품펀드, ELW, 선물·옵션, 주식신용거래 등", 6),
        ),
    ),
    _question(
        "investment_experience_period",
        "금융투자상품 투자경험 기간",
        options=_options(
            ("none", "투자경험 없음", 0),
            ("under_1y", "1년 미만", 1),
            ("1_to_3y", "1년 이상~3년 미만", 3),
            ("over_3y", "3년 이상", 5),
        ),
    ),
    _question(
        "investment_purpose",
        "금융투자상품 취득 및 처분 목적",
        multi=True,
        options=_options(
            ("education", "교육비", 1),
            ("living", "생활비", 1),
            ("marriage", "결혼자금", 1),
            ("debt", "채무상환", 1),
            ("housing", "주택마련자금", 2),
            ("growth", "자산증식자금", 3),
        ),
    ),
    _question(
        "financial_knowledge",
        "금융상품 지식 수준",
        options=_options(
            ("basic", "금융투자상품에 투자해 본 경험이 없음", 1),
            (
                "partial",
                "주식, 채권, 펀드 등의 구조와 위험을 일정 부분 이해하고 있음",
                3,
            ),
            ("deep", "주식, 채권, 펀드 등의 구조와 위험을 깊이 있게 이해하고 있음", 4),
            (
                "derivatives",
                "파생상품을 포함한 대부분의 금융상품 구조와 위험을 이해하고 있음",
                5,
            ),
        ),
    ),
    _question(
        "investment_horizon",
        "현재 투자자금의 투자예정기간",
        options=_options(
            ("under_1y", "1년 미만", 1),
            ("1_to_2y", "1년 이상~2년 미만", 2),
            ("2_to_3y", "2년 이상~3년 미만", 3),
            ("3_to_5y", "3년 이상~5년 미만", 4),
            ("over_5y", "5년 이상", 5),
        ),
    ),
    _question(
        "risk_attitude",
        "투자수익 및 위험에 대한 태도",
        options=_options(
            ("principal", "투자 수익을 고려하나 원금 보존이 더 중요함", 1),
            ("balanced", "원금 보존을 고려하나 투자 수익이 더 중요함", 3),
            ("return", "손실 위험이 있더라도 투자 수익이 더 중요함", 5),
        ),
    ),
    _question(
        "loss_tolerance",
        "기대수익률 및 손실감내도",
        options=(
            ProfileOption(
                value="limited",
                label="제한적인 손실을 감수하여 시중금리 수준의 수익을 기대",
                score=1,
                loss_tolerance_percent=Decimal("5"),
            ),
            ProfileOption(
                value="partial",
                label="원금의 일부 손실을 감수하여 시중금리보다 다소 높은 수준의 수익을 기대",
                score=3,
                loss_tolerance_percent=Decimal("15"),
            ),
            ProfileOption(
                value="principal_loss",
                label="원금 손실을 감수하여 시장수익률과 비슷한 수준의 수익을 기대",
                score=5,
                loss_tolerance_percent=Decimal("30"),
            ),
            ProfileOption(
                value="beyond_principal",
                label="원금 초과 손실까지 감수하여 시장수익률을 초과하는 높은 수익을 추구",
                score=7,
                loss_tolerance_percent=Decimal("50"),
            ),
        ),
    ),
    _question(
        "derivative_experience",
        "파생상품 투자경험",
        options=_options(
            ("none", "투자경험 없음", 0),
            ("under_1y", "1년 미만", 0),
            ("1_to_3y", "1년 ~ 3년 미만", 0),
            ("over_3y", "3년 이상", 0),
        ),
    ),
    _question(
        "vulnerable_investor",
        "취약 금융소비자 여부",
        options=_options(
            ("yes", "예", 0),
            ("no", "아니오", 0),
        ),
    ),
    _question(
        "validity_consent",
        "투자자정보 유효기간 설정 동의",
        options=_options(
            ("agree", "동의", 0),
            ("disagree", "미동의", 0),
        ),
    ),
    _question(
        "retirement_start_age",
        "연금 수령 개시 나이",
        options=_options(
            ("55", "만 55세", 0),
            ("56", "만 56세", 0),
            ("57", "만 57세", 0),
            ("58", "만 58세", 0),
            ("59", "만 59세", 0),
            ("60", "만 60세", 0),
        ),
    ),
)
QUESTION_BY_CODE = {question.code: question for question in QUESTIONS}
QUESTION_CODES = frozenset(QUESTION_BY_CODE)
SCORE_BANDS: tuple[tuple[int, RiskProfile], ...] = (
    (16, RiskProfile.STABLE),
    (24, RiskProfile.STABLE_SEEKING),
    (32, RiskProfile.RISK_NEUTRAL),
    (40, RiskProfile.ACTIVE),
    (56, RiskProfile.AGGRESSIVE),
)


class SurveyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_code: str = Field(min_length=1)
    selected_values: list[str] = Field(min_length=1)


class ProfileSurveyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[SurveyAnswer] = Field(min_length=1)

    @model_validator(mode="after")
    def require_complete_valid_answers(self) -> "ProfileSurveyInput":
        answered = [answer.question_code for answer in self.answers]
        if len(answered) != len(set(answered)) or set(answered) != QUESTION_CODES:
            raise ValueError("answers must cover every profile question exactly once")
        for answer in self.answers:
            question = QUESTION_BY_CODE[answer.question_code]
            if len(answer.selected_values) != len(set(answer.selected_values)):
                raise ValueError("selected_values must not contain duplicates")
            if not question.multi and len(answer.selected_values) != 1:
                raise ValueError(
                    f"{answer.question_code} requires exactly one selection"
                )
            allowed = {option.value for option in question.options}
            if any(value not in allowed for value in answer.selected_values):
                raise ValueError(f"{answer.question_code} contains an unknown option")
        return self


class EvaluatedProfileAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_code: str
    selected_value: str
    selected_label: str
    selected_score: int = Field(ge=0, le=7)


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
    loss_tolerance_percent: Decimal
    answers: list[EvaluatedProfileAnswer]
    evidence: list[SourceChip]


def _question_score(question: ProfileQuestion, selections: list[ProfileOption]) -> int:
    return max(option.score for option in selections)


def evaluate_profile(survey: ProfileSurveyInput) -> ProfileEvaluation:
    """Evaluate the complete login questionnaire without trusting client scores."""

    selections_by_code: dict[str, list[ProfileOption]] = {}
    evaluated_answers: list[EvaluatedProfileAnswer] = []
    for answer in survey.answers:
        question = QUESTION_BY_CODE[answer.question_code]
        options = {option.value: option for option in question.options}
        selected = [options[value] for value in answer.selected_values]
        selections_by_code[question.code] = selected
        evaluated_answers.extend(
            EvaluatedProfileAnswer(
                question_code=question.code,
                selected_value=option.value,
                selected_label=option.label,
                selected_score=option.score,
            )
            for option in selected
        )

    scored_questions = [
        question
        for question in QUESTIONS
        if any(option.score for option in question.options)
    ]
    total_score = sum(
        _question_score(question, selections_by_code[question.code])
        for question in scored_questions
    )
    min_score = sum(
        min(option.score for option in question.options)
        for question in scored_questions
    )
    max_score = sum(
        max(option.score for option in question.options)
        for question in scored_questions
    )
    risk_profile = next(
        profile for upper_bound, profile in SCORE_BANDS if total_score <= upper_bound
    )
    loss_option = selections_by_code["loss_tolerance"][0]
    assert loss_option.loss_tolerance_percent is not None
    score_percent = (
        Decimal(total_score - min_score)
        * Decimal("100")
        / Decimal(max_score - min_score)
    ).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
    return ProfileEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        rule_version=RULE_VERSION,
        provisional=False,
        total_score=total_score,
        min_score=min_score,
        max_score=max_score,
        score_percent=score_percent,
        risk_profile=risk_profile,
        loss_tolerance_percent=loss_option.loss_tolerance_percent,
        answers=evaluated_answers,
        evidence=[PROFILE_SOURCE],
    )
