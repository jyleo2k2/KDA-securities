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


def _survey_with_total(total_score: int) -> ProfileSurveyInput:
    """Build a valid complete survey with the requested Shinhan score."""
    scored = [
        question
        for question in QUESTIONS
        if any(option.score for option in question.options)
    ]
    choices: dict[int, dict[int, str]] = {0: {}}
    for question in scored:
        next_choices: dict[int, dict[int, str]] = {}
        for subtotal, chosen in choices.items():
            for option in question.options:
                candidate = subtotal + option.score
                next_choices.setdefault(
                    candidate, {**chosen, id(question): option.value}
                )
        choices = next_choices
    assert total_score in choices
    selected = choices[total_score]
    return ProfileSurveyInput(
        answers=[
            SurveyAnswer(
                question_code=question.code,
                selected_values=[selected.get(id(question), question.options[0].value)],
            )
            for question in QUESTIONS
        ]
    )


@pytest.mark.parametrize(
    ("total_score", "expected_profile"),
    [
        (10, RiskProfile.STABLE),
        (16, RiskProfile.STABLE),
        (17, RiskProfile.STABLE_SEEKING),
        (24, RiskProfile.STABLE_SEEKING),
        (25, RiskProfile.RISK_NEUTRAL),
        (32, RiskProfile.RISK_NEUTRAL),
        (33, RiskProfile.ACTIVE),
        (40, RiskProfile.ACTIVE),
        (41, RiskProfile.AGGRESSIVE),
        (56, RiskProfile.AGGRESSIVE),
    ],
)
def test_shinhan_score_bands(total_score: int, expected_profile: RiskProfile) -> None:
    evaluation = evaluate_profile(_survey_with_total(total_score))
    assert evaluation.total_score == total_score
    assert evaluation.risk_profile == expected_profile


def test_score_percent_spans_zero_to_hundred() -> None:
    assert evaluate_profile(_survey_with_total(10)).score_percent == Decimal("0.00")
    assert evaluate_profile(_survey_with_total(56)).score_percent == Decimal("100.00")


def test_missing_question_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileSurveyInput(answers=_survey_with_total(10).answers[:-1])


def test_duplicate_question_is_rejected() -> None:
    answers = _survey_with_total(10).answers
    answers[-1] = answers[0]
    with pytest.raises(ValidationError):
        ProfileSurveyInput(answers=answers)


def test_unknown_option_is_rejected() -> None:
    answers = _survey_with_total(10).answers
    answers[0] = SurveyAnswer(
        question_code=answers[0].question_code, selected_values=["unknown"]
    )
    with pytest.raises(ValidationError):
        ProfileSurveyInput(answers=answers)


def test_multi_select_uses_the_highest_shinhan_score_and_persists_all_choices() -> None:
    survey = _survey_with_total(10)
    survey.answers[6] = SurveyAnswer(
        question_code="investment_experience_product",
        selected_values=["very_low", "very_high"],
    )
    evaluation = evaluate_profile(survey)
    assert evaluation.total_score == 15
    stored = [
        answer
        for answer in evaluation.answers
        if answer.question_code == "investment_experience_product"
    ]
    assert [answer.selected_value for answer in stored] == ["very_low", "very_high"]


def test_loss_tolerance_answer_becomes_engine_input_percent() -> None:
    survey = _survey_with_total(10)
    survey.answers[12] = SurveyAnswer(
        question_code="loss_tolerance", selected_values=["beyond_principal"]
    )
    assert evaluate_profile(survey).loss_tolerance_percent == Decimal("50")
