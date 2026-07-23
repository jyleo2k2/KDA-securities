"""시연·테스트 계정은 설문 결과를 저장하지 않는다."""

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest

from backend.app.engine.profile import (
    QUESTIONS,
    ProfileSurveyInput,
    evaluate_profile,
)
from backend.app.investment_profile_repository import (
    InvestmentProfilePreferencesInput,
    InvestmentProfileRepository,
)
from backend.app.settings import Settings

DUMMY_DATABASE_URL = "postgresql://unused/unused"


class DatabaseTouched(RuntimeError):
    """DB 연결이 열리면 발생. 저장 경로를 탔다는 신호."""


@pytest.fixture(autouse=True)
def _forbid_real_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB 연결 시도를 즉시 예외로 바꾼다(느린 타임아웃 제거)."""

    @contextmanager
    def _raise(self: InvestmentProfileRepository):
        raise DatabaseTouched
        yield  # pragma: no cover

    monkeypatch.setattr(InvestmentProfileRepository, "_connection", _raise)

EPHEMERAL_OWNER_ID = UUID("00000000-0000-4000-8000-000000000abc")


def _survey() -> ProfileSurveyInput:
    return ProfileSurveyInput.model_validate(
        {
            "answers": [
                {
                    "question_code": question.code,
                    "selected_values": [question.options[0].value],
                }
                for question in QUESTIONS
            ]
        }
    )


def _preferences() -> InvestmentProfilePreferencesInput:
    return InvestmentProfilePreferencesInput(
        investment_advice_desired=True,
        investor_information_provided=True,
    )


def test_ephemeral_owner_record_does_not_touch_database() -> None:
    repository = InvestmentProfileRepository(
        DUMMY_DATABASE_URL,
        ephemeral_owner_ids=frozenset({EPHEMERAL_OWNER_ID}),
    )
    survey = _survey()
    evaluation = evaluate_profile(survey)

    stored = repository.record(
        owner_id=EPHEMERAL_OWNER_ID,
        survey=survey,
        evaluation=evaluation,
        preferences=_preferences(),
    )

    # 결과는 정상적으로 돌아온다(화면 표시용).
    assert stored.assessment.owner_id == EPHEMERAL_OWNER_ID
    assert stored.assessment.risk_profile == evaluation.risk_profile
    assert stored.assessment.total_score == evaluation.total_score
    assert len(stored.assessment.answers) == len(evaluation.answers)
    assert stored.preferences is not None
    assert stored.preferences.investment_advice_desired is True


def test_non_ephemeral_owner_still_uses_database() -> None:
    repository = InvestmentProfileRepository(
        DUMMY_DATABASE_URL,
        ephemeral_owner_ids=frozenset({EPHEMERAL_OWNER_ID}),
    )
    survey = _survey()

    # 허용 목록 밖 사용자는 평소대로 저장 경로(DB 연결)를 타야 한다.
    with pytest.raises(DatabaseTouched):
        repository.record(
            owner_id=uuid4(),
            survey=survey,
            evaluation=evaluate_profile(survey),
            preferences=_preferences(),
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", frozenset()),
        (
            "00000000-0000-4000-8000-000000000abc",
            frozenset({EPHEMERAL_OWNER_ID}),
        ),
        (
            " 00000000-0000-4000-8000-000000000abc , ",
            frozenset({EPHEMERAL_OWNER_ID}),
        ),
    ],
)
def test_settings_parses_owner_id_allowlist(
    raw: str, expected: frozenset[UUID]
) -> None:
    settings = Settings(ephemeral_investment_profile_owner_ids=raw)
    assert settings.ephemeral_investment_profile_owner_id_set() == expected
