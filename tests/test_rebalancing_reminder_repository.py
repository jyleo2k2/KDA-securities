from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from backend.app.rebalancing_reminder_repository import (
    RebalancingReminderRepository,
    _add_months,
)

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeCursor:
    def __init__(self, row: tuple | None) -> None:
        self.row = row
        self.queries: list[str] = []
        self.params: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query: str, params: tuple) -> None:
        self.queries.append(query)
        self.params.append(params)

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


class FakePool:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    @contextmanager
    def connection(self):
        yield FakeConnection(self.cursor)


def test_calendar_month_addition_clamps_end_of_month() -> None:
    assert _add_months(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(
        2026, 2, 28, tzinfo=UTC
    )


def test_due_state_uses_profile_cadence_and_last_completed_review() -> None:
    cursor = FakeCursor(
        (
            "aggressive",
            datetime(2026, 6, 15, tzinfo=UTC),
            True,
            datetime(2026, 6, 20, tzinfo=UTC),
        )
    )
    repository = RebalancingReminderRepository(
        "postgresql://test", pool=FakePool(cursor)  # type: ignore[arg-type]
    )

    state = repository.get_state(OWNER_ID, now=datetime(2026, 7, 20, tzinfo=UTC))

    assert state.risk_profile == "aggressive"
    assert state.cadence is not None
    assert state.cadence.review_interval_months == 1
    assert state.next_review_at == datetime(2026, 7, 20, tzinfo=UTC)
    assert state.is_due is True
    assert cursor.params == [(OWNER_ID,)]
    assert "assessment.owner_id = %s" in cursor.queries[0]


def test_profile_required_has_no_schedule() -> None:
    repository = RebalancingReminderRepository(
        "postgresql://test", pool=FakePool(FakeCursor(None))  # type: ignore[arg-type]
    )

    state = repository.get_state(OWNER_ID)

    assert state.profile_required is True
    assert state.enabled is False
    assert state.cadence is None
