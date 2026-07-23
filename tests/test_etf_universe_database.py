import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app import etf_universe_database
from backend.app.api import deps
from backend.app.engine.models import AccountType
from backend.app.etf_universe_database import (
    PortfolioUniverseLoadError,
    PostgresPortfolioUniverseRepository,
    load_portfolio_universe,
)

_AS_OF = "2026-07-16"


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_adjusted_price(
    root: Path, as_of: str, isu_code: str, observations: list[tuple[str, str]]
) -> None:
    _write(
        root / as_of / f"{isu_code}.json",
        {
            "price_policy": {"FID_ORG_ADJ_PRC": "0"},
            "observations": [
                {"date": observed_on, "adjusted_close": close}
                for observed_on, close in observations
            ],
        },
    )


def _build_universe_fixture(
    tmp_path: Path,
    *,
    as_of_by_account: dict[str, str] | None = None,
) -> tuple[Path, Path, Path, Path]:
    return_root = tmp_path / "returns"
    krx_root = tmp_path / "krx"
    adjusted_price_root = tmp_path / "adjusted_prices"
    event_root = tmp_path / "events"

    as_of_by_account = as_of_by_account or {
        "dc": _AS_OF,
        "irp": _AS_OF,
        "pension_savings": _AS_OF,
    }

    # "069500"은 dc·irp 둘 다에서 적격(이력 중복 병합 검증용).
    # "091160"은 pension_savings에만 있는 별도 종목.
    account_codes = {
        "dc": ["069500"],
        "irp": ["069500"],
        "pension_savings": ["091160"],
    }

    for account, isu_codes in account_codes.items():
        as_of = as_of_by_account[account]
        _write(
            return_root / f"{account}_etf_cost_return_{as_of}.json",
            {
                "as_of": as_of,
                "products": [
                    {"isu_code": code, "total_expense_ratio_percent": "0.15"}
                    for code in isu_codes
                ],
            },
        )
        for code in isu_codes:
            _write_adjusted_price(
                adjusted_price_root,
                as_of,
                code,
                [("2026-07-14", "10000"), ("2026-07-15", "10100")],
            )

    return return_root, krx_root, adjusted_price_root, event_root


def test_loads_universe_and_merges_shared_history(tmp_path: Path) -> None:
    return_root, krx_root, adjusted_price_root, event_root = _build_universe_fixture(
        tmp_path
    )
    fake = _FakeConnection()

    def _fake_connect(_url: str) -> "_FakeConnection":
        return fake

    original_connect = etf_universe_database.psycopg.connect
    etf_universe_database.psycopg.connect = _fake_connect  # type: ignore[method-assign]
    try:
        summary = load_portfolio_universe(
            "postgresql://unused",
            return_root=return_root,
            krx_root=krx_root,
            adjusted_price_root=adjusted_price_root,
            event_root=event_root,
        )
    finally:
        etf_universe_database.psycopg.connect = original_connect  # type: ignore[method-assign]

    assert summary.as_of.isoformat() == _AS_OF
    assert summary.version_id == 42
    # dc(1) + irp(1) + pension_savings(1) = 3 product rows
    # (계좌별로 보존, 중복 제거 없음)
    assert summary.product_rows == 3
    assert summary.account_product_counts == {
        "dc": 1,
        "irp": 1,
        "pension_savings": 1,
    }
    # "069500" 이력은 dc·irp 모두에서 나오지만 종목당 1행으로 합쳐진다(2관측).
    # "091160"은 별도 2관측 -> 총 4행.
    assert summary.history_rows == 4
    assert len(summary.source_sha256) == 64
    int(summary.source_sha256, 16)  # hex여야 한다

    product_insert = fake.cursor_obj.executemany_calls[0]
    assert "etf_universe_products" in product_insert[0]
    assert len(product_insert[1]) == 3

    history_insert = fake.cursor_obj.executemany_calls[1]
    assert "etf_return_histories" in history_insert[0]
    assert len(history_insert[1]) == 4
    inserted_keys = {(row[1], row[2]) for row in history_insert[1]}
    assert len(inserted_keys) == 4  # 중복 (isu_code, observed_on) 없음

    ready_update = fake.cursor_obj.executed[-1]
    assert "status = 'ready'" in ready_update[0]
    assert ready_update[1] == (3, 4, 42)


def test_rejects_mismatched_as_of_across_accounts(tmp_path: Path) -> None:
    return_root, krx_root, adjusted_price_root, event_root = _build_universe_fixture(
        tmp_path,
        as_of_by_account={
            "dc": _AS_OF,
            "irp": "2026-07-10",
            "pension_savings": _AS_OF,
        },
    )

    with pytest.raises(PortfolioUniverseLoadError, match="do not share one as_of"):
        load_portfolio_universe(
            "postgresql://unused",
            return_root=return_root,
            krx_root=krx_root,
            adjusted_price_root=adjusted_price_root,
            event_root=event_root,
        )


def test_source_hash_covers_adjusted_prices_and_event_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    return_root, krx_root, adjusted_price_root, event_root = _build_universe_fixture(
        tmp_path
    )
    event_path = event_root / f"etf_corporate_events_{_AS_OF}.json"
    _write(event_path, {"events": []})
    monkeypatch.setattr(
        etf_universe_database.psycopg,
        "connect",
        lambda _url: _FakeConnection(),
    )

    original = load_portfolio_universe(
        "postgresql://unused",
        return_root=return_root,
        krx_root=krx_root,
        adjusted_price_root=adjusted_price_root,
        event_root=event_root,
    )

    adjusted_path = adjusted_price_root / _AS_OF / "069500.json"
    adjusted = json.loads(adjusted_path.read_text(encoding="utf-8"))
    adjusted["observations"][0]["adjusted_close"] = "10001"
    _write(adjusted_path, adjusted)
    adjusted_changed = load_portfolio_universe(
        "postgresql://unused",
        return_root=return_root,
        krx_root=krx_root,
        adjusted_price_root=adjusted_price_root,
        event_root=event_root,
    )
    assert adjusted_changed.source_sha256 != original.source_sha256

    _write(event_path, {"events": [], "revision": 2})
    event_changed = load_portfolio_universe(
        "postgresql://unused",
        return_root=return_root,
        krx_root=krx_root,
        adjusted_price_root=adjusted_price_root,
        event_root=event_root,
    )
    assert event_changed.source_sha256 != adjusted_changed.source_sha256


def test_reads_latest_ready_universe_for_one_account() -> None:
    connection = _ReadConnection(
        version_row=(7, date(2026, 7, 16)),
        product_rows=[
            (
                "069500",
                {
                    "isu_code": "069500",
                    "isu_name": "KODEX 200",
                    "total_expense_ratio_percent": "0.15",
                },
            )
        ],
        history_rows=[
            (
                "069500",
                date(2026, 7, 14),
                Decimal("100"),
                "kis_adjusted_close",
            ),
            (
                "069500",
                date(2026, 7, 15),
                Decimal("101"),
                "kis_adjusted_close",
            ),
        ],
    )

    repository = PostgresPortfolioUniverseRepository(
        "postgresql://unused",
        connection_factory=lambda _url: connection,
    ).latest(AccountType.DC)

    assert repository.account_type is AccountType.DC
    assert repository.as_of == date(2026, 7, 16)
    assert repository.products[0]["isu_name"] == "KODEX 200"
    assert repository.histories == {
        "069500": {
            date(2026, 7, 14): Decimal("100"),
            date(2026, 7, 15): Decimal("101"),
        }
    }
    assert repository.history_sources == {"069500": "kis_adjusted_close"}
    assert repository.source_path.as_posix().endswith("etf_dataset_versions/7")
    assert connection.cursor_obj.executed[1][1] == (7, "dc")
    assert connection.cursor_obj.executed[2][1] == (7, "dc", 253)


def test_reads_theme_products_without_return_histories() -> None:
    connection = _ReadConnection(
        version_row=(7, date(2026, 7, 16)),
        product_rows=[
            (
                "069500",
                {
                    "isu_code": "069500",
                    "isu_name": "KODEX 200",
                },
            ),
            (
                "229200",
                {
                    "isu_code": "229200",
                    "isu_name": "KODEX 코스닥150",
                },
            ),
        ],
        history_rows=[],
    )

    universe = PostgresPortfolioUniverseRepository(
        "postgresql://unused",
        connection_factory=lambda _url: connection,
    ).latest_theme_products(("229200", "069500", "069500"))

    assert universe.as_of == date(2026, 7, 16)
    assert [product["isu_code"] for product in universe.products] == [
        "069500",
        "229200",
    ]
    assert len(connection.cursor_obj.executed) == 2
    product_sql, product_params = connection.cursor_obj.executed[1]
    assert "etf_return_histories" not in product_sql
    assert "distinct on (isu_code)" in product_sql
    assert "when 'dc' then 1" in product_sql
    assert product_params == (
        7,
        ["069500", "229200"],
        ["069500", "229200"],
    )


def test_rejects_database_without_ready_universe() -> None:
    connection = _ReadConnection(
        version_row=None,
        product_rows=[],
        history_rows=[],
    )

    with pytest.raises(PortfolioUniverseLoadError, match="ready ETF dataset"):
        PostgresPortfolioUniverseRepository(
            "postgresql://unused",
            connection_factory=lambda _url: connection,
        ).latest(AccountType.IRP)


def test_api_repository_uses_database_when_url_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = object()
    pool = object()

    class _Reader:
        def __init__(self, database_url: str, *, pool: object) -> None:
            assert database_url == "postgresql://configured"
            assert pool is globals_pool

        def latest(self, account_type: AccountType) -> object:
            assert account_type is AccountType.DC
            return expected

    globals_pool = pool
    deps.get_portfolio_universe_repository.cache_clear()
    observed_max_size: list[int] = []

    def fake_get_database_pool(_url: str, *, max_size: int) -> object:
        observed_max_size.append(max_size)
        return pool

    monkeypatch.setattr(
        deps,
        "get_database_pool",
        fake_get_database_pool,
    )
    monkeypatch.setattr(deps, "PostgresPortfolioUniverseRepository", _Reader)
    monkeypatch.setattr(
        deps.PortfolioUniverseRepository,
        "from_latest_cache",
        lambda _account: pytest.fail("configured DB must not fall back to cache"),
    )
    try:
        actual = deps.get_portfolio_universe_repository(
            AccountType.DC,
            "postgresql://configured",
        )
    finally:
        deps.get_portfolio_universe_repository.cache_clear()

    assert actual is expected
    assert observed_max_size == [5]


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.executed.append((sql, params))

    def executemany(
        self, sql: str, seq: list[tuple[object, ...]]
    ) -> None:
        self.executemany_calls.append((sql, list(seq)))

    def fetchone(self) -> tuple[int]:
        return (42,)


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


class _ReadCursor:
    def __init__(
        self,
        *,
        version_row: tuple[int, date] | None,
        product_rows: list[tuple[str, dict[str, object]]],
        history_rows: list[tuple[str, date, Decimal, str]],
    ) -> None:
        self.version_row = version_row
        self.product_rows = product_rows
        self.history_rows = history_rows
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []

    def __enter__(self) -> "_ReadCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> tuple[int, date] | None:
        return self.version_row

    def fetchall(self) -> list[tuple[object, ...]]:
        if len(self.executed) == 2:
            return list(self.product_rows)
        if len(self.executed) == 3:
            return list(self.history_rows)
        raise AssertionError("unexpected fetchall call")


class _ReadConnection:
    def __init__(
        self,
        *,
        version_row: tuple[int, date] | None,
        product_rows: list[tuple[str, dict[str, object]]],
        history_rows: list[tuple[str, date, Decimal, str]],
    ) -> None:
        self.cursor_obj = _ReadCursor(
            version_row=version_row,
            product_rows=product_rows,
            history_rows=history_rows,
        )

    def __enter__(self) -> "_ReadConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _ReadCursor:
        return self.cursor_obj
