"""Cross-account aggregation (아키텍처.md §2 module 4).

Aggregated figures are display-only. Account rules (risk caps, eligibility)
are judged per account by their own engines and never on combined totals
(계좌 규칙 혼합 금지).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .diagnostics import AccountInput
from .models import AccountType, AssetClass, AssetClassWeight, SourceChip
from .portfolio import MONEY_QUANTUM, PERCENT_QUANTUM

ENGINE_NAME = "portfolio_aggregation"
ENGINE_VERSION = "2026-07-15.1"
AGGREGATION_NOTICE = (
    "합산 수치는 표시용이며, 위험자산 한도 등 계좌 규칙은 계좌별로만 판정한다"
)
AGGREGATION_SOURCE = SourceChip(
    label="아키텍처 §2 모듈 4",
    reference="docs/30_스펙/아키텍처.md#2-규칙-엔진-6모듈--계산판단의-단일-소스",
    as_of=date(2026, 7, 15),
)


class AggregationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounts: list[AccountInput] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_account_ids(self) -> "AggregationInput":
        account_ids = [account.account_id for account in self.accounts]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("account_id values must be unique")
        return self


class AccountContribution(BaseModel):
    account_id: str
    account_type: AccountType
    amount_krw: Decimal
    weight_percent: Decimal


class OverlapFinding(BaseModel):
    asset_class: AssetClass
    account_ids: list[str]
    combined_amount_krw: Decimal
    combined_weight_percent: Decimal


class AggregationEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    total_amount_krw: Decimal
    asset_class_totals: list[AssetClassWeight]
    per_account: list[AccountContribution]
    overlaps: list[OverlapFinding]
    notice: str
    evidence: list[SourceChip]


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percent_of(part: Decimal, total: Decimal) -> Decimal:
    return (part / total * Decimal("100")).quantize(
        PERCENT_QUANTUM, rounding=ROUND_HALF_UP
    )


def aggregate_accounts(inputs: AggregationInput) -> AggregationEvaluation:
    """Aggregate accounts for display without judging any combined rule."""

    class_amounts: dict[AssetClass, Decimal] = {}
    class_accounts: dict[AssetClass, list[str]] = {}
    account_amounts: list[tuple[AccountInput, Decimal]] = []
    for account in inputs.accounts:
        account_total = sum(
            (holding.amount_krw for holding in account.holdings), Decimal("0")
        )
        account_amounts.append((account, account_total))
        for holding in account.holdings:
            class_amounts[holding.asset_class] = (
                class_amounts.get(holding.asset_class, Decimal("0"))
                + holding.amount_krw
            )
            owners = class_accounts.setdefault(holding.asset_class, [])
            if account.account_id not in owners:
                owners.append(account.account_id)

    total = sum((amount for _, amount in account_amounts), Decimal("0"))

    asset_class_totals = [
        AssetClassWeight(
            asset_class=asset_class,
            amount_krw=_money(amount),
            weight_percent=_percent_of(amount, total),
        )
        for asset_class, amount in sorted(class_amounts.items())
    ]
    per_account = [
        AccountContribution(
            account_id=account.account_id,
            account_type=account.account_type,
            amount_krw=_money(amount),
            weight_percent=_percent_of(amount, total),
        )
        for account, amount in account_amounts
    ]
    overlaps = [
        OverlapFinding(
            asset_class=asset_class,
            account_ids=owners,
            combined_amount_krw=_money(class_amounts[asset_class]),
            combined_weight_percent=_percent_of(class_amounts[asset_class], total),
        )
        for asset_class, owners in sorted(class_accounts.items())
        if len(owners) >= 2
    ]

    return AggregationEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        total_amount_krw=_money(total),
        asset_class_totals=asset_class_totals,
        per_account=per_account,
        overlaps=overlaps,
        notice=AGGREGATION_NOTICE,
        evidence=[AGGREGATION_SOURCE],
    )
