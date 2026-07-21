"""Build past-performance and synthetic-like metrics for six demo portfolios."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"
OUTPUT_PATH = MOCK_DIR / "demo_public_portfolio_metrics.json"
PERCENT_QUANTUM = Decimal("0.01")
LIKE_COUNT_AS_OF_DATE = "2026-07-21"
SYNTHETIC_LIKE_COUNTS = {
    "dc_dormant": 126,
    "tax_contribution_uninvested": 284,
    "overlap_risk_concentration": 173,
    "young_retirement_distance": 412,
    "family_budget_pressure": 358,
    "pension_payout_transition": 97,
}


def _read_accounts() -> dict[str, list[dict[str, str]]]:
    by_user: dict[str, list[dict[str, str]]] = defaultdict(list)
    with (MOCK_DIR / "accounts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        for row in csv.DictReader(file):
            by_user[row["user_id"]].append(row)
    return by_user


def _weighted_return(rows: list[dict[str, str]]) -> Decimal:
    total_balance = sum((Decimal(row["balance_krw"]) for row in rows), Decimal("0"))
    if total_balance <= 0:
        raise ValueError("demo portfolio balance must be positive")
    weighted_total = sum(
        (
            Decimal(row["balance_krw"])
            * Decimal(row["trailing_12m_return_pct"])
            for row in rows
        ),
        Decimal("0"),
    )
    return (weighted_total / total_balance).quantize(
        PERCENT_QUANTUM, rounding=ROUND_HALF_UP
    )


def build() -> dict[str, Any]:
    users = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    accounts_by_user = _read_accounts()
    if set(SYNTHETIC_LIKE_COUNTS) != {
        str(user["scenario_code"]) for user in users
    }:
        raise ValueError("synthetic like counts must match the six demo scenarios")

    metrics: list[dict[str, Any]] = []
    for user in users:
        scenario_code = str(user["scenario_code"])
        benchmark_user_id = str(user["benchmark_user_id"])
        rows = accounts_by_user[benchmark_user_id]
        period_ends = {row["return_period_end"] for row in rows}
        if len(period_ends) != 1:
            raise ValueError(f"return periods differ for {scenario_code}")
        period_end = date.fromisoformat(period_ends.pop())
        period_start = period_end.replace(year=period_end.year - 1) + timedelta(days=1)
        metrics.append(
            {
                "scenario_code": scenario_code,
                "benchmark_user_id": benchmark_user_id,
                "portfolio_trailing_12m_return_pct": str(_weighted_return(rows)),
                "return_period_start": period_start.isoformat(),
                "return_period_end": period_end.isoformat(),
                "like_count": SYNTHETIC_LIKE_COUNTS[scenario_code],
            }
        )

    return {
        "schema_version": 1,
        "data_boundary": "mock",
        "notice": (
            "과거 수익률은 1만 명 기준 고객의 계좌별 2025년 합성 수익률을 "
            "계좌잔액으로 가중한 시연 참고값이며 미래 성과 예측이나 공식 랭킹 "
            "산식이 아니다. 좋아요 수는 수익률과 무관하게 배정한 합성 참여지표다."
        ),
        "return_metric": {
            "metric_code": "balance_weighted_trailing_12m_mock_return",
            "label": "과거 12개월 계좌잔액 가중 합성수익률",
            "calculation_basis": "Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액",
            "source_label": "data/mock/accounts.csv 합성 계좌 수익률",
            "data_kind": "MOCK",
            "is_forecast": False,
            "official_ranking_metric": False,
        },
        "like_metric": {
            "metric_code": "synthetic_demo_like_count",
            "label": "추천(좋아요)",
            "as_of_date": LIKE_COUNT_AS_OF_DATE,
            "data_kind": "MOCK",
            "is_synthetic": True,
            "performance_based": False,
        },
        "profiles": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        is_stale = (
            not OUTPUT_PATH.exists()
            or OUTPUT_PATH.read_text(encoding="utf-8") != rendered
        )
        if is_stale:
            raise SystemExit("demo public portfolio metrics are stale")
        print("PASS: demo public portfolio metrics are current")
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print("wrote six demo public portfolio metrics")


if __name__ == "__main__":
    main()
