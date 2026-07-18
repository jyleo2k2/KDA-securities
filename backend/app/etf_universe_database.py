"""로컬 ETF 포트폴리오 유니버스 캐시를 Supabase로 적재한다(아키텍처.md §4/§9).

`PortfolioUniverseRepository.from_latest_cache`가 파일에서 만든 결과를 그대로
`etf_dataset_versions`·`etf_universe_products`·`etf_return_histories`에 옮긴다.
값을 재계산하거나 재해석하지 않는다 — DB는 검증된 입력을 보관·제공만 한다.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.app.engine.models import AccountType
from backend.app.portfolio_universe_repository import (
    DEFAULT_ADJUSTED_PRICE_ROOT,
    DEFAULT_EVENT_ROOT,
    DEFAULT_KRX_ROOT,
    DEFAULT_RETURN_ROOT,
    HISTORY_FILE_LOOKBACK,
    PortfolioUniverseRepository,
)

ACCOUNT_TYPES: tuple[AccountType, ...] = (
    AccountType.DC,
    AccountType.IRP,
    AccountType.PENSION_SAVINGS,
)


class PortfolioUniverseLoadError(RuntimeError):
    """적재 실패 — 운영자에게 그대로 노출해도 되는 메시지만 담는다."""


@dataclass(frozen=True, slots=True)
class PortfolioUniverseLoadSummary:
    as_of: date
    version_id: int
    product_rows: int
    history_rows: int
    account_product_counts: dict[str, int]
    source_sha256: str


class PostgresPortfolioUniverseRepository:
    """최신 ready ETF 데이터셋을 계좌별 엔진 입력으로 복원한다."""

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

    def latest(self, account_type: AccountType) -> PortfolioUniverseRepository:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, as_of
                from public.etf_dataset_versions
                where status = 'ready'
                order by as_of desc, id desc
                limit 1
                """
            )
            version_row = cursor.fetchone()
            if version_row is None:
                raise PortfolioUniverseLoadError(
                    "database has no ready ETF dataset version"
                )
            version_id = int(version_row[0])
            as_of = (
                version_row[1]
                if isinstance(version_row[1], date)
                else date.fromisoformat(str(version_row[1]))
            )

            cursor.execute(
                """
                select isu_code, payload
                from public.etf_universe_products
                where version_id = %s and account_type = %s
                order by isu_code
                """,
                (version_id, account_type.value),
            )
            product_rows = cursor.fetchall()

            cursor.execute(
                """
                select h.isu_code, h.observed_on, h.index_value, h.source
                from public.etf_return_histories h
                join public.etf_universe_products p
                  on p.version_id = h.version_id
                 and p.isu_code = h.isu_code
                where h.version_id = %s and p.account_type = %s
                order by h.isu_code, h.observed_on
                """,
                (version_id, account_type.value),
            )
            history_rows = cursor.fetchall()

        products: list[dict[str, Any]] = []
        for isu_code, payload in product_rows:
            if not isinstance(payload, dict):
                raise PortfolioUniverseLoadError(
                    f"ETF product payload is not an object: {isu_code}"
                )
            if payload.get("isu_code") != isu_code:
                raise PortfolioUniverseLoadError(
                    f"ETF product code does not match payload: {isu_code}"
                )
            products.append(payload)
        if not products:
            raise PortfolioUniverseLoadError(
                f"ready ETF dataset has no products for {account_type.value}"
            )

        histories: dict[str, dict[date, Decimal]] = defaultdict(dict)
        history_sources: dict[str, str] = {}
        for isu_code, observed_on, index_value, source in history_rows:
            parsed_date = (
                observed_on
                if isinstance(observed_on, date)
                else date.fromisoformat(str(observed_on))
            )
            histories[str(isu_code)][parsed_date] = Decimal(str(index_value))
            existing_source = history_sources.setdefault(str(isu_code), str(source))
            if existing_source != source:
                raise PortfolioUniverseLoadError(
                    f"ETF history has mixed sources: {isu_code}"
                )

        missing_histories = {
            str(product["isu_code"]) for product in products
        }.difference(histories)
        if missing_histories:
            raise PortfolioUniverseLoadError(
                "ready ETF dataset has products without history: "
                f"{len(missing_histories)}"
            )

        return PortfolioUniverseRepository(
            account_type=account_type,
            products=products,
            histories=dict(histories),
            history_sources=history_sources,
            as_of=as_of,
            source_path=(
                Path("database") / "etf_dataset_versions" / str(version_id)
            ),
        )


def _combined_source_sha256(source_files: list[tuple[str, Path]]) -> str:
    digest = hashlib.sha256()
    for label, path in sorted(source_files):
        file_digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                file_digest.update(chunk)
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.digest())
    return digest.hexdigest()


def _dataset_source_files(
    repositories: dict[AccountType, PortfolioUniverseRepository],
    *,
    krx_root: Path,
    adjusted_price_root: Path,
    event_root: Path,
) -> list[tuple[str, Path]]:
    sources = {
        f"returns/{repo.source_path.name}": repo.source_path
        for repo in repositories.values()
    }
    adjusted_directories = (
        sorted(path for path in adjusted_price_root.iterdir() if path.is_dir())
        if adjusted_price_root.exists()
        else []
    )
    if adjusted_directories:
        adjusted_directory = adjusted_directories[-1]
        kis_codes = {
            code
            for repo in repositories.values()
            for code, source in repo.history_sources.items()
            if source.startswith("kis_adjusted_close")
        }
        for code in kis_codes:
            path = adjusted_directory / f"{code}.json"
            if path.exists():
                label = (
                    f"kis/adjusted_prices/{adjusted_directory.name}/{path.name}"
                )
                sources[label] = path

    event_paths = sorted(event_root.glob("etf_corporate_events_*.json"))
    if event_paths:
        path = event_paths[-1]
        sources[f"events/{path.name}"] = path

    uses_krx_fallback = any(
        source == "krx_close_fallback"
        for repo in repositories.values()
        for source in repo.history_sources.values()
    )
    if uses_krx_fallback:
        krx_paths = sorted((krx_root / "etf_bydd_trd").glob("*/*/*.json"))[
            -HISTORY_FILE_LOOKBACK:
        ]
        for path in krx_paths:
            relative = path.relative_to(krx_root).as_posix()
            sources[f"krx/{relative}"] = path
    return list(sources.items())


def load_portfolio_universe(
    database_url: str,
    *,
    return_root: Path = DEFAULT_RETURN_ROOT,
    krx_root: Path = DEFAULT_KRX_ROOT,
    adjusted_price_root: Path = DEFAULT_ADJUSTED_PRICE_ROOT,
    event_root: Path = DEFAULT_EVENT_ROOT,
) -> PortfolioUniverseLoadSummary:
    """계좌 3종의 최신 캐시를 하나의 데이터셋 버전으로 원격에 적재한다."""

    repositories = {
        account_type: PortfolioUniverseRepository.from_latest_cache(
            account_type,
            return_root=return_root,
            krx_root=krx_root,
            adjusted_price_root=adjusted_price_root,
            event_root=event_root,
        )
        for account_type in ACCOUNT_TYPES
    }

    as_of_values = {repo.as_of for repo in repositories.values()}
    if len(as_of_values) != 1:
        raise PortfolioUniverseLoadError(
            "account cost-return masters do not share one as_of date: "
            f"{sorted(value.isoformat() for value in as_of_values)}"
        )
    as_of = as_of_values.pop()
    source_sha256 = _combined_source_sha256(
        _dataset_source_files(
            repositories,
            krx_root=krx_root,
            adjusted_price_root=adjusted_price_root,
            event_root=event_root,
        )
    )

    # 같은 종목이 둘 이상 계좌에서 적격이면 이력이 동일하므로 종목당 1행으로 합친다.
    combined_histories: dict[str, dict[date, tuple[Decimal, str]]] = {}
    for repo in repositories.values():
        for isu_code, history in repo.histories.items():
            source = repo.history_sources[isu_code]
            bucket = combined_histories.setdefault(isu_code, {})
            for observed_on, value in history.items():
                bucket[observed_on] = (value, source)

    product_rows = [
        (account_type.value, product["isu_code"], as_of, Jsonb(product))
        for account_type, repo in repositories.items()
        for product in repo.products
        if isinstance(product, dict) and isinstance(product.get("isu_code"), str)
    ]
    history_rows = [
        (isu_code, observed_on, value, source)
        for isu_code, history in combined_histories.items()
        for observed_on, (value, source) in history.items()
    ]

    with (
        psycopg.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
                insert into public.etf_dataset_versions (as_of, status, source_sha256)
                values (%s, 'loading', %s)
                on conflict (as_of) do update set
                    status = 'loading',
                    source_sha256 = excluded.source_sha256,
                    loaded_at = null
                returning id
                """,
            (as_of, source_sha256),
        )
        version_row = cursor.fetchone()
        if version_row is None:
            raise PortfolioUniverseLoadError("failed to create dataset version")
        version_id = int(version_row[0])

        cursor.execute(
            "delete from public.etf_universe_products where version_id = %s",
            (version_id,),
        )
        cursor.execute(
            "delete from public.etf_return_histories where version_id = %s",
            (version_id,),
        )
        if product_rows:
            cursor.executemany(
                """
                    insert into public.etf_universe_products (
                        version_id, account_type, isu_code, as_of, payload
                    )
                    values (%s, %s, %s, %s, %s)
                    """,
                [(version_id, *row) for row in product_rows],
            )
        if history_rows:
            cursor.executemany(
                """
                    insert into public.etf_return_histories (
                        version_id, isu_code, observed_on, index_value, source
                    )
                    values (%s, %s, %s, %s, %s)
                    on conflict (version_id, isu_code, observed_on) do nothing
                    """,
                [(version_id, *row) for row in history_rows],
            )
        cursor.execute(
            """
                update public.etf_dataset_versions
                set status = 'ready',
                    product_rows = %s,
                    history_rows = %s,
                    loaded_at = now()
                where id = %s
                """,
            (len(product_rows), len(history_rows), version_id),
        )

    return PortfolioUniverseLoadSummary(
        as_of=as_of,
        version_id=version_id,
        product_rows=len(product_rows),
        history_rows=len(history_rows),
        account_product_counts={
            account_type.value: len(repo.products)
            for account_type, repo in repositories.items()
        },
        source_sha256=source_sha256,
    )
