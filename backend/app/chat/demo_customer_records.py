"""Canonical 10k-record projection for the six detailed demo customers."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[3]
MOCK_DIR = ROOT / "data" / "mock"


class BenchmarkHoldingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str
    asset_class: str
    weight: Decimal
    amount_krw: Decimal
    data_kind: str
    source_ids: str


class BenchmarkAccountRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str
    user_id: str
    account_type: str
    balance_krw: Decimal
    monthly_contribution_krw: Decimal
    annual_contribution_krw: Decimal
    contribution_status: str
    contribution_frequency: str
    account_open_year: int
    contribution_years: int
    planned_contribution_years_at_receipt: int
    pension_receipt_eligibility: str
    tax_credit_eligible_contribution_krw: Decimal
    estimated_tax_credit_krw: Decimal
    planned_annual_pension_receipt_krw: Decimal
    planned_receipt_tax_treatment: str
    risky_asset_ratio: Decimal
    safe_asset_ratio: Decimal
    cash_ratio: Decimal
    trailing_12m_return_pct: Decimal
    return_period_end: str
    data_kind: str
    source_ids: str
    holdings: tuple[BenchmarkHoldingRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_aggregates(self) -> BenchmarkAccountRecord:
        if (
            sum((item.amount_krw for item in self.holdings), Decimal("0"))
            != self.balance_krw
        ):
            raise ValueError("benchmark holding amounts must equal account balance")
        if self.annual_contribution_krw != self.monthly_contribution_krw * 12:
            raise ValueError(
                "annual contribution must equal monthly contribution times 12"
            )
        return self


class BenchmarkCustomerRecord(BaseModel):
    """Every common customer/account/holding column for one benchmark user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    age: int
    age_group: str
    employment_type: str
    gross_salary_krw: Decimal | None
    comprehensive_income_krw: Decimal | None
    tax_credit_income_basis: str
    tax_credit_income_amount_krw: Decimal
    tax_year: int
    pension_tax_credit_rate_pct: Decimal
    total_tax_credit_eligible_contribution_krw: Decimal
    estimated_pension_tax_credit_krw: Decimal
    planned_pension_start_age: int
    planned_receipt_years: int
    planned_annual_total_pension_receipt_krw: Decimal
    planned_annual_personal_pension_receipt_krw: Decimal
    planned_low_rate_pension_tax_pct: Decimal
    planned_receipt_tax_treatment: str
    risk_profile: str
    preferred_management_type: str
    retirement_fund_attitude: str
    investment_readiness: str
    payout_preference: str
    primary_outside_asset: str
    mock_scenario: str
    data_kind: str
    source_ids: str
    pension_savings_contribution_krw: Decimal
    irp_contribution_krw: Decimal
    accounts: tuple[BenchmarkAccountRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_common_contract(self) -> BenchmarkCustomerRecord:
        salary_present = self.gross_salary_krw is not None
        comprehensive_present = self.comprehensive_income_krw is not None
        if salary_present == comprehensive_present:
            raise ValueError("exactly one income amount must be present")
        pension_savings = sum(
            (
                account.annual_contribution_krw
                for account in self.accounts
                if account.account_type == "PENSION_SAVINGS_FUND"
            ),
            Decimal("0"),
        )
        irp = sum(
            (
                account.annual_contribution_krw
                for account in self.accounts
                if account.account_type == "IRP"
            ),
            Decimal("0"),
        )
        if (
            pension_savings != self.pension_savings_contribution_krw
            or irp != self.irp_contribution_krw
        ):
            raise ValueError("customer contributions must equal account contributions")
        if pension_savings + irp > Decimal("18000000"):
            raise ValueError("combined personal-pension contribution exceeds KRW 18m")
        return self


def _read_rows(path: Path) -> list[dict[str, str | None]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return [
            {key: (value if value != "" else None) for key, value in row.items()}
            for row in csv.DictReader(file)
        ]


@lru_cache(maxsize=1)
def _customer_records() -> dict[str, BenchmarkCustomerRecord]:
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    selected_user_ids = {item["benchmark_user_id"] for item in manifest}
    selected_account_rows = [
        row
        for row in _read_rows(MOCK_DIR / "accounts.csv")
        if row["user_id"] in selected_user_ids
    ]
    selected_account_ids = {str(row["account_id"]) for row in selected_account_rows}
    holdings_by_account: dict[str, list[BenchmarkHoldingRecord]] = defaultdict(list)
    for row in _read_rows(MOCK_DIR / "holdings.csv"):
        if row["account_id"] not in selected_account_ids:
            continue
        holding = BenchmarkHoldingRecord.model_validate(row)
        holdings_by_account[holding.account_id].append(holding)

    accounts_by_user: dict[str, list[BenchmarkAccountRecord]] = defaultdict(list)
    for row in selected_account_rows:
        account_id = str(row["account_id"])
        account = BenchmarkAccountRecord.model_validate(
            {**row, "holdings": tuple(holdings_by_account[account_id])}
        )
        accounts_by_user[account.user_id].append(account)

    return {
        str(row["user_id"]): BenchmarkCustomerRecord.model_validate(
            {**row, "accounts": tuple(accounts_by_user[str(row["user_id"])])}
        )
        for row in _read_rows(MOCK_DIR / "users.csv")
        if row["user_id"] in selected_user_ids
    }


def get_benchmark_customer(user_id: str) -> BenchmarkCustomerRecord:
    try:
        return _customer_records()[user_id]
    except KeyError as exc:
        raise ValueError(f"unknown benchmark demo customer: {user_id}") from exc
