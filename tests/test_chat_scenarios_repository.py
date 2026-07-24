from contextlib import contextmanager
from decimal import Decimal

from backend.app.chat.scenarios import PostgresScenarioRepository


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query: str, params=None) -> None:
        self.query = query

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    @contextmanager
    def connection(self):
        yield _FakeConnection(self._cursor)


def test_postgres_scenario_reads_linked_etf_code_and_verified_name() -> None:
    cursor = _FakeCursor(
        [
            (
                "family_budget_pressure",
                "가계지출 압박형",
                "설명",
                "40s",
                "balanced",
                13,
                15,
                "dc",
                "회사 DC",
                101,
                "KODEX 미국S&P500",
                "global_equity",
                Decimal("20000000"),
                "general_risky",
                None,
                "379800",
            )
        ]
    )
    repository = PostgresScenarioRepository(
        "postgresql://test",
        pool=_FakePool(cursor),
    )

    scenario = repository.get("family_budget_pressure")

    assert scenario is not None
    holding = scenario.accounts[0].holdings[0]
    assert holding.instrument_name == "KODEX 미국S&P500"
    assert holding.etf_isu_code == "379800"
    assert "pension_accounts" in cursor.query
    assert "account_snapshots" in cursor.query
    assert "account_holding_snapshots" in cursor.query
    assert "mock_accounts" not in cursor.query
    assert "mock_holdings" not in cursor.query
    assert "etf_universe_products" in cursor.query
    assert "holding.etf_isu_code" in cursor.query
    assert "holding.raw_instrument_name" in cursor.query
    assert "holding.instrument_name" not in cursor.query
