from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID

import pytest

from backend.app.api import deps
from backend.app.engine import (
    AccountType,
    HoldingInput,
    PortfolioInput,
    RiskTreatment,
    evaluate_risk_cap,
)
from backend.app.engine import audit as module
from backend.app.engine.audit import EngineAuditRepository
from backend.app.settings import Settings

DATABASE_URL = "postgresql://test"
RUN_ID = UUID("22222222-2222-2222-2222-222222222222")


class _FakeCursor:
    def __init__(self) -> None:
        self._rows = [
            (1,),
            (RUN_ID,),
            (
                2,
                3,
                "연금_기초.md §4-2",
                {
                    "max_percent": "70",
                    "included_treatments": ["general_risky"],
                },
            ),
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None) -> None:
        pass

    def executemany(self, query, params) -> None:
        pass

    def fetchone(self):
        return self._rows.pop(0)


class _FakeConnection:
    def __init__(self) -> None:
        self._cursor = _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self) -> None:
        self.connection_calls = 0

    @contextmanager
    def connection(self):
        self.connection_calls += 1
        yield _FakeConnection()


def _evaluation():
    return evaluate_risk_cap(
        PortfolioInput(
            account_type=AccountType.DC,
            holdings=[
                HoldingInput(
                    holding_id="equity",
                    amount_krw=Decimal("700000"),
                    risk_treatment=RiskTreatment.GENERAL_RISKY,
                ),
                HoldingInput(
                    holding_id="deposit",
                    amount_krw=Decimal("300000"),
                    risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
                ),
            ],
        )
    )


def test_audit_repository_dependency_uses_shared_pool(monkeypatch) -> None:
    pool = _FakePool()
    monkeypatch.setattr(deps, "get_database_pool", lambda database_url: pool)
    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail(
            "psycopg.connect must not be called when a pool exists"
        ),
    )
    repository = deps.get_engine_audit_repository(
        Settings(_env_file=None, database_url=DATABASE_URL)
    )

    assert repository.record(_evaluation()) == RUN_ID
    assert pool.connection_calls == 1


def test_audit_repository_falls_back_to_direct_connection(monkeypatch) -> None:
    connection_calls = []

    def connect(database_url):
        connection_calls.append(database_url)
        return _FakeConnection()

    monkeypatch.setattr(module.psycopg, "connect", connect)

    assert EngineAuditRepository(DATABASE_URL).record(_evaluation()) == RUN_ID
    assert connection_calls == [DATABASE_URL]
