"""Read the latest stored KIS ETF component snapshots for chatbot answers."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool


@dataclass(frozen=True, slots=True)
class EtfComponentHolding:
    rank: int
    component_isu_code: str | None
    component_name: str
    weight_percent: Decimal


@dataclass(frozen=True, slots=True)
class EtfComponentSnapshot:
    isu_code: str
    captured_at: datetime
    holdings: tuple[EtfComponentHolding, ...]


class EtfComponentSnapshotRepository:
    """Server-only reader for the latest successful KIS component snapshot."""

    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
        connection_factory: Callable[[str], Any] = psycopg.connect,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
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

    def latest_for(
        self, isu_codes: Sequence[str]
    ) -> dict[str, EtfComponentSnapshot]:
        codes = tuple(dict.fromkeys(code.strip() for code in isu_codes if code.strip()))
        if not codes:
            return {}
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                with latest as (
                    select distinct on (isu_code) id, isu_code, captured_at
                    from public.etf_component_snapshots
                    where isu_code = any(%s)
                      and status = 'succeeded'
                      and component_count > 0
                    order by isu_code, captured_at desc
                )
                select
                    latest.isu_code,
                    latest.captured_at,
                    item.rank,
                    item.component_isu_code,
                    item.component_name,
                    item.weight_percent
                from latest
                left join public.etf_component_snapshot_items item
                  on item.snapshot_id = latest.id
                order by latest.isu_code, item.rank
                """,
                (list(codes),),
            )
            rows = cursor.fetchall()

        grouped: dict[str, list[EtfComponentHolding]] = {}
        captured_at: dict[str, datetime] = {}
        for code, captured, rank, component_code, name, weight in rows:
            normalized_code = str(code)
            holdings = grouped.setdefault(normalized_code, [])
            if rank is not None:
                holdings.append(
                    EtfComponentHolding(
                        rank=int(rank),
                        component_isu_code=(
                            str(component_code) if component_code else None
                        ),
                        component_name=str(name),
                        weight_percent=Decimal(str(weight)),
                    )
                )
            captured_at[normalized_code] = captured
        return {
            code: EtfComponentSnapshot(
                isu_code=code,
                captured_at=captured_at[code],
                holdings=tuple(holdings),
            )
            for code, holdings in grouped.items()
        }
