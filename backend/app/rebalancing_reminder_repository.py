"""Owner-scoped persistence for user-approved rebalancing reminders."""

import calendar
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict

from .engine.educational_portfolio import (
    RebalancingCadenceGuidance,
    rebalancing_cadence,
)
from .engine.models import RiskProfile


class RebalancingReminderState(BaseModel):
    """A display model; cadence always comes from the pure rules engine."""

    model_config = ConfigDict(extra="forbid")

    profile_required: bool
    enabled: bool
    risk_profile: RiskProfile | None = None
    cadence: RebalancingCadenceGuidance | None = None
    last_reviewed_at: datetime | None = None
    next_review_at: datetime | None = None
    is_due: bool = False


def _add_months(value: datetime, months: int) -> datetime:
    """Keep the local calendar day where possible when advancing a review date."""

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class RebalancingReminderRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def get_state(
        self, owner_id: UUID, *, now: datetime | None = None
    ) -> RebalancingReminderState:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select assessment.risk_profile, assessment.assessed_at,
                       preference.enabled, preference.last_reviewed_at
                from public.investment_profile_assessments as assessment
                left join public.user_rebalancing_reminder_preferences as preference
                  on preference.owner_id = assessment.owner_id
                where assessment.owner_id = %s
                order by assessment.assessed_at desc, assessment.id desc
                limit 1
                """,
                (owner_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return RebalancingReminderState(profile_required=True, enabled=False)

        risk_profile = RiskProfile(row[0])
        assessed_at = row[1]
        enabled = bool(row[2]) if row[2] is not None else False
        last_reviewed_at = row[3]
        cadence = rebalancing_cadence(risk_profile)
        anchor_at = last_reviewed_at or assessed_at
        next_review_at = _add_months(anchor_at, cadence.review_interval_months)
        reference_now = now or datetime.now(UTC)
        return RebalancingReminderState(
            profile_required=False,
            enabled=enabled,
            risk_profile=risk_profile,
            cadence=cadence,
            last_reviewed_at=last_reviewed_at,
            next_review_at=next_review_at,
            is_due=enabled and reference_now >= next_review_at,
        )

    def update_enabled(
        self, owner_id: UUID, *, enabled: bool
    ) -> RebalancingReminderState:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.user_rebalancing_reminder_preferences (
                    owner_id, enabled, enabled_at
                )
                values (%s, %s, case when %s then now() else null end)
                on conflict (owner_id) do update set
                    enabled = excluded.enabled,
                    enabled_at = case
                        when excluded.enabled then now()
                        else public.user_rebalancing_reminder_preferences.enabled_at
                    end,
                    updated_at = now()
                """,
                (owner_id, enabled, enabled),
            )
        return self.get_state(owner_id)

    def record_review_completion(self, owner_id: UUID) -> RebalancingReminderState:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.user_rebalancing_reminder_preferences (
                    owner_id, last_reviewed_at
                )
                values (%s, now())
                on conflict (owner_id) do update set
                    last_reviewed_at = now(),
                    updated_at = now()
                """,
                (owner_id,),
            )
        return self.get_state(owner_id)
