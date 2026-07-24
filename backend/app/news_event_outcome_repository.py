"""Read-only boundary for verified historical news-event outcome records."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import psycopg
from psycopg_pool import ConnectionPool


@dataclass(frozen=True, slots=True)
class NewsEventOutcomeRecord:
    event_key: str
    occurred_on: date
    theme_id: str
    isu_code: str
    isu_name: str
    horizon_months: int
    total_return_percent: Decimal
    maximum_drawdown_percent: Decimal
    peer_median_total_return_percent: Decimal
    peer_sample_count: int
    event_source_url: str
    event_source_label: str
    event_source_as_of: date | None
    history_source: str
    history_source_url: str
    history_source_as_of: date | None


class NewsEventOutcomeReader(Protocol):
    def list_for_theme_ids(
        self, theme_ids: tuple[str, ...], *, limit: int = 12
    ) -> list[NewsEventOutcomeRecord]: ...


class PostgresNewsEventOutcomeRepository:
    """Returns stored outcomes only; it never recalculates or recommends."""

    def __init__(
        self, database_url: str, *, pool: ConnectionPool | None = None
    ) -> None:
        self._database_url = database_url
        self._pool = pool

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._pool is not None:
            with self._pool.connection() as connection:
                yield connection
            return
        with psycopg.connect(self._database_url) as connection:
            yield connection

    def list_for_theme_ids(
        self, theme_ids: tuple[str, ...], *, limit: int = 12
    ) -> list[NewsEventOutcomeRecord]:
        themes = tuple(dict.fromkeys(theme_id for theme_id in theme_ids if theme_id))
        if not themes:
            return []
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select event_key, occurred_on, theme_id, isu_code, isu_name,
                       horizon_months, total_return_percent,
                       maximum_drawdown_percent,
                       peer_median_total_return_percent, peer_sample_count,
                       event_source_url, event_source_label, event_source_as_of,
                       history_source, history_source_url, history_source_as_of
                from public.news_event_outcomes
                where theme_id = any(%s)
                order by occurred_on desc, horizon_months, isu_code
                limit %s
                """,
                (list(themes), limit),
            )
            rows = cursor.fetchall()
        return [
            NewsEventOutcomeRecord(
                event_key=str(row[0]),
                occurred_on=_date(row[1]),
                theme_id=str(row[2]),
                isu_code=str(row[3]),
                isu_name=str(row[4]),
                horizon_months=int(row[5]),
                total_return_percent=Decimal(str(row[6])),
                maximum_drawdown_percent=Decimal(str(row[7])),
                peer_median_total_return_percent=Decimal(str(row[8])),
                peer_sample_count=int(row[9]),
                event_source_url=str(row[10]),
                event_source_label=str(row[11]),
                event_source_as_of=_optional_date(row[12]),
                history_source=str(row[13]),
                history_source_url=str(row[14]),
                history_source_as_of=_optional_date(row[15]),
            )
            for row in rows
        ]


def _date(value: object) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _optional_date(value: object) -> date | None:
    return None if value is None else _date(value)
