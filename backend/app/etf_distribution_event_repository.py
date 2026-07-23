"""Versioned official ETF distribution-event storage boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool


class EtfDistributionEventLoadError(RuntimeError):
    pass


class EtfDistributionEventUnavailable(EtfDistributionEventLoadError):
    pass


@dataclass(frozen=True, slots=True)
class EtfDistributionEventLoadSummary:
    as_of: date
    version_id: int
    event_rows: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class EtfDistributionEventDataset:
    as_of: date
    events: list[dict[str, Any]]


class PostgresEtfDistributionEventRepository:
    """Read the latest ready official event master; never calculates events."""

    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
        connection_factory: Callable[[str], Any] = psycopg.connect,
    ) -> None:
        self._database_url = database_url
        self._pool = pool
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._pool is not None:
            with self._pool.connection() as connection:
                yield connection
            return
        with self._connection_factory(self._database_url) as connection:
            yield connection

    def latest_for_etf(self, isu_code: str) -> EtfDistributionEventDataset:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, as_of from public.etf_distribution_event_versions
                where status = 'ready' order by as_of desc, id desc limit 1
                """
            )
            version = cursor.fetchone()
            if version is None:
                raise EtfDistributionEventUnavailable("no ready event master")
            cursor.execute(
                """
                select event_type, effective_date, record_date, payment_date,
                       cash_per_share_krw, ratio, timing_basis, confidence,
                       status, source_evidence
                from public.etf_distribution_events
                where version_id = %s and isu_code = %s
                order by effective_date desc, event_type
                """,
                (int(version[0]), isu_code),
            )
            rows = cursor.fetchall()
        as_of = version[1]
        if not isinstance(as_of, date):
            as_of = date.fromisoformat(str(as_of))
        return EtfDistributionEventDataset(
            as_of=as_of,
            events=[
                {
                    "event_type": str(row[0]),
                    "effective_date": _date_text(row[1]),
                    "record_date": _date_text(row[2]),
                    "payment_date": _date_text(row[3]),
                    "cash_per_share_krw": _decimal_text(row[4]),
                    "ratio": _decimal_text(row[5]),
                    "timing_basis": str(row[6]),
                    "confidence": str(row[7]),
                    "status": str(row[8]),
                    "source_evidence": row[9] if isinstance(row[9], list) else [],
                }
                for row in rows
            ],
        )


def _date_text(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _decimal_text(value: object) -> str | None:
    return format(Decimal(str(value)), "f") if value is not None else None


def load_etf_distribution_event_master(
    database_url: str, *, event_path: Path
) -> EtfDistributionEventLoadSummary:
    """Persist one normalized official event master without recalculating it."""

    report = _load_report(event_path)
    as_of = _as_date(report.get("as_of"), field="as_of")
    engine_name = _required_text(report.get("engine_name"), field="engine_name")
    engine_version = _required_text(
        report.get("engine_version"), field="engine_version"
    )
    source_files = report.get("source_files")
    if not isinstance(source_files, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in source_files.items()
    ):
        raise EtfDistributionEventLoadError("source_files must be a string map")
    raw_events = report.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise EtfDistributionEventLoadError("events must be a non-empty list")
    if not all(isinstance(event, dict) for event in raw_events):
        raise EtfDistributionEventLoadError("events must contain objects")

    event_rows = [_event_row(event) for event in raw_events]
    event_keys = [str(row[0]) for row in event_rows]
    if len(event_keys) != len(set(event_keys)):
        raise EtfDistributionEventLoadError("events contain duplicate payloads")
    source_sha256 = _sha256(event_path)

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.etf_distribution_event_versions (
                as_of, status, source_sha256, engine_name, engine_version, source_files
            ) values (%s, 'loading', %s, %s, %s, %s)
            on conflict (as_of) do update set
                status = 'loading', source_sha256 = excluded.source_sha256,
                engine_name = excluded.engine_name,
                engine_version = excluded.engine_version,
                source_files = excluded.source_files, loaded_at = null
            returning id
            """,
            (as_of, source_sha256, engine_name, engine_version, Jsonb(source_files)),
        )
        version = cursor.fetchone()
        if version is None:
            raise EtfDistributionEventLoadError("failed to create event version")
        version_id = int(version[0])
        cursor.execute(
            "delete from public.etf_distribution_events where version_id = %s",
            (version_id,),
        )
        cursor.executemany(
            """
            insert into public.etf_distribution_events (
                version_id, event_key, isu_code, isu_name, isin, event_type,
                effective_date, record_date, payment_date, cash_per_share_krw, ratio,
                timing_basis, confidence, status, source_evidence, raw_payload
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            [(version_id, *row) for row in event_rows],
        )
        cursor.execute(
            """
            update public.etf_distribution_event_versions
            set status = 'ready', event_rows = %s, loaded_at = now()
            where id = %s
            """,
            (len(event_rows), version_id),
        )
    return EtfDistributionEventLoadSummary(
        as_of=as_of,
        version_id=version_id,
        event_rows=len(event_rows),
        source_sha256=source_sha256,
    )


def _load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EtfDistributionEventLoadError(
            f"cannot read ETF distribution event master: {path}"
        ) from error
    if not isinstance(payload, dict):
        raise EtfDistributionEventLoadError("event master root must be an object")
    if payload.get("report_type") != "pension_eligible_etf_corporate_event_master":
        raise EtfDistributionEventLoadError("unexpected event master report_type")
    return payload


def _event_row(event: dict[str, Any]) -> tuple[Any, ...]:
    source_evidence = event.get("source_evidence")
    if (
        not isinstance(source_evidence, list)
        or not source_evidence
        or not all(isinstance(item, dict) for item in source_evidence)
    ):
        raise EtfDistributionEventLoadError("event source_evidence must be object list")
    canonical = json.dumps(
        event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return (
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        _required_text(event.get("isu_code"), field="isu_code"),
        _optional_text(event.get("isu_name")),
        _optional_text(event.get("isin")),
        _required_text(event.get("event_type"), field="event_type"),
        _as_date(event.get("effective_date"), field="effective_date"),
        _optional_date_value(event.get("record_date"), field="record_date"),
        _optional_date_value(event.get("payment_date"), field="payment_date"),
        _optional_positive_decimal(
            event.get("cash_per_share_krw"), field="cash_per_share_krw"
        ),
        _optional_positive_decimal(event.get("ratio"), field="ratio"),
        _required_text(event.get("timing_basis"), field="timing_basis"),
        _required_text(event.get("confidence"), field="confidence"),
        _required_text(event.get("status"), field="status"),
        Jsonb(source_evidence),
        Jsonb(event),
    )


def _as_date(value: object, *, field: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise EtfDistributionEventLoadError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise EtfDistributionEventLoadError(f"{field} must be an ISO date") from error


def _optional_date_value(value: object, *, field: str) -> date | None:
    return None if value is None else _as_date(value, field=field)


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EtfDistributionEventLoadError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    return None if value is None else _required_text(value, field="optional text")


def _optional_positive_decimal(value: object, *, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise EtfDistributionEventLoadError(f"{field} must be decimal") from error
    if not parsed.is_finite() or parsed < 0:
        raise EtfDistributionEventLoadError(f"{field} must be non-negative")
    if parsed == 0:
        return None
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
