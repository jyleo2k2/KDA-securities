"""Persist normalized KRX ETF daily market snapshots with ingestion evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .krx_client import (
    KRX_ETF_DAILY_ENDPOINT,
    KrxEtfDailyResponse,
    parse_krx_etf_payload,
)

KRX_ETF_MARKET_SOURCE_CODE = "krx_etf_bydd_trd"
DEFAULT_KRX_RAW_ROOT = Path("data/raw/krx")


class KrxEtfMarketLoadError(RuntimeError):
    """A safe-to-report KRX market snapshot load failure."""


@dataclass(frozen=True, slots=True)
class KrxEtfMarketLoadSummary:
    base_date: date
    source_rows: int
    normalized_rows: int
    skipped_rows: int
    run_id: UUID
    raw_sha256: str


@dataclass(frozen=True, slots=True)
class _RunHandle:
    run_id: UUID
    source_id: int


def _decimal(
    value: object,
    *,
    field: str,
    required: bool = False,
    positive: bool = False,
    nonnegative: bool = False,
) -> Decimal | None:
    if value in {None, "", "-"}:
        if required:
            raise KrxEtfMarketLoadError(f"KRX {field} is required")
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise KrxEtfMarketLoadError(f"KRX {field} is invalid") from exc
    if not parsed.is_finite():
        raise KrxEtfMarketLoadError(f"KRX {field} is not finite")
    if positive and parsed <= 0:
        if required:
            raise KrxEtfMarketLoadError(f"KRX {field} must be positive")
        return None
    if nonnegative and parsed < 0:
        raise KrxEtfMarketLoadError(f"KRX {field} must be nonnegative")
    return parsed


def _integer(
    value: object,
    *,
    field: str,
    required: bool = False,
    positive: bool = False,
    nonnegative: bool = False,
) -> int | None:
    parsed = _decimal(
        value,
        field=field,
        required=required,
        positive=positive,
        nonnegative=nonnegative,
    )
    if parsed is None:
        return None
    if parsed != parsed.to_integral_value():
        raise KrxEtfMarketLoadError(f"KRX {field} must be an integer")
    return int(parsed)


def normalize_krx_etf_market_rows(
    response: KrxEtfDailyResponse,
) -> list[dict[str, Any]]:
    """Normalize every ETF with a usable close on the requested trading day."""

    rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for raw in response.records:
        if raw["TDD_CLSPRC"] in {"", "-"}:
            continue
        code = raw["ISU_CD"].strip()
        if code in seen_codes:
            raise KrxEtfMarketLoadError(f"duplicate KRX ETF code: {code}")
        if len(code) != 6 or not all(
            character.isdigit() or "A" <= character <= "Z" for character in code
        ):
            raise KrxEtfMarketLoadError(f"invalid KRX ETF code: {code}")
        name = raw["ISU_NM"].strip()
        if not name:
            raise KrxEtfMarketLoadError(f"KRX ETF name is missing: {code}")
        seen_codes.add(code)
        rows.append(
            {
                "base_date": response.base_date,
                "isu_code": code,
                "isu_name": name,
                "close_price_krw": _decimal(
                    raw["TDD_CLSPRC"],
                    field="TDD_CLSPRC",
                    required=True,
                    positive=True,
                ),
                "previous_day_change_krw": _decimal(
                    raw["CMPPREVDD_PRC"], field="CMPPREVDD_PRC"
                ),
                "fluctuation_rate_percent": _decimal(raw["FLUC_RT"], field="FLUC_RT"),
                "nav_krw": _decimal(raw["NAV"], field="NAV", positive=True),
                "open_price_krw": _decimal(
                    raw["TDD_OPNPRC"], field="TDD_OPNPRC", positive=True
                ),
                "high_price_krw": _decimal(
                    raw["TDD_HGPRC"], field="TDD_HGPRC", positive=True
                ),
                "low_price_krw": _decimal(
                    raw["TDD_LWPRC"], field="TDD_LWPRC", positive=True
                ),
                "trading_volume": _integer(
                    raw["ACC_TRDVOL"],
                    field="ACC_TRDVOL",
                    required=True,
                    nonnegative=True,
                ),
                "trading_value_krw": _decimal(
                    raw["ACC_TRDVAL"],
                    field="ACC_TRDVAL",
                    required=True,
                    nonnegative=True,
                ),
                "market_cap_krw": _decimal(
                    raw["MKTCAP"], field="MKTCAP", positive=True
                ),
                "net_assets_krw": _decimal(
                    raw["INVSTASST_NETASST_TOTAMT"],
                    field="INVSTASST_NETASST_TOTAMT",
                    positive=True,
                ),
                "listed_shares": _integer(
                    raw["LIST_SHRS"], field="LIST_SHRS", positive=True
                ),
                "benchmark_name": raw["IDX_IND_NM"].strip() or None,
                "benchmark_index": _decimal(
                    raw["OBJ_STKPRC_IDX"],
                    field="OBJ_STKPRC_IDX",
                    positive=True,
                ),
            }
        )
    return rows


def _load_raw(path: Path) -> tuple[KrxEtfDailyResponse, bytes]:
    raw_content = path.read_bytes()
    try:
        payload = json.loads(raw_content)
        base_date = date.fromisoformat(
            f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise KrxEtfMarketLoadError(f"invalid KRX raw file: {path}") from exc
    return (
        parse_krx_etf_payload(
            payload,
            base_date=base_date,
            raw_content=raw_content,
        ),
        raw_content,
    )


def latest_usable_krx_etf_raw_path(
    raw_root: Path = DEFAULT_KRX_RAW_ROOT,
) -> Path:
    candidates = sorted((raw_root / "etf_bydd_trd").glob("*/*/*.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no KRX ETF raw files under {raw_root}")
    for path in candidates:
        response, _ = _load_raw(path)
        if normalize_krx_etf_market_rows(response):
            return path
    raise KrxEtfMarketLoadError("KRX raw history has no usable ETF trading day")


class KrxEtfMarketSnapshotWriter:
    def __init__(
        self,
        database_url: str,
        *,
        connection_factory: Callable[[str], Any] = psycopg.connect,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._connection_factory = connection_factory

    def start_run(
        self,
        *,
        base_date: date,
        source_rows: int,
        raw_path: Path,
        raw_sha256: str,
    ) -> _RunHandle:
        with (
            self._connection_factory(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                    insert into public.data_sources (
                        code, name, source_type, authority, base_url,
                        default_source_unit, metadata
                    )
                    values (
                        %s, %s, 'market_api', '한국거래소', %s,
                        'krw_and_shares', %s
                    )
                    on conflict (code) do update set
                        name = excluded.name,
                        base_url = excluded.base_url,
                        default_source_unit = excluded.default_source_unit,
                        metadata = data_sources.metadata || excluded.metadata,
                        is_active = true,
                        updated_at = now()
                    returning id
                    """,
                (
                    KRX_ETF_MARKET_SOURCE_CODE,
                    "KRX ETF 일별매매정보",
                    KRX_ETF_DAILY_ENDPOINT,
                    Jsonb(
                        {
                            "data_boundary": "official_market_data",
                            "is_mock": False,
                        }
                    ),
                ),
            )
            source = cursor.fetchone()
            if source is None:
                raise KrxEtfMarketLoadError("failed to resolve KRX data source")
            source_id = int(source[0])
            cursor.execute(
                """
                    insert into public.ingestion_runs (
                        source_id, endpoint, requested_params, status,
                        source_record_count, metadata
                    )
                    values (%s, %s, %s, 'running', %s, %s)
                    returning id
                    """,
                (
                    source_id,
                    KRX_ETF_DAILY_ENDPOINT,
                    Jsonb({"basDd": base_date.strftime("%Y%m%d")}),
                    source_rows,
                    Jsonb(
                        {
                            "data_boundary": "official_market_data",
                            "is_mock": False,
                            "raw_path": raw_path.as_posix(),
                            "raw_sha256": raw_sha256,
                        }
                    ),
                ),
            )
            run = cursor.fetchone()
            if run is None:
                raise KrxEtfMarketLoadError("failed to create KRX ingestion run")
            return _RunHandle(run_id=run[0], source_id=source_id)

    def complete_run(
        self,
        *,
        handle: _RunHandle,
        rows: list[dict[str, Any]],
    ) -> None:
        params = [
            {**row, "source_id": handle.source_id, "ingestion_run_id": handle.run_id}
            for row in rows
        ]
        with (
            self._connection_factory(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.executemany(
                """
                    insert into public.etf_daily_market_snapshots (
                        base_date, isu_code, isu_name, close_price_krw,
                        previous_day_change_krw, fluctuation_rate_percent, nav_krw,
                        open_price_krw, high_price_krw, low_price_krw,
                        trading_volume, trading_value_krw, market_cap_krw,
                        net_assets_krw, listed_shares, benchmark_name,
                        benchmark_index, source_id, ingestion_run_id
                    )
                    values (
                        %(base_date)s, %(isu_code)s, %(isu_name)s,
                        %(close_price_krw)s, %(previous_day_change_krw)s,
                        %(fluctuation_rate_percent)s, %(nav_krw)s,
                        %(open_price_krw)s, %(high_price_krw)s, %(low_price_krw)s,
                        %(trading_volume)s, %(trading_value_krw)s,
                        %(market_cap_krw)s, %(net_assets_krw)s, %(listed_shares)s,
                        %(benchmark_name)s, %(benchmark_index)s,
                        %(source_id)s, %(ingestion_run_id)s
                    )
                    on conflict (base_date, isu_code) do update set
                        isu_name = excluded.isu_name,
                        close_price_krw = excluded.close_price_krw,
                        previous_day_change_krw = excluded.previous_day_change_krw,
                        fluctuation_rate_percent = excluded.fluctuation_rate_percent,
                        nav_krw = excluded.nav_krw,
                        open_price_krw = excluded.open_price_krw,
                        high_price_krw = excluded.high_price_krw,
                        low_price_krw = excluded.low_price_krw,
                        trading_volume = excluded.trading_volume,
                        trading_value_krw = excluded.trading_value_krw,
                        market_cap_krw = excluded.market_cap_krw,
                        net_assets_krw = excluded.net_assets_krw,
                        listed_shares = excluded.listed_shares,
                        benchmark_name = excluded.benchmark_name,
                        benchmark_index = excluded.benchmark_index,
                        source_id = excluded.source_id,
                        ingestion_run_id = excluded.ingestion_run_id,
                        observed_at = now()
                    """,
                params,
            )
            cursor.execute(
                """
                    update public.ingestion_runs
                    set status = 'succeeded',
                        completed_at = now(),
                        normalized_record_count = %s,
                        upserted_record_count = %s,
                        metadata = metadata || %s
                    where id = %s and status = 'running'
                    """,
                (
                    len(rows),
                    len(rows),
                    Jsonb({"outcome": "succeeded"}),
                    handle.run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KrxEtfMarketLoadError("failed to complete KRX ingestion run")

    def fail_run(self, handle: _RunHandle, error: Exception) -> None:
        safe_message = f"{type(error).__name__}:market_snapshot_load_failed"
        with (
            self._connection_factory(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                    update public.ingestion_runs
                    set status = 'failed',
                        completed_at = now(),
                        error_message = %s,
                        metadata = metadata || %s
                    where id = %s and status = 'running'
                    """,
                (
                    safe_message,
                    Jsonb({"outcome": "failed"}),
                    handle.run_id,
                ),
            )


def load_krx_etf_market_snapshot(
    database_url: str,
    *,
    raw_path: Path,
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> KrxEtfMarketLoadSummary:
    response, raw_content = _load_raw(raw_path)
    rows = normalize_krx_etf_market_rows(response)
    if not rows:
        raise KrxEtfMarketLoadError("KRX raw file has no usable ETF rows")
    digest = hashlib.sha256(raw_content).hexdigest()
    writer = KrxEtfMarketSnapshotWriter(
        database_url,
        connection_factory=connection_factory,
    )
    handle = writer.start_run(
        base_date=response.base_date,
        source_rows=len(response.records),
        raw_path=raw_path,
        raw_sha256=digest,
    )
    try:
        writer.complete_run(handle=handle, rows=rows)
    except Exception as exc:
        writer.fail_run(handle, exc)
        raise
    return KrxEtfMarketLoadSummary(
        base_date=response.base_date,
        source_rows=len(response.records),
        normalized_rows=len(rows),
        skipped_rows=len(response.records) - len(rows),
        run_id=handle.run_id,
        raw_sha256=digest,
    )
