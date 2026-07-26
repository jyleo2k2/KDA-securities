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
from datetime import date, datetime
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
    HISTORY_OBSERVATIONS,
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


@dataclass(frozen=True, slots=True)
class PortfolioUniverseOperationalAudit:
    """Integrity evidence for the promoted ETF universe kept in PostgreSQL."""

    version_id: int
    as_of: date
    loaded_at: datetime
    source_sha256: str
    expected_product_rows: int
    actual_product_rows: int
    expected_history_rows: int
    actual_history_rows: int
    products_without_history: int
    account_product_counts: dict[str, int]

    def as_json(self) -> dict[str, object]:
        return {
            "account_product_counts": self.account_product_counts,
            "actual_history_rows": self.actual_history_rows,
            "actual_product_rows": self.actual_product_rows,
            "as_of": self.as_of.isoformat(),
            "expected_history_rows": self.expected_history_rows,
            "expected_product_rows": self.expected_product_rows,
            "loaded_at": self.loaded_at.isoformat(),
            "products_without_history": self.products_without_history,
            "source_sha256": self.source_sha256,
            "version_id": self.version_id,
        }


@dataclass(frozen=True, slots=True)
class EtfThemeProductUniverse:
    """ETF 테마 카드에 필요한 상품 payload만 담는 경량 읽기 모델."""

    products: list[dict[str, Any]]
    as_of: date


def audit_latest_portfolio_universe(
    database_url: str,
    *,
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> PortfolioUniverseOperationalAudit:
    """Read the ready dataset and compare recorded counts to persisted rows.

    The database is the durable boundary for the large total-return history.
    This check deliberately reads aggregates only, so a scheduled runner never
    needs to materialize the full price cache just to verify the promoted set.
    """

    if not database_url:
        raise ValueError("database_url is required")
    with connection_factory(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            with latest as (
                select id, as_of, loaded_at, source_sha256,
                       product_rows, history_rows
                from public.etf_dataset_versions
                where status = 'ready'
                order by as_of desc, id desc
                limit 1
            ), product_counts as (
                select p.version_id,
                       count(*)::integer as actual_product_rows,
                       jsonb_object_agg(p.account_type, p.count_by_account)
                           as account_product_counts
                from (
                    select version_id, account_type, count(*)::integer
                        as count_by_account
                    from public.etf_universe_products
                    group by version_id, account_type
                ) p
                group by p.version_id
            ), history_counts as (
                select version_id, count(*)::integer as actual_history_rows
                from public.etf_return_histories
                group by version_id
            ), missing_history_counts as (
                select p.version_id, count(*)::integer as products_without_history
                from public.etf_universe_products p
                where not exists (
                    select 1
                    from public.etf_return_histories h
                    where h.version_id = p.version_id
                      and h.isu_code = p.isu_code
                )
                group by p.version_id
            )
            select latest.id, latest.as_of, latest.loaded_at, latest.source_sha256,
                   latest.product_rows, latest.history_rows,
                   coalesce(product_counts.actual_product_rows, 0),
                   coalesce(history_counts.actual_history_rows, 0),
                   coalesce(missing_history_counts.products_without_history, 0),
                   coalesce(product_counts.account_product_counts, '{}'::jsonb)
            from latest
            left join product_counts on product_counts.version_id = latest.id
            left join history_counts on history_counts.version_id = latest.id
            left join missing_history_counts
              on missing_history_counts.version_id = latest.id
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise PortfolioUniverseLoadError("database has no ready ETF dataset version")

    (
        version_id,
        as_of,
        loaded_at,
        source_sha256,
        expected_product_rows,
        expected_history_rows,
        actual_product_rows,
        actual_history_rows,
        products_without_history,
        account_product_counts,
    ) = row
    parsed_as_of = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    parsed_loaded_at = (
        loaded_at
        if isinstance(loaded_at, datetime)
        else datetime.fromisoformat(str(loaded_at))
    )
    if not isinstance(account_product_counts, dict):
        raise PortfolioUniverseLoadError("ETF dataset account counts are invalid")
    audit = PortfolioUniverseOperationalAudit(
        version_id=int(version_id),
        as_of=parsed_as_of,
        loaded_at=parsed_loaded_at,
        source_sha256=str(source_sha256),
        expected_product_rows=int(expected_product_rows),
        actual_product_rows=int(actual_product_rows),
        expected_history_rows=int(expected_history_rows),
        actual_history_rows=int(actual_history_rows),
        products_without_history=int(products_without_history),
        account_product_counts={
            str(account): int(count)
            for account, count in account_product_counts.items()
        },
    )
    validate_portfolio_universe_operational_audit(audit)
    return audit


def validate_portfolio_universe_operational_audit(
    audit: PortfolioUniverseOperationalAudit,
) -> None:
    """Reject a ready universe whose promoted rows are incomplete or changed."""

    if len(audit.source_sha256) != 64:
        raise PortfolioUniverseLoadError("ETF dataset source hash is invalid")
    if audit.expected_product_rows != audit.actual_product_rows:
        raise PortfolioUniverseLoadError(
            "ETF dataset product row count does not match the promoted version"
        )
    if audit.expected_history_rows != audit.actual_history_rows:
        raise PortfolioUniverseLoadError(
            "ETF dataset history row count does not match the promoted version"
        )
    if audit.products_without_history:
        raise PortfolioUniverseLoadError(
            "ETF dataset has products without total-return history: "
            f"{audit.products_without_history}"
        )
    if set(audit.account_product_counts) != {
        account_type.value for account_type in ACCOUNT_TYPES
    } or any(count <= 0 for count in audit.account_product_counts.values()):
        raise PortfolioUniverseLoadError(
            "ETF dataset does not contain products for every account type"
        )


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

    def _historical_histories(
        self,
        version_id: int,
        account_type: AccountType,
        isu_codes: set[str],
    ) -> tuple[dict[str, dict[date, Decimal]], dict[str, str]]:
        if not isu_codes:
            return {}, {}
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select h.isu_code, h.observed_on, h.index_value, h.source
                from public.etf_return_histories h
                join public.etf_universe_products p
                  on p.version_id = h.version_id
                 and p.isu_code = h.isu_code
                where h.version_id = %s
                  and p.account_type = %s
                  and h.isu_code = any(%s)
                order by h.isu_code, h.observed_on
                """,
                (version_id, account_type.value, sorted(isu_codes)),
            )
            rows = cursor.fetchall()
        histories: dict[str, dict[date, Decimal]] = defaultdict(dict)
        sources: dict[str, str] = {}
        for isu_code, observed_on, index_value, source in rows:
            code = str(isu_code)
            parsed_date = (
                observed_on
                if isinstance(observed_on, date)
                else date.fromisoformat(str(observed_on))
            )
            histories[code][parsed_date] = Decimal(str(index_value))
            existing = sources.setdefault(code, str(source))
            if existing != source:
                raise PortfolioUniverseLoadError(
                    f"ETF history has mixed sources: {code}"
                )
        return dict(histories), sources

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
                with ranked as (
                    select
                        h.isu_code,
                        h.observed_on,
                        h.index_value,
                        h.source,
                        row_number() over (
                            partition by h.isu_code
                            order by h.observed_on desc
                        ) as history_rank
                    from public.etf_return_histories h
                    join public.etf_universe_products p
                      on p.version_id = h.version_id
                     and p.isu_code = h.isu_code
                    where h.version_id = %s and p.account_type = %s
                )
                select isu_code, observed_on, index_value, source
                from ranked
                where history_rank <= %s
                order by isu_code, observed_on
                """,
                (version_id, account_type.value, HISTORY_OBSERVATIONS),
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
            source_path=(Path("database") / "etf_dataset_versions" / str(version_id)),
            historical_history_loader=lambda isu_codes: self._historical_histories(
                version_id, account_type, isu_codes
            ),
        )

    def latest_theme_products(
        self,
        isu_codes: tuple[str, ...] | None,
    ) -> EtfThemeProductUniverse:
        """Return canonical product payloads without loading return histories."""

        normalized_codes = (
            tuple(sorted(set(isu_codes))) if isu_codes is not None else None
        )
        query_codes = list(normalized_codes) if normalized_codes is not None else None
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
                select distinct on (isu_code) isu_code, payload
                from public.etf_universe_products
                where version_id = %s
                  and (%s::text[] is null or isu_code = any(%s::text[]))
                order by
                    isu_code,
                    case account_type
                        when 'dc' then 1
                        when 'irp' then 2
                        when 'pension_savings' then 3
                        else 4
                    end
                """,
                (version_id, query_codes, query_codes),
            )
            product_rows = cursor.fetchall()

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
        return EtfThemeProductUniverse(products=products, as_of=as_of)


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
                label = f"kis/adjusted_prices/{adjusted_directory.name}/{path.name}"
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
    all_codes = {
        str(product["isu_code"])
        for repo in repositories.values()
        for product in repo.products
    }
    history_repository = max(repositories.values(), key=lambda repo: len(repo.products))
    full_histories, full_sources = history_repository.load_total_return_histories(
        all_codes
    )
    combined_histories: dict[str, dict[date, tuple[Decimal, str]]] = {
        isu_code: {
            observed_on: (value, full_sources[isu_code])
            for observed_on, value in history.items()
        }
        for isu_code, history in full_histories.items()
        if isu_code in full_sources
    }
    for repo in repositories.values():
        for isu_code, history in repo.histories.items():
            if isu_code in combined_histories:
                continue
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
