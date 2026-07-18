from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import TypeAdapter

from ..engine import (
    ScenarioAccountInput,
    ScenarioHoldingInput,
    ScenarioPortfolioInput,
)
from .models import ScenarioSummary

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIO_PATH = ROOT / "data" / "mock" / "chatbot_scenarios.json"


class ScenarioRepository(Protocol):
    def get(self, code: str) -> ScenarioPortfolioInput | None: ...

    def list(self) -> list[ScenarioSummary]: ...


class LocalScenarioRepository:
    def __init__(self, path: Path = DEFAULT_SCENARIO_PATH) -> None:
        self._path = path
        adapter = TypeAdapter(list[ScenarioPortfolioInput])
        scenarios = adapter.validate_json(self._path.read_text(encoding="utf-8"))
        self._scenarios = tuple(scenarios)

    def get(self, code: str) -> ScenarioPortfolioInput | None:
        return next(
            (
                scenario
                for scenario in self._scenarios
                if scenario.scenario_code == code
            ),
            None,
        )

    def list(self) -> list[ScenarioSummary]:
        return [
            ScenarioSummary(
                code=scenario.scenario_code,
                name=scenario.name,
                description=scenario.description,
                age_band=scenario.age_band,
                risk_profile=scenario.risk_profile,
                investment_horizon_years=scenario.investment_horizon_years,
            )
            for scenario in self._scenarios
        ]


class PostgresScenarioRepository:
    """Read the same scenario contract from the authoritative mock tables."""

    def __init__(
        self, database_url: str, *, pool: ConnectionPool | None = None
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def get(self, code: str) -> ScenarioPortfolioInput | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    scenario.code,
                    scenario.name,
                    scenario.description,
                    scenario.age_band,
                    scenario.risk_profile,
                    scenario.investment_horizon_years,
                    account.id,
                    account.account_type,
                    account.label,
                    holding.id,
                    coalesce(
                        product.payload ->> 'isu_name',
                        holding.instrument_name
                    ),
                    asset.code,
                    holding.market_value_krw,
                    holding.risk_treatment,
                    holding.statutory_exception,
                    holding.etf_isu_code
                from public.mock_scenarios as scenario
                join public.mock_accounts as account
                  on account.scenario_id = scenario.id
                join public.mock_holdings as holding
                  on holding.account_id = account.id
                join public.asset_classes as asset
                  on asset.id = holding.asset_class_id
                left join public.etf_dataset_versions as version
                  on version.status = 'ready'
                 and version.id = (
                     select max(id)
                     from public.etf_dataset_versions
                     where status = 'ready'
                 )
                left join public.etf_universe_products as product
                  on product.version_id = version.id
                 and product.account_type = account.account_type
                 and product.isu_code = holding.etf_isu_code
                where scenario.code = %s
                  and scenario.is_active = true
                order by account.id, holding.id
                """,
                (code,),
            )
            rows = list(cursor)
        if not rows:
            return None

        account_rows: dict[int, tuple[str, str]] = {}
        holdings_by_account: dict[int, list[ScenarioHoldingInput]] = {}
        for row in rows:
            account_id = row[6]
            holdings_by_account.setdefault(account_id, []).append(
                ScenarioHoldingInput(
                    holding_id=str(row[9]),
                    instrument_name=row[10],
                    asset_class_code=row[11],
                    amount_krw=row[12],
                    risk_treatment=row[13],
                    statutory_exception=row[14],
                    etf_isu_code=row[15],
                )
            )
            account_rows.setdefault(account_id, (row[7], row[8]))
        populated_accounts = [
            ScenarioAccountInput(
                account_id=str(account_id),
                account_type=account_type,
                label=label,
                holdings=holdings_by_account[account_id],
            )
            for account_id, (account_type, label) in account_rows.items()
        ]
        first = rows[0]
        return ScenarioPortfolioInput(
            scenario_code=first[0],
            name=first[1],
            description=first[2],
            age_band=first[3],
            risk_profile=first[4],
            investment_horizon_years=first[5],
            accounts=populated_accounts,
        )

    def list(self) -> list[ScenarioSummary]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    code,
                    name,
                    description,
                    age_band,
                    risk_profile,
                    investment_horizon_years
                from public.mock_scenarios
                where is_active = true
                order by id
                """
            )
            return [
                ScenarioSummary(
                    code=row[0],
                    name=row[1],
                    description=row[2],
                    age_band=row[3],
                    risk_profile=row[4],
                    investment_horizon_years=row[5],
                )
                for row in cursor
            ]
