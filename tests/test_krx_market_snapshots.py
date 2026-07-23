import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.api.deps import (
    get_etf_distribution_event_repository,
    get_etf_market_repository,
)
from backend.app.etf_distribution_event_repository import EtfDistributionEventDataset
from backend.app.etf_market_repository import (
    EtfMarketObservation,
    EtfMarketRepository,
    EtfMarketSnapshot,
)
from backend.app.ingestion.krx_client import (
    KRX_ETF_REQUIRED_FIELDS,
    parse_krx_etf_payload,
)
from backend.app.ingestion.krx_market_repository import (
    load_krx_etf_market_snapshot,
    normalize_krx_etf_market_rows,
)
from backend.app.main import app

BASE_DATE = date(2026, 7, 16)
RUN_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _row(**overrides: str) -> dict[str, str]:
    row = {field: "1" for field in KRX_ETF_REQUIRED_FIELDS}
    row.update(
        {
            "BAS_DD": "20260716",
            "ISU_CD": "069500",
            "ISU_NM": "KODEX 200",
            "TDD_CLSPRC": "10,000",
            "TDD_OPNPRC": "0",
            "ACC_TRDVOL": "1,234,567",
            "ACC_TRDVAL": "12,345,670,000",
            "INVSTASST_NETASST_TOTAMT": "9,000,000,000,000",
            "IDX_IND_NM": "코스피 200",
        }
    )
    row.update(overrides)
    return row


def _observation(observed_on: date = BASE_DATE) -> EtfMarketObservation:
    return EtfMarketObservation(
        base_date=observed_on,
        isu_code="069500",
        isu_name="KODEX 200",
        close_price_krw=Decimal("10000"),
        fluctuation_rate_percent=Decimal("1.25"),
        nav_krw=Decimal("10010.5"),
        trading_volume=1_234_567,
        trading_value_krw=Decimal("12345670000"),
        market_cap_krw=Decimal("9000000000000"),
        net_assets_krw=Decimal("9000000000000"),
        benchmark_name="코스피 200",
    )


def test_normalizes_all_usable_krx_rows_and_skips_holiday_blanks() -> None:
    response = parse_krx_etf_payload(
        {
            "OutBlock_1": [
                _row(),
                _row(
                    ISU_CD="0184E0",
                    ISU_NM="KODEX 반도체",
                    TDD_CLSPRC="",
                ),
            ]
        },
        base_date=BASE_DATE,
    )

    rows = normalize_krx_etf_market_rows(response)

    assert len(rows) == 1
    assert rows[0]["isu_code"] == "069500"
    assert rows[0]["trading_volume"] == 1_234_567
    assert rows[0]["trading_value_krw"] == Decimal("12345670000")
    assert rows[0]["open_price_krw"] is None


def test_loads_snapshot_with_source_and_ingestion_run(tmp_path: Path) -> None:
    raw_path = tmp_path / "20260716.json"
    raw_path.write_text(
        json.dumps({"OutBlock_1": [_row()]}),
        encoding="utf-8",
    )
    cursor = _WriteCursor()

    summary = load_krx_etf_market_snapshot(
        "postgresql://unused",
        raw_path=raw_path,
        connection_factory=lambda _url: _Connection(cursor),
    )

    assert summary.base_date == BASE_DATE
    assert summary.source_rows == 1
    assert summary.normalized_rows == 1
    assert summary.skipped_rows == 0
    assert summary.run_id == RUN_ID
    assert len(summary.raw_sha256) == 64
    assert len(cursor.executemany_calls) == 1
    insert_sql, params = cursor.executemany_calls[0]
    assert "etf_daily_market_snapshots" in insert_sql
    assert params[0]["trading_volume"] == 1_234_567
    assert params[0]["ingestion_run_id"] == RUN_ID
    assert "status = 'succeeded'" in cursor.executed[-1][0]


def test_repository_reads_latest_snapshot_and_volume_history() -> None:
    snapshot_rows = [
        (
            BASE_DATE,
            "069500",
            "KODEX 200",
            Decimal("10000"),
            Decimal("1.25"),
            Decimal("10010.5"),
            1_234_567,
            Decimal("12345670000"),
            Decimal("9000000000000"),
            Decimal("9000000000000"),
            "코스피 200",
            1,
        )
    ]
    snapshot_cursor = _ReadCursor(target_date=BASE_DATE, rows=snapshot_rows)
    repository = EtfMarketRepository(
        "postgresql://unused",
        connection_factory=lambda _url: _Connection(snapshot_cursor),
    )

    snapshot = repository.list_snapshot(
        as_of=None,
        sort_by="trading_volume",
        order="desc",
        limit=2000,
    )

    assert snapshot.as_of == BASE_DATE
    assert snapshot.total_count == 1
    assert snapshot.results[0].trading_volume == 1_234_567
    assert "order by trading_volume desc" in snapshot_cursor.executed[1][0]

    history_rows = [
        (*snapshot_rows[0][:11],),
        (
            date(2026, 7, 15),
            *snapshot_rows[0][1:11],
        ),
    ]
    history_cursor = _ReadCursor(target_date=None, rows=history_rows)
    history_repository = EtfMarketRepository(
        "postgresql://unused",
        connection_factory=lambda _url: _Connection(history_cursor),
    )
    history = history_repository.volume_history(
        "069500",
        from_date=None,
        to_date=None,
        limit=253,
    )

    assert [item.base_date for item in history] == [
        date(2026, 7, 15),
        BASE_DATE,
    ]


class FakeEtfMarketRepository:
    def list_snapshot(self, **_: object) -> EtfMarketSnapshot:
        return EtfMarketSnapshot(
            as_of=BASE_DATE,
            total_count=1,
            results=[_observation()],
        )

    def volume_history(self, _isu_code: str, **_: object) -> list[EtfMarketObservation]:
        return [_observation(date(2026, 7, 15)), _observation()]


class FakeDistributionEventRepository:
    def latest_for_etf(self, isu_code: str) -> EtfDistributionEventDataset:
        assert isu_code == "069500"
        return EtfDistributionEventDataset(
            as_of=BASE_DATE,
            events=[
                {
                    "event_type": "cash_distribution",
                    "effective_date": "2026-07-15",
                    "record_date": None,
                    "payment_date": "2026-07-18",
                    "cash_per_share_krw": "125",
                    "ratio": None,
                    "timing_basis": "kind",
                    "confidence": "high",
                    "status": "confirmed_cash_flow",
                    "source_evidence": [
                        {
                            "source_type": "kind_cash_distribution",
                            "source_url": "https://example.test/kind/069500",
                        }
                    ],
                }
            ],
        )


def test_etf_market_api_exposes_official_volume_with_source_boundary() -> None:
    app.dependency_overrides[get_etf_market_repository] = FakeEtfMarketRepository
    try:
        with TestClient(app) as client:
            snapshot = client.get("/market/etfs?sort=trading_volume&order=desc")
            history = client.get("/market/etfs/069500/volume-history")
    finally:
        app.dependency_overrides.clear()

    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["data_boundary"] == "official_market_data"
    assert payload["as_of"] == "2026-07-16"
    assert payload["results"][0]["trading_volume"] == 1_234_567
    assert payload["results"][0]["trading_value_krw"] == "12345670000"
    assert history.status_code == 200
    assert history.json()["from_date"] == "2026-07-15"


def test_etf_volume_history_hides_repository_key_error(caplog) -> None:
    class MissingRepository:
        def volume_history(
            self, _isu_code: str, **_: object
        ) -> list[EtfMarketObservation]:
            raise KeyError("internal repository detail")

    app.dependency_overrides[get_etf_market_repository] = MissingRepository
    try:
        with TestClient(app) as client:
            response = client.get("/market/etfs/069500/volume-history")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "Requested ETF volume history was not found",
        }
    }
    assert "etf_volume_history_not_found isu_code=069500" in caplog.messages


def test_etf_distribution_events_api_exposes_official_event_source_chips() -> None:
    app.dependency_overrides[
        get_etf_distribution_event_repository
    ] = FakeDistributionEventRepository
    try:
        with TestClient(app) as client:
            response = client.get("/market/etfs/069500/distribution-events")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_boundary"] == "official_distribution_event_data"
    assert payload["as_of"] == "2026-07-16"
    assert payload["results"][0]["cash_per_share_krw"] == "125"
    assert payload["results"][0]["source_chips"] == [
        {
            "source_type": "kind_cash_distribution",
            "reference": "https://example.test/kind/069500",
        }
    ]


class _Connection:
    def __init__(self, cursor: object) -> None:
        self._cursor = cursor

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> object:
        return self._cursor


class _WriteCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []
        self.executemany_calls: list[tuple[str, list[dict[str, object]]]] = []
        self._fetches = [(7,), (RUN_ID,)]
        self.rowcount = 1

    def __enter__(self) -> "_WriteCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    def executemany(self, sql: str, params: list[dict[str, object]]) -> None:
        self.executemany_calls.append((sql, list(params)))

    def fetchone(self) -> tuple[object, ...]:
        return self._fetches.pop(0)


class _ReadCursor:
    def __init__(
        self,
        *,
        target_date: date | None,
        rows: list[tuple[object, ...]],
    ) -> None:
        self.target_date = target_date
        self.rows = rows
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "_ReadCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> tuple[date | None]:
        return (self.target_date,)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows
