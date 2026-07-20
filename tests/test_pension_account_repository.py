from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import get_pension_account_repository
from backend.app.auth import require_supabase_user_id
from backend.app.main import app
from backend.app.pension_accounts_repository import (
    PensionAccountDataError,
    PensionAccountRepository,
    UserPensionPortfolio,
)

OWNER_ID = UUID("7c945b56-2b06-4bd2-ae41-f51713585e1e")
ACCOUNT_ID = UUID("f7c7731d-a704-478e-bd4c-0244bec32e87")
SNAPSHOT_ID = UUID("69585b30-7188-4610-a6fd-4bb012769880")


def _rows(*, snapshot_total: Decimal = Decimal("10000000")) -> list[tuple]:
    return [
        (
            ACCOUNT_ID,
            "dc",
            "회사 DC",
            "mock",
            "synthetic",
            SNAPSHOT_ID,
            date(2026, 7, 16),
            None,
            snapshot_total,
            UUID("eea0717b-129d-448a-845b-ccf1845e0122"),
            None,
            "KODEX 미국S&P500",
            "379800",
            "global_equity",
            Decimal("6000000"),
            "general_risky",
            None,
        ),
        (
            ACCOUNT_ID,
            "dc",
            "회사 DC",
            "mock",
            "synthetic",
            SNAPSHOT_ID,
            date(2026, 7, 16),
            None,
            snapshot_total,
            UUID("65269d74-a8b8-456d-89a1-96b6714fe491"),
            None,
            "원리금보장 모형",
            None,
            "deposit",
            Decimal("4000000"),
            "capital_preservation",
            None,
        ),
    ]


class FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        self.query = query
        self.params = params

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakePool:
    def __init__(self, cursor: FakeCursor) -> None:
        self._connection = FakeConnection(cursor)

    @contextmanager
    def connection(self):
        yield self._connection


def test_repository_uses_owned_real_accounts_then_demo_mock_fallback() -> None:
    cursor = FakeCursor(_rows())
    repository = PensionAccountRepository(
        "postgresql://test",
        pool=FakePool(cursor),
    )

    portfolio = repository.get(OWNER_ID)

    assert cursor.params == (OWNER_ID,)
    normalized_query = " ".join(cursor.query.lower().split())
    assert "account.owner_id = context.owner_id" in normalized_query
    assert "demo.auth_user_id = context.owner_id" in normalized_query
    assert "not exists (select 1 from real_accounts)" in normalized_query
    assert "order by current_snapshot.as_of_date desc" in normalized_query

    assert portfolio.data_boundary == "mock"
    assert portfolio.accounts[0].market_value_krw == Decimal("10000000")
    assert portfolio.accounts[0].holdings[0].etf_isu_code == "379800"
    engine_input = portfolio.to_aggregation_input()
    assert engine_input.accounts[0].account_type.value == "dc"
    assert engine_input.accounts[0].holdings[0].asset_class.value == "global_equity"


def test_repository_rejects_snapshot_and_holding_total_mismatch() -> None:
    with pytest.raises(PensionAccountDataError, match="holding total"):
        PensionAccountRepository._portfolio_from_rows(
            OWNER_ID,
            _rows(snapshot_total=Decimal("9999999")),
        )


class FakeRepository:
    def get(self, owner_id: UUID) -> UserPensionPortfolio:
        return PensionAccountRepository._portfolio_from_rows(owner_id, _rows())


def test_authenticated_pension_accounts_api_returns_engine_ready_holdings() -> None:
    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_pension_account_repository] = FakeRepository
    try:
        with TestClient(app) as client:
            response = client.get(
                "/me/pension-accounts",
                headers={"Authorization": "Bearer test"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["owner_id"] == str(OWNER_ID)
    assert payload["data_boundary"] == "mock"
    assert payload["accounts"][0]["holdings"][0]["etf_isu_code"] == "379800"
    assert payload["accounts"][0]["contributed_principal_krw"] is None


def test_pension_accounts_route_is_registered() -> None:
    assert "/me/pension-accounts" in {route.path for route in app.routes}
