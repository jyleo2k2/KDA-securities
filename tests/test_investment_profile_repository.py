from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from backend.app.investment_profile_repository import InvestmentProfileRepository

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")
ASSESSMENT_ID = UUID("33333333-3333-3333-3333-333333333333")


class FakeCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[tuple] = []
        self._rows = [
            [
                (
                    ASSESSMENT_ID,
                    OWNER_ID,
                    datetime(2026, 1, 13, tzinfo=UTC),
                    18,
                    6,
                    30,
                    Decimal("50.00"),
                    "risk_neutral",
                    "investor_profile",
                    "2026-07-15.1",
                    "2026-07-15-provisional",
                    True,
                    False,
                    True,
                    datetime(2026, 1, 13, tzinfo=UTC),
                    "2026-07-20.1",
                )
            ],
            [("investment_horizon", "middle", "중기", 3)],
        ]
        self.current: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        self.queries.append(query)
        self.params.append(params)
        self.current = self._rows.pop(0)

    def fetchone(self):
        return self.current[0] if self.current else None

    def __iter__(self):
        return iter(self.current)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


class FakePool:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor
        self.calls = 0

    @contextmanager
    def connection(self):
        self.calls += 1
        yield FakeConnection(self.cursor)


def test_latest_profile_is_pool_backed_and_owner_scoped_in_both_queries() -> None:
    cursor = FakeCursor()
    pool = FakePool(cursor)
    repository = InvestmentProfileRepository("postgresql://test", pool=pool)  # type: ignore[arg-type]

    stored = repository.get_latest(OWNER_ID)

    assert stored is not None
    assert stored.assessment.owner_id == OWNER_ID
    assert stored.assessment.answers[0].selected_label == "중기"
    assert pool.calls == 1
    assert cursor.params == [(OWNER_ID,), (ASSESSMENT_ID, OWNER_ID)]
    assert all("assessment.owner_id = %s" in query for query in cursor.queries)
