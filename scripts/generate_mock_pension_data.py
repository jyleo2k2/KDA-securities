"""Generate reproducible synthetic pension-account data for the demo.

Only DC, IRP, and pension-savings-fund accounts are produced. The records are
fully synthetic: official statistics calibrate group averages, while missing
cross-sectional dispersion and account-combination data are explicit model
assumptions documented in data/mock/README.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


DC = "DC"
IRP = "IRP"
PENSION_SAVINGS_FUND = "PENSION_SAVINGS_FUND"
ALLOWED_ACCOUNT_TYPES = (DC, IRP, PENSION_SAVINGS_FUND)

SCENARIO_WEIGHTS = {
    "DC_NEGLECT": 0.40,
    "TAX_BENEFIT_IDLE": 0.30,
    "OVERLAP_RISK": 0.30,
}
AGE_GROUP_WEIGHTS = {
    "20s": 0.1190,
    "30s": 0.2906,
    "40s": 0.3248,
    "50_plus": 0.2656,
}
AGE_RANGES = {
    "20s": (20, 29),
    "30s": (30, 39),
    "40s": (40, 49),
    "50_plus": (50, 64),
}

# Arithmetic mean account balances by age group (KRW). DC is reported survey
# data; IRP and pension-savings-fund use official market averages scaled by the
# observed DC age pattern because their public age cross-tabs are unavailable.
BALANCE_MEAN_KRW = {
    DC: {"20s": 7_570_000, "30s": 51_200_000, "40s": 43_420_000, "50_plus": 64_810_000},
    IRP: {"20s": 4_430_000, "30s": 29_960_000, "40s": 25_410_000, "50_plus": 37_930_000},
    PENSION_SAVINGS_FUND: {
        "20s": 1_680_000,
        "30s": 11_370_000,
        "40s": 9_650_000,
        "50_plus": 14_400_000,
    },
}
BALANCE_LOG_SIGMA = {DC: 0.90, IRP: 1.00, PENSION_SAVINGS_FUND: 1.10}

# Age patterns for risky assets. DC/IRP baselines are anchored to the KIRI age
# pattern and 2025 official aggregate performance-linked shares (33%, 44.3%).
# Scenario modifiers intentionally move the final synthetic means away from
# those market aggregates to create neglect, idle-cash, and overlap-risk cases.
RISKY_MEAN = {
    DC: {"20s": 0.409, "30s": 0.336, "40s": 0.321, "50_plus": 0.298},
    IRP: {"20s": 0.549, "30s": 0.451, "40s": 0.430, "50_plus": 0.399},
    PENSION_SAVINGS_FUND: {"20s": 0.70, "30s": 0.60, "40s": 0.50, "50_plus": 0.35},
}

RETURN_MEAN_PCT = {DC: 8.47, IRP: 9.44, PENSION_SAVINGS_FUND: 29.30}
RETURN_SD_ASSUMPTION = {DC: 5.69, IRP: 6.00, PENSION_SAVINGS_FUND: 12.00}

MONTHLY_CONTRIBUTION_MEAN_KRW = {
    DC: {"20s": 400_000, "30s": 600_000, "40s": 750_000, "50_plus": 800_000},
    IRP: {"20s": 150_000, "30s": 250_000, "40s": 300_000, "50_plus": 250_000},
    PENSION_SAVINGS_FUND: {
        "20s": 200_000,
        "30s": 350_000,
        "40s": 400_000,
        "50_plus": 350_000,
    },
}

RISK_PROFILES = (
    "CONSERVATIVE",
    "STABLE_GROWTH",
    "BALANCED",
    "GROWTH",
    "AGGRESSIVE",
)
RISK_PROFILE_WEIGHTS = {
    "20s": (0.10, 0.20, 0.30, 0.25, 0.15),
    "30s": (0.12, 0.23, 0.32, 0.23, 0.10),
    "40s": (0.18, 0.30, 0.30, 0.17, 0.05),
    "50_plus": (0.30, 0.35, 0.22, 0.10, 0.03),
}
PROFILE_RISK_TARGET = {
    "CONSERVATIVE": 0.15,
    "STABLE_GROWTH": 0.30,
    "BALANCED": 0.45,
    "GROWTH": 0.60,
    "AGGRESSIVE": 0.80,
}

SOURCES = {
    "KIRI_2025_20": {
        "kind": "official_research_survey",
        "use": "age weights, DC balance and asset-allocation age pattern",
        "url": "https://www.kiri.or.kr/report/downloadFile.do?docId=782989",
    },
    "MOEL_FSS_RETIREMENT_2025": {
        "kind": "official_aggregate",
        "use": "DC/IRP performance-linked shares and 2025 annual returns",
        "url": "https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19411",
    },
    "KOSTAT_RETIREMENT_2024": {
        "kind": "official_aggregate",
        "use": "IRP participants and assets for derived mean balance",
        "url": "https://www.kostat.go.kr/board.es?act=view&bid=11816&list_no=442406&mid=a10301060100",
    },
    "FSC_FSS_PSA_2025": {
        "kind": "official_aggregate",
        "use": "pension-savings-fund contracts, assets, and 2025 annual return",
        "url": "https://www.fsc.go.kr/no010101/87144",
    },
    "ASSUMPTION_V1": {
        "kind": "model_assumption",
        "use": "account combinations, dispersion, contributions, and within-account holdings",
        "url": None,
    },
}


def allocate_counts(total: int, weights: dict[str, float]) -> dict[str, int]:
    raw = {key: total * weight for key, weight in weights.items()}
    counts = {key: math.floor(value) for key, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(raw, key=lambda key: raw[key] - counts[key], reverse=True)
    for key in order[:remainder]:
        counts[key] += 1
    return counts


def weighted_choice(rng: random.Random, values: tuple[str, ...], weights: tuple[float, ...]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def account_types_for_scenario(rng: random.Random, scenario: str) -> list[str]:
    if scenario == "DC_NEGLECT":
        account_types = [DC]
        if rng.random() < 0.25:
            account_types.append(IRP)
        if rng.random() < 0.15:
            account_types.append(PENSION_SAVINGS_FUND)
    elif scenario == "TAX_BENEFIT_IDLE":
        primary = rng.choice((IRP, PENSION_SAVINGS_FUND))
        account_types = [primary]
        other = PENSION_SAVINGS_FUND if primary == IRP else IRP
        if rng.random() < 0.35:
            account_types.append(other)
        if rng.random() < 0.20:
            account_types.append(DC)
    else:
        account_types = list(
            rng.choices(
                population=(
                    (DC, IRP, PENSION_SAVINGS_FUND),
                    (DC, IRP),
                    (DC, PENSION_SAVINGS_FUND),
                    (IRP, PENSION_SAVINGS_FUND),
                ),
                weights=(0.60, 0.15, 0.15, 0.10),
                k=1,
            )[0]
        )
    return sorted(set(account_types), key=ALLOWED_ACCOUNT_TYPES.index)


def sample_beta(rng: random.Random, mean: float, concentration: float = 24.0) -> float:
    mean = min(max(mean, 0.001), 0.999)
    return rng.betavariate(mean * concentration, (1.0 - mean) * concentration)


def sample_allocation(
    rng: random.Random,
    account_type: str,
    age_group: str,
    risk_profile: str,
    scenario: str,
) -> tuple[float, float, float]:
    baseline = RISKY_MEAN[account_type][age_group]
    max_risky = 0.70 if account_type in (DC, IRP) else 0.95

    if scenario == "DC_NEGLECT" and account_type == DC:
        risky_mean = baseline * 0.35
        cash_ratio = rng.uniform(0.12, 0.30)
    elif scenario == "TAX_BENEFIT_IDLE" and account_type in (IRP, PENSION_SAVINGS_FUND):
        risky_mean = baseline * 0.35
        cash_ratio = rng.uniform(0.45, 0.70)
    elif scenario == "OVERLAP_RISK":
        risky_mean = max(baseline, PROFILE_RISK_TARGET[risk_profile])
        cash_ratio = rng.uniform(0.01, 0.05)
    else:
        risky_mean = baseline
        cash_ratio = rng.uniform(0.05, 0.15)

    risky_ratio = min(sample_beta(rng, risky_mean), max_risky, 1.0 - cash_ratio)
    safe_ratio = 1.0 - risky_ratio - cash_ratio
    return risky_ratio, safe_ratio, cash_ratio


def lognormal_with_mean(rng: random.Random, arithmetic_mean: float, sigma: float) -> float:
    mu = math.log(arithmetic_mean) - (sigma**2) / 2.0
    return rng.lognormvariate(mu, sigma)


def generate_records(user_count: int, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    age_groups = [
        group
        for group, count in allocate_counts(user_count, AGE_GROUP_WEIGHTS).items()
        for _ in range(count)
    ]
    scenarios = [
        scenario
        for scenario, count in allocate_counts(user_count, SCENARIO_WEIGHTS).items()
        for _ in range(count)
    ]
    rng.shuffle(age_groups)
    rng.shuffle(scenarios)

    users: list[dict] = []
    accounts: list[dict] = []
    account_number = 1

    for index, (age_group, scenario) in enumerate(zip(age_groups, scenarios), start=1):
        age = rng.randint(*AGE_RANGES[age_group])
        risk_profile = weighted_choice(rng, RISK_PROFILES, RISK_PROFILE_WEIGHTS[age_group])
        user_id = f"USR{index:05d}"
        users.append(
            {
                "user_id": user_id,
                "age": age,
                "age_group": age_group,
                "risk_profile": risk_profile,
                "mock_scenario": scenario,
                "data_kind": "MOCK",
                "source_ids": "KIRI_2025_20|ASSUMPTION_V1",
            }
        )

        for account_type in account_types_for_scenario(rng, scenario):
            risky_ratio, safe_ratio, cash_ratio = sample_allocation(
                rng, account_type, age_group, risk_profile, scenario
            )
            target_balance = BALANCE_MEAN_KRW[account_type][age_group]
            raw_balance = lognormal_with_mean(rng, target_balance, BALANCE_LOG_SIGMA[account_type])
            contribution_mean = MONTHLY_CONTRIBUTION_MEAN_KRW[account_type][age_group]
            monthly_contribution = lognormal_with_mean(rng, contribution_mean, 0.45)
            return_sensitivity = 18.0 if account_type in (DC, IRP) else 25.0
            raw_return = (
                RETURN_MEAN_PCT[account_type]
                + return_sensitivity * (risky_ratio - RISKY_MEAN[account_type][age_group])
                + rng.gauss(0.0, RETURN_SD_ASSUMPTION[account_type])
            )
            accounts.append(
                {
                    "account_id": f"ACC{account_number:06d}",
                    "user_id": user_id,
                    "account_type": account_type,
                    "age_group": age_group,
                    "raw_balance": raw_balance,
                    "balance_krw": 0,
                    "monthly_contribution_krw": int(round(monthly_contribution / 10_000) * 10_000),
                    "risky_asset_ratio": risky_ratio,
                    "safe_asset_ratio": safe_ratio,
                    "cash_ratio": cash_ratio,
                    "trailing_12m_return_pct": min(max(raw_return, -50.0), 80.0),
                    "return_period_end": "2025-12-31",
                    "data_kind": "MOCK",
                    "source_ids": account_source_ids(account_type),
                }
            )
            account_number += 1

    calibrate_balances(accounts)
    calibrate_returns(accounts)
    return users, accounts


def account_source_ids(account_type: str) -> str:
    if account_type == DC:
        return "KIRI_2025_20|MOEL_FSS_RETIREMENT_2025|ASSUMPTION_V1"
    if account_type == IRP:
        return "KOSTAT_RETIREMENT_2024|MOEL_FSS_RETIREMENT_2025|ASSUMPTION_V1"
    return "FSC_FSS_PSA_2025|ASSUMPTION_V1"


def calibrate_balances(accounts: list[dict]) -> None:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for account in accounts:
        groups[(account["account_type"], account["age_group"])].append(account)

    for (account_type, age_group), group in groups.items():
        raw_mean = statistics.fmean(account["raw_balance"] for account in group)
        scale = BALANCE_MEAN_KRW[account_type][age_group] / raw_mean
        for account in group:
            account["balance_krw"] = max(10_000, int(round(account["raw_balance"] * scale / 10_000) * 10_000))
            del account["raw_balance"]


def calibrate_returns(accounts: list[dict]) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for account in accounts:
        groups[account["account_type"]].append(account)

    for account_type, group in groups.items():
        delta = RETURN_MEAN_PCT[account_type] - statistics.fmean(
            account["trailing_12m_return_pct"] for account in group
        )
        for account in group:
            account["trailing_12m_return_pct"] = round(
                account["trailing_12m_return_pct"] + delta, 2
            )


def build_holdings(accounts: list[dict]) -> list[dict]:
    holdings: list[dict] = []
    global_share_by_age = {"20s": 0.65, "30s": 0.55, "40s": 0.40, "50_plus": 0.30}

    for account in accounts:
        risky = account["risky_asset_ratio"]
        safe = account["safe_asset_ratio"]
        cash = account["cash_ratio"]
        global_share = global_share_by_age[account["age_group"]]
        weights = [
            ("EQUITY_KR", risky * (1.0 - global_share)),
            ("EQUITY_GLOBAL", risky * global_share),
            ("BOND", safe if account["account_type"] == PENSION_SAVINGS_FUND else safe * 0.30),
        ]
        if account["account_type"] in (DC, IRP):
            weights.append(("PRINCIPAL_GUARANTEED", safe * 0.70))
        weights.append(("CASH", cash))

        normalized_total = sum(weight for _, weight in weights)
        normalized = [(asset, weight / normalized_total) for asset, weight in weights]
        rounded_weights: list[tuple[str, float]] = []
        running_weight = 0.0
        for asset, weight in normalized[:-1]:
            rounded = round(weight, 6)
            rounded_weights.append((asset, rounded))
            running_weight += rounded
        rounded_weights.append((normalized[-1][0], round(1.0 - running_weight, 6)))

        running_amount = 0
        for index, (asset_class, weight) in enumerate(rounded_weights):
            if index == len(rounded_weights) - 1:
                amount = account["balance_krw"] - running_amount
            else:
                amount = int(round(account["balance_krw"] * weight))
                running_amount += amount
            holdings.append(
                {
                    "account_id": account["account_id"],
                    "asset_class": asset_class,
                    "weight": f"{weight:.6f}",
                    "amount_krw": amount,
                    "data_kind": "MOCK",
                    "source_ids": account["source_ids"],
                }
            )
    return holdings


def validate_and_summarize(
    users: list[dict], accounts: list[dict], holdings: list[dict], expected_users: int, seed: int
) -> dict:
    errors: list[str] = []
    user_ids = {user["user_id"] for user in users}
    if len(users) != expected_users or len(user_ids) != expected_users:
        errors.append("user count or uniqueness mismatch")

    account_count_by_user = Counter(account["user_id"] for account in accounts)
    missing_accounts = user_ids - set(account_count_by_user)
    if missing_accounts:
        errors.append(f"users without accounts: {len(missing_accounts)}")
    unknown_users = set(account_count_by_user) - user_ids
    if unknown_users:
        errors.append(f"accounts with unknown users: {len(unknown_users)}")

    invalid_types = sorted({account["account_type"] for account in accounts} - set(ALLOWED_ACCOUNT_TYPES))
    if invalid_types:
        errors.append(f"invalid account types: {invalid_types}")

    for account in accounts:
        if account["account_type"] in (DC, IRP) and account["risky_asset_ratio"] > 0.7000001:
            errors.append(f"risk cap exceeded: {account['account_id']}")
            break
        ratio_sum = (
            account["risky_asset_ratio"] + account["safe_asset_ratio"] + account["cash_ratio"]
        )
        if not math.isclose(ratio_sum, 1.0, abs_tol=1e-9):
            errors.append(f"account ratios do not sum to 1: {account['account_id']}")
            break

    holdings_by_account: dict[str, list[dict]] = defaultdict(list)
    for holding in holdings:
        holdings_by_account[holding["account_id"]].append(holding)
    account_ids = {account["account_id"] for account in accounts}
    unknown_holding_accounts = set(holdings_by_account) - account_ids
    if unknown_holding_accounts:
        errors.append(f"holdings with unknown accounts: {len(unknown_holding_accounts)}")
    for account in accounts:
        rows = holdings_by_account[account["account_id"]]
        if not rows:
            errors.append(f"account without holdings: {account['account_id']}")
            break
        if account["account_type"] == PENSION_SAVINGS_FUND and any(
            row["asset_class"] == "PRINCIPAL_GUARANTEED" for row in rows
        ):
            errors.append(f"principal-guaranteed holding in pension savings fund: {account['account_id']}")
            break
        if not math.isclose(sum(float(row["weight"]) for row in rows), 1.0, abs_tol=1e-6):
            errors.append(f"holding weights do not sum to 1: {account['account_id']}")
            break
        if sum(row["amount_krw"] for row in rows) != account["balance_krw"]:
            errors.append(f"holding amounts do not match balance: {account['account_id']}")
            break

    type_stats = {}
    for account_type in ALLOWED_ACCOUNT_TYPES:
        group = [account for account in accounts if account["account_type"] == account_type]
        balances = [account["balance_krw"] for account in group]
        returns = [account["trailing_12m_return_pct"] for account in group]
        type_stats[account_type] = {
            "accounts": len(group),
            "mean_balance_krw": round(statistics.fmean(balances)),
            "balance_population_sd_krw": round(statistics.pstdev(balances)),
            "mean_trailing_12m_return_pct": round(statistics.fmean(returns), 2),
            "return_population_sd_pct": round(statistics.pstdev(returns), 2),
            "mean_risky_asset_ratio": round(
                statistics.fmean(account["risky_asset_ratio"] for account in group), 4
            ),
        }

    age_type_mean_balance = {}
    for account_type in ALLOWED_ACCOUNT_TYPES:
        age_type_mean_balance[account_type] = {}
        for age_group in AGE_GROUP_WEIGHTS:
            group = [
                account
                for account in accounts
                if account["account_type"] == account_type and account["age_group"] == age_group
            ]
            age_type_mean_balance[account_type][age_group] = round(
                statistics.fmean(account["balance_krw"] for account in group)
            )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "seed": seed,
        "users": len(users),
        "accounts": len(accounts),
        "holdings": len(holdings),
        "allowed_account_types": list(ALLOWED_ACCOUNT_TYPES),
        "scenario_counts": dict(sorted(Counter(user["mock_scenario"] for user in users).items())),
        "age_group_counts": dict(sorted(Counter(user["age_group"] for user in users).items())),
        "account_type_stats": type_stats,
        "age_type_mean_balance_krw": age_type_mean_balance,
        "assumption_note": "Dispersion, account combinations, contributions, and detailed holdings are model assumptions.",
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def generate(output_dir: Path, user_count: int = 10_000, seed: int = 20260714) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    users, accounts = generate_records(user_count, seed)
    holdings = build_holdings(accounts)
    summary = validate_and_summarize(users, accounts, holdings, user_count, seed)
    if summary["status"] != "PASS":
        raise ValueError("Generated data failed validation: " + "; ".join(summary["errors"]))

    write_csv(
        output_dir / "users.csv",
        users,
        ["user_id", "age", "age_group", "risk_profile", "mock_scenario", "data_kind", "source_ids"],
    )
    write_csv(
        output_dir / "accounts.csv",
        accounts,
        [
            "account_id",
            "user_id",
            "account_type",
            "balance_krw",
            "monthly_contribution_krw",
            "risky_asset_ratio",
            "safe_asset_ratio",
            "cash_ratio",
            "trailing_12m_return_pct",
            "return_period_end",
            "data_kind",
            "source_ids",
        ],
    )
    write_csv(
        output_dir / "holdings.csv",
        holdings,
        ["account_id", "asset_class", "weight", "amount_krw", "data_kind", "source_ids"],
    )
    (output_dir / "sources.json").write_text(
        json.dumps(SOURCES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--output-dir", type=Path, default=Path("data/mock"))
    args = parser.parse_args()
    summary = generate(args.output_dir, args.users, args.seed)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
