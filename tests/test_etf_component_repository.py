from datetime import UTC, datetime
from decimal import Decimal

from backend.app.etf_component_repository import EtfComponentSnapshotRepository


class _Cursor:
    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[object, ...]]:
        return [
            (
                "123456",
                datetime(2026, 7, 21, 3, tzinfo=UTC),
                1,
                "005930",
                "삼성전자",
                Decimal("25.5"),
            ),
            (
                "123456",
                datetime(2026, 7, 21, 3, tzinfo=UTC),
                2,
                "000660",
                "SK하이닉스",
                Decimal("18.25"),
            ),
        ]

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.cursor_obj = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_obj

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_latest_component_snapshot_returns_ranked_top3() -> None:
    connection = _Connection()
    repository = EtfComponentSnapshotRepository(
        "postgresql://example",
        connection_factory=lambda _: connection,
    )

    snapshots = repository.latest_for(["123456", "123456"])

    assert connection.cursor_obj.params == (["123456"],)
    assert "distinct on (isu_code)" in connection.cursor_obj.query.lower()
    assert "status = 'succeeded'" in connection.cursor_obj.query.lower()
    assert "component_count > 0" in connection.cursor_obj.query.lower()
    assert [item.component_name for item in snapshots["123456"].holdings] == [
        "삼성전자",
        "SK하이닉스",
    ]
    assert snapshots["123456"].holdings[0].weight_percent == Decimal("25.5")
