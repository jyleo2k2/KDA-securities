from contextlib import contextmanager
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.api.deps import get_benchmark_follow_repository
from backend.app.auth import require_supabase_user_id
from backend.app.benchmark_follow_repository import (
    BenchmarkFollowRepository,
    BenchmarkFollowState,
)
from backend.app.main import app

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")
PORTFOLIO_ID = "꾸준한거북이"


class FakeCursor:
    def __init__(self, result_sets: list[list[tuple]]) -> None:
        self.result_sets = result_sets
        self.current_rows: list[tuple] = []
        self.queries: list[str] = []
        self.params: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query: str, params: tuple = ()) -> None:
        self.queries.append(query)
        self.params.append(params)
        self.current_rows = self.result_sets.pop(0) if self.result_sets else []

    def fetchone(self):
        return self.current_rows[0] if self.current_rows else None

    def __iter__(self):
        return iter(self.current_rows)


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


def test_repository_lists_aggregate_count_and_owner_follow_state() -> None:
    cursor = FakeCursor(
        [[(PORTFOLIO_ID, 1_207, True), ("배당모으미", 876, False)]]
    )
    repository = BenchmarkFollowRepository(
        "postgresql://test", pool=FakePool(cursor)  # type: ignore[arg-type]
    )

    states = repository.list_states(OWNER_ID)

    assert states == [
        BenchmarkFollowState(
            portfolio_id=PORTFOLIO_ID,
            follow_count=1_207,
            is_following=True,
        ),
        BenchmarkFollowState(
            portfolio_id="배당모으미",
            follow_count=876,
            is_following=False,
        ),
    ]
    assert cursor.params == [(OWNER_ID,)]
    assert "count(follow.owner_id)" in cursor.queries[0]


def test_repository_sets_follow_idempotently_and_returns_fresh_count() -> None:
    cursor = FakeCursor(
        [
            [],
            [(PORTFOLIO_ID, 1_205, True)],
        ]
    )
    repository = BenchmarkFollowRepository(
        "postgresql://test", pool=FakePool(cursor)  # type: ignore[arg-type]
    )

    state = repository.set_following(
        OWNER_ID,
        portfolio_id=PORTFOLIO_ID,
        following=True,
    )

    assert state.follow_count == 1_205
    assert state.is_following is True
    assert "on conflict (owner_id, portfolio_id) do nothing" in cursor.queries[0]
    assert cursor.params[0] == (OWNER_ID, PORTFOLIO_ID)


def test_follow_endpoints_are_authenticated_and_owner_scoped() -> None:
    calls: list[tuple[str, UUID, str | None, bool | None]] = []

    class Repository:
        def list_states(self, owner_id: UUID):
            calls.append(("list", owner_id, None, None))
            return [
                BenchmarkFollowState(
                    portfolio_id=PORTFOLIO_ID,
                    follow_count=1_204,
                    is_following=False,
                )
            ]

        def set_following(
            self,
            owner_id: UUID,
            *,
            portfolio_id: str,
            following: bool,
        ):
            calls.append(("set", owner_id, portfolio_id, following))
            return BenchmarkFollowState(
                portfolio_id=portfolio_id,
                follow_count=1_205,
                is_following=following,
            )

    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_benchmark_follow_repository] = Repository
    try:
        with TestClient(app) as client:
            listed = client.get("/me/benchmark-follows")
            followed = client.put(
                f"/me/benchmark-follows/{PORTFOLIO_ID}",
                json={"following": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert listed.status_code == 200
    assert listed.json() == [
        {
            "portfolio_id": PORTFOLIO_ID,
            "follow_count": 1_204,
            "is_following": False,
        }
    ]
    assert followed.status_code == 200
    assert followed.json()["follow_count"] == 1_205
    assert calls == [
        ("list", OWNER_ID, None, None),
        ("set", OWNER_ID, PORTFOLIO_ID, True),
    ]


def test_follow_endpoint_requires_authentication() -> None:
    assert TestClient(app).get("/me/benchmark-follows").status_code == 401
