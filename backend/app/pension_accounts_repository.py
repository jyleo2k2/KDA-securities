"""Authenticated pension-account snapshots mapped to pure engine inputs."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .engine.aggregation import AggregationInput
from .engine.diagnostics import AccountHolding, AccountInput
from .engine.models import (
    AccountType,
    AssetClass,
    RiskTreatment,
    StatutoryException,
)


class PensionAccountDataError(ValueError):
    """Raised when stored account facts cannot form a valid engine input."""


class PensionHoldingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holding_id: UUID
    product_id: UUID | None
    instrument_name: str = Field(min_length=1)
    etf_isu_code: str | None = Field(default=None, min_length=1)
    asset_class: AssetClass
    amount_krw: Decimal = Field(ge=0, allow_inf_nan=False)
    risk_treatment: RiskTreatment
    statutory_exception: StatutoryException | None

    def to_engine_input(self) -> AccountHolding:
        return AccountHolding(
            holding_id=str(self.holding_id),
            instrument_name=self.instrument_name,
            asset_class=self.asset_class,
            amount_krw=self.amount_krw,
            risk_treatment=self.risk_treatment,
            statutory_exception=self.statutory_exception,
        )


class PensionAccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    account_type: AccountType
    account_name: str = Field(min_length=1)
    data_kind: Literal["real", "mock"]
    origin: Literal["user_input", "provider_import", "synthetic"]
    snapshot_id: UUID
    as_of_date: date
    contributed_principal_krw: Decimal | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )
    market_value_krw: Decimal = Field(ge=0, allow_inf_nan=False)
    holdings: list[PensionHoldingSnapshot] = Field(min_length=1)

    @model_validator(mode="after")
    def require_holding_total_to_match_snapshot(self) -> "PensionAccountSnapshot":
        holding_total = sum(
            (holding.amount_krw for holding in self.holdings),
            Decimal("0"),
        )
        if holding_total != self.market_value_krw:
            raise PensionAccountDataError(
                f"holding total does not match snapshot for account {self.account_id}"
            )
        return self

    def to_engine_input(self) -> AccountInput:
        return AccountInput(
            account_id=str(self.account_id),
            account_type=self.account_type,
            holdings=[
                holding.to_engine_input() for holding in self.holdings
            ],
        )


class UserPensionPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: UUID
    data_boundary: Literal["real", "mock", "mixed", "unavailable"]
    accounts: list[PensionAccountSnapshot] = Field(default_factory=list)

    def to_aggregation_input(self) -> AggregationInput:
        if not self.accounts:
            raise PensionAccountDataError("no pension accounts are available")
        return AggregationInput(
            accounts=[account.to_engine_input() for account in self.accounts]
        )


class PensionAccountRepository:
    """Read the latest account snapshot owned by or assigned to one Auth user."""

    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
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

    def get(self, owner_id: UUID) -> UserPensionPortfolio:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                with request_context as (
                    select %s::uuid as owner_id
                ),
                real_accounts as (
                    select account.*
                    from public.pension_accounts as account
                    cross join request_context as context
                    where account.data_kind = 'real'
                      and account.owner_id = context.owner_id
                ),
                entitled_accounts as (
                    select real_account.*
                    from real_accounts as real_account
                    union all
                    select account.*
                    from public.pension_accounts as account
                    join public.demo_user_financial_context as demo
                      on demo.scenario_id = account.scenario_id
                    cross join request_context as context
                    where account.data_kind = 'mock'
                      and demo.auth_user_id = context.owner_id
                      and not exists (select 1 from real_accounts)
                )
                select
                    account.id,
                    account.account_type,
                    account.account_name,
                    account.data_kind,
                    account.origin,
                    snapshot.id,
                    snapshot.as_of_date,
                    snapshot.contributed_principal_krw,
                    snapshot.market_value_krw,
                    holding.id,
                    holding.product_id,
                    coalesce(product.product_name, holding.raw_instrument_name),
                    holding.etf_isu_code,
                    asset.code,
                    holding.market_value_krw,
                    holding.risk_treatment,
                    holding.statutory_exception
                from entitled_accounts as account
                join lateral (
                    select current_snapshot.*
                    from public.account_snapshots as current_snapshot
                    where current_snapshot.account_id = account.id
                    order by current_snapshot.as_of_date desc,
                             current_snapshot.captured_at desc
                    limit 1
                ) as snapshot on true
                join public.account_holding_snapshots as holding
                  on holding.snapshot_id = snapshot.id
                join public.asset_classes as asset
                  on asset.id = holding.asset_class_id
                left join public.financial_products as product
                  on product.id = holding.product_id
                order by account.account_type, account.id, holding.id
                """,
                (owner_id,),
            )
            rows = list(cursor)
        return self._portfolio_from_rows(owner_id, rows)

    @staticmethod
    def _portfolio_from_rows(
        owner_id: UUID,
        rows: Sequence[Sequence[object]],
    ) -> UserPensionPortfolio:
        grouped: dict[UUID, dict[str, object]] = {}
        account_order: list[UUID] = []
        for row in rows:
            account_id = UUID(str(row[0]))
            if account_id not in grouped:
                account_order.append(account_id)
                grouped[account_id] = {
                    "account_id": account_id,
                    "account_type": row[1],
                    "account_name": row[2],
                    "data_kind": row[3],
                    "origin": row[4],
                    "snapshot_id": row[5],
                    "as_of_date": row[6],
                    "contributed_principal_krw": row[7],
                    "market_value_krw": row[8],
                    "holdings": [],
                }
            holdings = grouped[account_id]["holdings"]
            assert isinstance(holdings, list)
            holdings.append(
                PensionHoldingSnapshot(
                    holding_id=row[9],
                    product_id=row[10],
                    instrument_name=row[11],
                    etf_isu_code=row[12],
                    asset_class=row[13],
                    amount_krw=row[14],
                    risk_treatment=row[15],
                    statutory_exception=row[16],
                )
            )

        try:
            accounts = [
                PensionAccountSnapshot.model_validate(grouped[account_id])
                for account_id in account_order
            ]
        except ValidationError as exc:
            raise PensionAccountDataError(str(exc)) from exc
        data_kinds = {account.data_kind for account in accounts}
        if not data_kinds:
            boundary = "unavailable"
        elif len(data_kinds) == 1:
            boundary = next(iter(data_kinds))
        else:
            boundary = "mixed"
        return UserPensionPortfolio(
            owner_id=owner_id,
            data_boundary=boundary,
            accounts=accounts,
        )
