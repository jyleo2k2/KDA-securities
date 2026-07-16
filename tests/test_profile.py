from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.models import RiskProfile
from backend.app.engine.profile import (
    QUESTIONS,
    ProfileSurveyInput,
    SurveyAnswer,
    evaluate_profile,
)


def survey_with_total(total_score: int) -> ProfileSurveyInput:
    extra = total_score - len(QUESTIONS)
    assert 0 <= extra <= len(QUESTIONS) * 4
    answers = []
    for question in QUESTIONS:
        bump = min(extra, 4)
        extra -= bump
        answers.append(
            SurveyAnswer(question_code=question.code, selected_score=1 + bump)
        )
    return ProfileSurveyInput(answers=answers)


@pytest.mark.parametrize(
    ("total_score", "expected_profile"),
    [
        (6, RiskProfile.STABLE),
        (10, RiskProfile.STABLE),
        (11, RiskProfile.STABLE_SEEKING),
        (15, RiskProfile.STABLE_SEEKING),
        (16, RiskProfile.RISK_NEUTRAL),
        (20, RiskProfile.RISK_NEUTRAL),
        (21, RiskProfile.ACTIVE),
        (25, RiskProfile.ACTIVE),
        (26, RiskProfile.AGGRESSIVE),
        (30, RiskProfile.AGGRESSIVE),
    ],
)
def test_band_boundaries(total_score: int, expected_profile: RiskProfile) -> None:
    evaluation = evaluate_profile(survey_with_total(total_score))
    assert evaluation.total_score == total_score
    assert evaluation.risk_profile == expected_profile


def test_score_percent_spans_zero_to_hundred() -> None:
    assert evaluate_profile(survey_with_total(6)).score_percent == Decimal("0.00")
    assert evaluate_profile(survey_with_total(30)).score_percent == Decimal("100.00")


def test_missing_question_is_rejected() -> None:
    answers = [
        SurveyAnswer(question_code=question.code, selected_score=3)
        for question in QUESTIONS[:-1]
    ]
    with pytest.raises(ValidationError):
        ProfileSurveyInput(answers=answers)


def test_duplicate_question_is_rejected() -> None:
    answers = [
        SurveyAnswer(question_code=question.code, selected_score=3)
        for question in QUESTIONS
    ]
    answers[-1] = SurveyAnswer(
        question_code=QUESTIONS[0].code, selected_score=3
    )
    with pytest.raises(ValidationError):
        ProfileSurveyInput(answers=answers)


def test_unknown_question_is_rejected() -> None:
    answers = [
        SurveyAnswer(question_code=question.code, selected_score=3)
        for question in QUESTIONS[:-1]
    ]
    answers.append(SurveyAnswer(question_code="unknown_topic", selected_score=3))
    with pytest.raises(ValidationError):
        ProfileSurveyInput(answers=answers)


def test_out_of_range_score_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SurveyAnswer(question_code=QUESTIONS[0].code, selected_score=0)
    with pytest.raises(ValidationError):
        SurveyAnswer(question_code=QUESTIONS[0].code, selected_score=6)


def test_evaluation_is_deterministic_and_marked_provisional() -> None:
    survey = survey_with_total(18)
    first = evaluate_profile(survey).model_dump(mode="json")
    second = evaluate_profile(survey).model_dump(mode="json")
    assert first == second
    assert first["provisional"] is True
    assert "provisional" in first["rule_version"]


def test_loss_tolerance_answer_becomes_engine_input_percent() -> None:
    evaluation = evaluate_profile(survey_with_total(18))
    loss_answer = next(
        answer
        for answer in survey_with_total(18).answers
        if answer.question_code == "loss_tolerance"
    )
    expected = {
        1: Decimal("5"),
        2: Decimal("10"),
        3: Decimal("20"),
        4: Decimal("30"),
        5: Decimal("40"),
    }[loss_answer.selected_score]

    assert evaluation.loss_tolerance_percent == expected
