"""Read validated ETF component snapshots for chatbot answers."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
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
    as_of_date: date | None = None
    source_kind: str = "actual_portfolio"
    coverage_kind: str = "full_portfolio"
    weight_basis: str = "reported_weight_percent"
    source_code: str = "kis_etf_components"
    publisher: str = "한국투자증권 Open Trading API"
    source_locator: str = (
        "https://openapi.koreainvestment.com:9443/uapi/etfetn/"
        "v1/quotations/inquire-component-stock-price"
    )


class EtfComponentSnapshotRepository:
    """Server-only reader for latest complete components from approved sources."""

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
                with latest_ready_version as (
                    select id
                    from public.etf_dataset_versions
                    where status = 'ready'
                    order by as_of desc, id desc
                    limit 1
                ), product_classification as (
                    select
                        product.isu_code,
                        bool_or(
                            coalesce(
                                product.payload->'classification'->>'asset_class',
                                ''
                            ) = 'equity'
                            and coalesce(
                                product.payload->'classification'->>'region',
                                'south_korea'
                            ) <> 'south_korea'
                        ) as is_foreign_equity
                    from public.etf_universe_products product
                    join latest_ready_version version
                      on version.id = product.version_id
                    where product.isu_code = any(%s)
                    group by product.isu_code
                ), latest as (
                    select distinct on (snapshot.isu_code)
                        snapshot.id,
                        snapshot.isu_code,
                        snapshot.captured_at,
                        snapshot.as_of_date,
                        snapshot.source_kind,
                        snapshot.coverage_kind,
                        snapshot.weight_basis,
                        source.code as source_code,
                        source.authority as publisher,
                        coalesce(
                            snapshot.source_locator,
                            source.base_url
                        ) as source_locator
                    from public.etf_component_snapshots snapshot
                    join product_classification classification
                      on classification.isu_code = snapshot.isu_code
                    join public.data_sources source on source.id = snapshot.source_id
                    left join public.etf_component_source_bindings binding
                      on binding.isu_code = snapshot.isu_code
                     and binding.source_id = snapshot.source_id
                     and binding.adapter_code is not null
                     and binding.is_active
                    where snapshot.status = 'succeeded'
                      and snapshot.component_count > 0
                      and snapshot.source_kind <> 'collateral'
                      and (
                          source.code = 'kis_etf_components'
                          or (
                              source.code <> 'kis_etf_components'
                              and binding.id is not null
                              and snapshot.completeness = 'complete'
                              and snapshot.as_of_date is not null
                              and snapshot.as_of_date >= current_date - 10
                          )
                      )
                    order by
                        snapshot.isu_code,
                        case
                            when source.code = 'kis_etf_components' then 0
                            when classification.is_foreign_equity then 1
                            else 2
                        end,
                        case snapshot.source_kind
                            when 'actual_portfolio' then 1
                            when 'creation_basket' then 2
                            when 'index_exposure' then 3
                            when 'look_through' then 4
                            else 5
                        end,
                        coalesce(binding.priority, 1000),
                        snapshot.as_of_date desc nulls last,
                        snapshot.captured_at desc
                )
                select
                    latest.isu_code,
                    latest.captured_at,
                    latest.as_of_date,
                    latest.source_kind,
                    latest.coverage_kind,
                    latest.weight_basis,
                    latest.source_code,
                    latest.publisher,
                    latest.source_locator,
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
        snapshot_metadata: dict[str, tuple[Any, ...]] = {}
        for (
            code,
            captured,
            as_of,
            source_kind,
            coverage_kind,
            weight_basis,
            source_code,
            publisher,
            source_locator,
            rank,
            component_code,
            name,
            weight,
        ) in rows:
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
            snapshot_metadata[normalized_code] = (
                captured,
                as_of,
                source_kind,
                coverage_kind,
                weight_basis,
                source_code,
                publisher,
                source_locator,
            )
        return {
            code: EtfComponentSnapshot(
                isu_code=code,
                captured_at=snapshot_metadata[code][0],
                holdings=tuple(holdings),
                as_of_date=snapshot_metadata[code][1],
                source_kind=str(snapshot_metadata[code][2]),
                coverage_kind=str(snapshot_metadata[code][3]),
                weight_basis=str(snapshot_metadata[code][4]),
                source_code=str(snapshot_metadata[code][5]),
                publisher=str(snapshot_metadata[code][6]),
                source_locator=str(snapshot_metadata[code][7]),
            )
            for code, holdings in grouped.items()
        }
