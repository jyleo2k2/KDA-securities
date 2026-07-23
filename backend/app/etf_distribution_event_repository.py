"""Versioned official ETF distribution-event storage boundary."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool


class EtfDistributionEventUnavailable(RuntimeError):
    pass


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
