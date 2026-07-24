"""Owner-scoped persistence for engine-evaluated investor profiles."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict

from .engine.models import RiskProfile
from .engine.profile import ProfileEvaluation, ProfileSurveyInput
from .investment_profile_policy import PROFILE_VALIDITY_POLICY_VERSION


class InvestmentProfileAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_code: str
    selected_value: str
    selected_label: str
    selected_score: int


class InvestmentProfileAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: UUID
    owner_id: UUID
    assessed_at: datetime
    total_score: int
    min_score: int
    max_score: int
    score_percent: Decimal
    risk_profile: RiskProfile
    engine_name: str
    engine_version: str
    rule_version: str
    provisional: bool
    answers: list[InvestmentProfileAnswer]


class InvestmentProfilePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investment_advice_desired: bool
    investor_information_provided: bool
    confirmed_at: datetime
    policy_version: str


class InvestmentProfilePreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investment_advice_desired: bool
    investor_information_provided: bool


class StoredInvestmentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: InvestmentProfileAssessment
    preferences: InvestmentProfilePreferences | None


class InvestmentProfileRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
        ephemeral_owner_ids: frozenset[UUID] = frozenset(),
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool
        self._ephemeral_owner_ids = ephemeral_owner_ids

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def record(
        self,
        *,
        owner_id: UUID,
        survey: ProfileSurveyInput,
        evaluation: ProfileEvaluation,
        preferences: InvestmentProfilePreferencesInput,
    ) -> StoredInvestmentProfile:
        if owner_id in self._ephemeral_owner_ids:
            return self._unsaved_profile(owner_id, evaluation, preferences)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    question_set.id, question_set.engine_name,
                    question_set.engine_version, question_set.rule_version,
                    question_set.provisional, question.id, question.code,
                    option.id, option.answer_value, option.label, option.score
                from public.profile_question_sets as question_set
                join public.profile_questions as question
                  on question.question_set_id = question_set.id
                join public.profile_question_options as option
                  on option.question_id = question.id
                where question_set.status = 'active'
                order by question.display_order, option.display_order
                """
            )
            question_set_id, answer_rows = self._answers_for_active_question_set(
                list(cursor), survey, evaluation
            )
            cursor.execute(
                """
                insert into public.investment_profile_assessments (
                    owner_id, question_set_id, total_score, min_score, max_score,
                    score_percent, risk_profile, engine_name, engine_version,
                    rule_version, provisional
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    owner_id,
                    question_set_id,
                    evaluation.total_score,
                    evaluation.min_score,
                    evaluation.max_score,
                    evaluation.score_percent,
                    evaluation.risk_profile.value,
                    evaluation.engine_name,
                    evaluation.engine_version,
                    evaluation.rule_version,
                    evaluation.provisional,
                ),
            )
            assessment_row = cursor.fetchone()
            if assessment_row is None:
                raise RuntimeError("failed to create investment profile assessment")
            assessment_id = assessment_row[0]
            cursor.executemany(
                """
                insert into public.investment_profile_answers (
                    assessment_id, question_id, option_id, selected_value,
                    selected_label, selected_score
                )
                values (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (assessment_id, question_id, option_id, value, label, score)
                    for question_id, option_id, value, label, score in answer_rows
                ],
            )
            cursor.execute(
                """
                insert into public.investment_profile_confirmations (
                    assessment_id, owner_id, investment_advice_desired,
                    investor_information_provided, policy_version
                )
                values (%s, %s, %s, %s, %s)
                """,
                (
                    assessment_id,
                    owner_id,
                    preferences.investment_advice_desired,
                    preferences.investor_information_provided,
                    PROFILE_VALIDITY_POLICY_VERSION,
                ),
            )
        stored = self.get_latest(owner_id)
        if stored is None:
            raise RuntimeError("stored investment profile is missing")
        return stored

    @staticmethod
    def _unsaved_profile(
        owner_id: UUID,
        evaluation: ProfileEvaluation,
        preferences: InvestmentProfilePreferencesInput,
    ) -> StoredInvestmentProfile:
        """시연·테스트 계정용. 저장하지 않고 평가 결과만 조립해 돌려준다.

        DB에 아무것도 쓰지 않으므로 이후 get_latest는 계속 None을 반환한다.
        """
        now = datetime.now(UTC)
        return StoredInvestmentProfile(
            assessment=InvestmentProfileAssessment(
                assessment_id=uuid4(),
                owner_id=owner_id,
                assessed_at=now,
                total_score=evaluation.total_score,
                min_score=evaluation.min_score,
                max_score=evaluation.max_score,
                score_percent=evaluation.score_percent,
                risk_profile=evaluation.risk_profile,
                engine_name=evaluation.engine_name,
                engine_version=evaluation.engine_version,
                rule_version=evaluation.rule_version,
                provisional=evaluation.provisional,
                answers=[
                    InvestmentProfileAnswer(
                        question_code=answer.question_code,
                        selected_value=answer.selected_value,
                        selected_label=answer.selected_label,
                        selected_score=answer.selected_score,
                    )
                    for answer in evaluation.answers
                ],
            ),
            preferences=InvestmentProfilePreferences(
                investment_advice_desired=preferences.investment_advice_desired,
                investor_information_provided=(
                    preferences.investor_information_provided
                ),
                confirmed_at=now,
                policy_version=PROFILE_VALIDITY_POLICY_VERSION,
            ),
        )

    def get_latest(self, owner_id: UUID) -> StoredInvestmentProfile | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    assessment.id, assessment.owner_id, assessment.assessed_at,
                    assessment.total_score, assessment.min_score,
                    assessment.max_score, assessment.score_percent,
                    assessment.risk_profile, assessment.engine_name,
                    assessment.engine_version, assessment.rule_version,
                    assessment.provisional, confirmation.investment_advice_desired,
                    confirmation.investor_information_provided,
                    confirmation.confirmed_at, confirmation.policy_version
                from public.investment_profile_assessments as assessment
                left join public.investment_profile_confirmations as confirmation
                  on confirmation.assessment_id = assessment.id
                 and confirmation.owner_id = assessment.owner_id
                where assessment.owner_id = %s
                order by assessment.assessed_at desc, assessment.id desc
                limit 1
                """,
                (owner_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """
                select question.code, answer.selected_value, answer.selected_label,
                       answer.selected_score
                from public.investment_profile_answers as answer
                join public.profile_questions as question
                  on question.id = answer.question_id
                join public.investment_profile_assessments as assessment
                  on assessment.id = answer.assessment_id
                where answer.assessment_id = %s
                  and assessment.owner_id = %s
                order by question.display_order
                """,
                (row[0], owner_id),
            )
            answers = [
                InvestmentProfileAnswer(
                    question_code=answer_row[0],
                    selected_value=answer_row[1],
                    selected_label=answer_row[2],
                    selected_score=answer_row[3],
                )
                for answer_row in cursor
            ]
        preferences = (
            InvestmentProfilePreferences(
                investment_advice_desired=row[12],
                investor_information_provided=row[13],
                confirmed_at=row[14],
                policy_version=row[15],
            )
            if row[12] is not None
            else None
        )
        return StoredInvestmentProfile(
            assessment=InvestmentProfileAssessment(
                assessment_id=row[0],
                owner_id=row[1],
                assessed_at=row[2],
                total_score=row[3],
                min_score=row[4],
                max_score=row[5],
                score_percent=row[6],
                risk_profile=row[7],
                engine_name=row[8],
                engine_version=row[9],
                rule_version=row[10],
                provisional=row[11],
                answers=answers,
            ),
            preferences=preferences,
        )

    @staticmethod
    def _answers_for_active_question_set(
        rows: Sequence[Sequence[object]],
        survey: ProfileSurveyInput,
        evaluation: ProfileEvaluation,
    ) -> tuple[int, list[tuple[int, int, str, str, int]]]:
        if not rows:
            raise RuntimeError("active profile question set is missing")
        first = rows[0]
        if tuple(first[1:5]) != (
            evaluation.engine_name,
            evaluation.engine_version,
            evaluation.rule_version,
            evaluation.provisional,
        ):
            raise RuntimeError("active profile question set does not match the engine")
        question_set_ids = {int(row[0]) for row in rows}
        if len(question_set_ids) != 1:
            raise RuntimeError("exactly one active profile question set is required")
        selected_options = {
            (answer.question_code, answer.selected_value): answer
            for answer in evaluation.answers
        }
        selected: dict[tuple[str, str], tuple[int, int, str, str, int]] = {}
        for row in rows:
            question_id, code, option_id, value, label, score = row[5:]
            key = (str(code), str(value))
            expected = selected_options.get(key)
            if expected is not None:
                if expected.selected_score != score or expected.selected_label != label:
                    raise RuntimeError(
                        "profile survey option does not match active DB options"
                    )
                selected[key] = (
                    int(question_id),
                    int(option_id),
                    str(value),
                    str(label),
                    int(score),
                )
        if set(selected) != set(selected_options):
            raise RuntimeError("profile survey answers do not match active DB options")
        return question_set_ids.pop(), [
            selected[(answer.question_code, answer.selected_value)]
            for answer in evaluation.answers
        ]
