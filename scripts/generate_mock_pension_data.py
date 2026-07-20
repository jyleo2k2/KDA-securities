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
SALARIED_EMPLOYEE = "SALARIED_EMPLOYEE"
SELF_EMPLOYED = "SELF_EMPLOYED"
FREELANCER = "FREELANCER"

SCENARIO_WEIGHTS = {
    "DC_NEGLECT": 0.40,
    "TAX_BENEFIT_IDLE": 0.30,
    "OVERLAP_RISK": 0.30,
}
EMPLOYMENT_TYPE_WEIGHTS_BY_SCENARIO = {
    "DC_NEGLECT": {SALARIED_EMPLOYEE: 1.00},
    "TAX_BENEFIT_IDLE": {
        SALARIED_EMPLOYEE: 0.65,
        SELF_EMPLOYED: 0.18,
        FREELANCER: 0.17,
    },
    "OVERLAP_RISK": {
        SALARIED_EMPLOYEE: 0.65,
        SELF_EMPLOYED: 0.18,
        FREELANCER: 0.17,
    },
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
    IRP: {
        "20s": 4_430_000,
        "30s": 29_960_000,
        "40s": 25_410_000,
        "50_plus": 37_930_000,
    },
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

# Annual income is a synthetic driver, not an observed customer attribute. The
# age means are calibrated so that DC's legal monthly equivalent (income / 144)
# is close to the 2024 aggregate benchmark of KRW 511,000.
GROSS_SALARY_MEAN_KRW = {
    "20s": 42_000_000,
    "30s": 64_000_000,
    "40s": 80_000_000,
    "50_plus": 88_000_000,
}
COMPREHENSIVE_INCOME_MEAN_KRW = {
    SELF_EMPLOYED: {
        "20s": 30_000_000,
        "30s": 45_000_000,
        "40s": 55_000_000,
        "50_plus": 60_000_000,
    },
    FREELANCER: {
        "20s": 24_000_000,
        "30s": 36_000_000,
        "40s": 45_000_000,
        "50_plus": 50_000_000,
    },
}
INCOME_LOG_SIGMA = 0.38

# 2020 National Tax Statistics-based active-contributor monthly equivalents.
# Pension-savings figures cover all pension-savings products and are used as a
# proxy for pension-savings-fund because a fund-only contribution cross-tab is
# not publicly available.
ACTIVE_CONTRIBUTION_MEAN_KRW = {
    IRP: (
        (20_000_000, 56_000),
        (40_000_000, 153_000),
        (60_000_000, 214_000),
        (80_000_000, 263_000),
        (100_000_000, 300_000),
        (math.inf, 331_000),
    ),
    PENSION_SAVINGS_FUND: (
        (20_000_000, 65_000),
        (40_000_000, 166_000),
        (60_000_000, 207_000),
        (80_000_000, 244_000),
        (100_000_000, 264_000),
        (math.inf, 227_000),
    ),
}
CONTRIBUTION_ACTIVE_RATE = {IRP: 0.52, PENSION_SAVINGS_FUND: 0.63}
# The IRP scale reconciles the income-band pattern with the separate 2021
# active additional-contributor mean of about KRW 421,000 per month.
ACTIVE_CONTRIBUTION_SCALE = {IRP: 1.65, PENSION_SAVINGS_FUND: 1.00}
CONTRIBUTION_FREQUENCY_WEIGHTS = {
    "MONTHLY": 0.75,
    "QUARTERLY": 0.15,
    "ANNUAL_LUMP_SUM": 0.10,
}

TAX_YEAR = 2025
GROSS_SALARY_TAX_CREDIT_THRESHOLD_KRW = 55_000_000
COMPREHENSIVE_INCOME_TAX_CREDIT_THRESHOLD_KRW = 45_000_000
TAX_CREDIT_RATE_WITH_LOCAL = {"LOWER_INCOME": 0.165, "HIGHER_INCOME": 0.132}
PENSION_SAVINGS_TAX_CREDIT_LIMIT_KRW = 6_000_000
COMBINED_PENSION_TAX_CREDIT_LIMIT_KRW = 9_000_000
COMBINED_PERSONAL_PENSION_CONTRIBUTION_LIMIT_KRW = 18_000_000
PRIVATE_PENSION_SEPARATE_TAX_THRESHOLD_KRW = 15_000_000

PROFILE_RISK_TARGET = {
    "STABLE": 0.15,
    "STABLE_SEEKING": 0.30,
    "RISK_NEUTRAL": 0.45,
    "ACTIVE": 0.60,
    "AGGRESSIVE": 0.80,
}

# KEF's 2025 employee survey reports four preferred retirement-fund management
# types. They are preserved as their own field and mapped to the closest four
# bands of the service's five-band RiskProfile vocabulary. The survey has no
# separate "aggressive" category, so it is not synthesized from unsupported data.
PREFERRED_MANAGEMENT_WEIGHTS = {
    "PRINCIPAL_GUARANTEED": 0.225,
    "STABLE_INVESTMENT": 0.501,
    "NEUTRAL_INVESTMENT": 0.212,
    "ACTIVE_INVESTMENT": 0.062,
}
PREFERRED_MANAGEMENT_TO_RISK_PROFILE = {
    "PRINCIPAL_GUARANTEED": "STABLE",
    "STABLE_INVESTMENT": "STABLE_SEEKING",
    "NEUTRAL_INVESTMENT": "RISK_NEUTRAL",
    "ACTIVE_INVESTMENT": "ACTIVE",
}
RETIREMENT_FUND_ATTITUDE_WEIGHTS = {
    "20s": {
        "STABILITY_FIRST": 0.616,
        "PARTIAL_INVESTMENT": 0.320,
        "ACTIVE": 0.064,
    },
    "30s": {
        "STABILITY_FIRST": 0.524,
        "PARTIAL_INVESTMENT": 0.369,
        "ACTIVE": 0.107,
    },
    "40s": {
        "STABILITY_FIRST": 0.636,
        "PARTIAL_INVESTMENT": 0.292,
        "ACTIVE": 0.072,
    },
    "50_plus": {
        "STABILITY_FIRST": 0.737,
        "PARTIAL_INVESTMENT": 0.227,
        "ACTIVE": 0.036,
    },
}
INVESTMENT_READINESS_WEIGHTS = {
    "NEEDS_GUIDANCE": 0.571,
    "INFORMED": 0.336,
    "DISENGAGED": 0.093,
}
PAYOUT_PREFERENCE_WEIGHTS = {
    "20s": {"MIXED": 0.396, "ANNUITY": 0.272, "LUMP_SUM": 0.332},
    "30s": {"MIXED": 0.425, "ANNUITY": 0.293, "LUMP_SUM": 0.282},
    "40s": {"MIXED": 0.404, "ANNUITY": 0.300, "LUMP_SUM": 0.296},
    "50_plus": {"MIXED": 0.283, "ANNUITY": 0.426, "LUMP_SUM": 0.291},
}
PRIMARY_OUTSIDE_ASSET_WEIGHTS = {
    "DEPOSIT_SAVINGS": 0.319,
    "SECURITIES": 0.235,
    "INSURANCE_PENSION": 0.180,
    "GOLD_FX": 0.105,
    "REAL_ESTATE": 0.083,
    "CRYPTO": 0.048,
    "NONE": 0.030,
}

SOURCES = {
    "KIRI_2025_20": {
        "kind": "official_research_survey",
        "use": "age weights, DC balance and asset-allocation age pattern",
        "url": "https://www.kiri.or.kr/report/downloadFile.do?docId=782989",
    },
    "MOEL_FSS_RETIREMENT_2025": {
        "kind": "official_aggregate",
        "use": (
            "DC/IRP performance-linked shares, 2025 annual returns, and "
            "top/bottom return-group asset composition"
        ),
        "reference_file": (
            "260520_보도자료_2025년퇴직연금 투자 백서(관계부처합동) (1).pdf"
        ),
        "pdf_pages_used": [7, 16, 18],
        "url": "https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19411",
    },
    "KEF_RETIREMENT_AWARENESS_2025": {
        "kind": "employee_survey",
        "use": (
            "preferred management type, retirement-fund attitude, investment "
            "readiness, payout preference, and primary outside investment asset"
        ),
        "reference_file": "[경총_보고서] 2025 직장인 퇴직연금 인식조사.pdf",
        "survey_period": "2025-06-02/2025-06-13",
        "sample_size": 1003,
        "pdf_pages_used": [4, 5, 6, 8, 9],
        "url": None,
    },
    "KOSTAT_RETIREMENT_2024": {
        "kind": "official_aggregate",
        "use": "IRP participants and assets for derived mean balance",
        "url": "https://www.kostat.go.kr/board.es?act=view&bid=11816&list_no=442406&mid=a10301060100",
    },
    "FSC_FSS_PSA_2025": {
        "kind": "official_aggregate",
        "use": (
            "pension-savings-fund contracts, assets, and 2025 annual return; "
            "all-product pension-savings contributions and participants"
        ),
        "url": "https://www.fsc.go.kr/no010101/87144",
    },
    "RETIREMENT_CONTRIBUTION_2024": {
        "kind": "official_joint_whitepaper",
        "use": "2024 DC employer and IRP participant annual contribution totals",
        "url": "https://kiri.or.kr/PDF/weeklytrend/20250623/trend20250623_1.pdf",
    },
    "KIRI_PENSION_CONTRIBUTION_2022": {
        "kind": "official_research",
        "use": (
            "2020 IRP and pension-savings active-contributor annual means by "
            "income band, based on National Tax Statistics"
        ),
        "url": "https://www.kiri.or.kr/report/downloadFile.do?docId=147139",
    },
    "KIRI_REPLACEMENT_RATE_2023": {
        "kind": "official_research",
        "use": "2021 IRP active additional-contributor annual mean",
        "url": "https://www.kiri.or.kr/report/downloadFile.do?docId=345589",
    },
    "NTS_PENSION_TAX_2025": {
        "kind": "official_tax_rule",
        "use": (
            "pension-account tax-credit limits and gross-salary KRW 55 million / "
            "comprehensive-income KRW 45 million rate boundaries; private-pension "
            "withholding rates and KRW 15 million annual threshold"
        ),
        "url": "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7875&mi=6596",
        "pension_income_url": (
            "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7888&mi=6452"
        ),
    },
    "INCOME_TAX_DECREE_PENSION_RECEIPT": {
        "kind": "official_law",
        "use": "age 55 and five-year holding requirements for pension receipt",
        "url": "https://www.law.go.kr/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=1001059447",
    },
    "ASSUMPTION_V1": {
        "kind": "model_assumption",
        "use": (
            "account combinations, dispersion, contributions, "
            "and within-account holdings"
        ),
        "url": None,
    },
    "ASSUMPTION_V2": {
        "kind": "model_assumption",
        "use": (
            "map KEF four management types to the closest service risk-profile "
            "bands and apply the survey's 50s cross-tabs to ages 50-64"
        ),
        "url": None,
    },
    "ASSUMPTION_CONTRIBUTION_V1": {
        "kind": "model_assumption",
        "use": (
            "synthetic annual-income distribution, contribution activity rates, "
            "frequency mix, dispersion, and pension-savings-fund proxy mapping"
        ),
        "url": None,
    },
    "ASSUMPTION_TAX_SCENARIO_V1": {
        "kind": "model_assumption",
        "use": (
            "employment-type mix, gross-salary and comprehensive-income "
            "distributions, account tenure, planned pension start age and receipt "
            "period, and current-balance-only planned receipt amount; IRP source "
            "composition is not available, so tax treatment is indicative"
        ),
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


def shuffled_labels(
    rng: random.Random, total: int, weights: dict[str, float]
) -> list[str]:
    labels = [
        label
        for label, count in allocate_counts(total, weights).items()
        for _ in range(count)
    ]
    rng.shuffle(labels)
    return labels


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
    profile_adjusted_mean = (baseline + PROFILE_RISK_TARGET[risk_profile]) / 2.0

    if scenario == "DC_NEGLECT" and account_type == DC:
        risky_mean = profile_adjusted_mean * 0.35
        cash_ratio = rng.uniform(0.12, 0.30)
    elif scenario == "TAX_BENEFIT_IDLE" and account_type in (IRP, PENSION_SAVINGS_FUND):
        risky_mean = profile_adjusted_mean * 0.35
        cash_ratio = rng.uniform(0.45, 0.70)
    elif scenario == "OVERLAP_RISK":
        risky_mean = min(
            max(
                profile_adjusted_mean * 1.25,
                PROFILE_RISK_TARGET[risk_profile],
            ),
            max_risky,
        )
        cash_ratio = rng.uniform(0.01, 0.05)
    else:
        risky_mean = profile_adjusted_mean
        cash_ratio = rng.uniform(0.05, 0.15)

    risky_ratio = min(sample_beta(rng, risky_mean), max_risky, 1.0 - cash_ratio)
    safe_ratio = 1.0 - risky_ratio - cash_ratio
    return risky_ratio, safe_ratio, cash_ratio


def lognormal_with_mean(
    rng: random.Random, arithmetic_mean: float, sigma: float
) -> float:
    mu = math.log(arithmetic_mean) - (sigma**2) / 2.0
    return rng.lognormvariate(mu, sigma)


def round_to_10k(value: float) -> int:
    return int(round(value / 10_000) * 10_000)


def income_band_contribution_mean(account_type: str, annual_income: int) -> int:
    for upper_bound, monthly_mean in ACTIVE_CONTRIBUTION_MEAN_KRW[account_type]:
        if annual_income <= upper_bound:
            return monthly_mean
    raise ValueError(f"no contribution income band: {annual_income}")


def sample_contribution(
    rng: random.Random, account_type: str, annual_income: int
) -> tuple[int, int, str, str]:
    if account_type == DC:
        monthly_equivalent = round_to_10k(annual_income / 144)
        return (
            monthly_equivalent,
            monthly_equivalent * 12,
            "ACTIVE",
            "MONTHLY_EQUIVALENT",
        )

    if rng.random() >= CONTRIBUTION_ACTIVE_RATE[account_type]:
        return 0, 0, "INACTIVE", "NONE"

    active_mean = (
        income_band_contribution_mean(account_type, annual_income)
        * ACTIVE_CONTRIBUTION_SCALE[account_type]
    )
    monthly_equivalent = max(
        10_000, round_to_10k(lognormal_with_mean(rng, active_mean, 0.45))
    )
    frequency = rng.choices(
        population=tuple(CONTRIBUTION_FREQUENCY_WEIGHTS),
        weights=tuple(CONTRIBUTION_FREQUENCY_WEIGHTS.values()),
        k=1,
    )[0]
    return monthly_equivalent, monthly_equivalent * 12, "ACTIVE", frequency


def tax_credit_rate(income_basis: str, income_amount: int) -> float:
    threshold = (
        GROSS_SALARY_TAX_CREDIT_THRESHOLD_KRW
        if income_basis == "GROSS_SALARY"
        else COMPREHENSIVE_INCOME_TAX_CREDIT_THRESHOLD_KRW
    )
    income_band = "LOWER_INCOME" if income_amount <= threshold else "HIGHER_INCOME"
    return TAX_CREDIT_RATE_WITH_LOCAL[income_band]


def cap_personal_pension_contributions(accounts: list[dict]) -> None:
    """Apply the annual KRW 18m IRP + pension-savings contribution limit.

    Contributions are generated as KRW 10k monthly equivalents. When the two
    personal-pension accounts exceed KRW 1.5m per month, the cap is allocated
    proportionally and any remaining KRW 10k units are assigned by fractional
    remainder and stable account id.
    """

    personal_accounts_by_user: dict[str, list[dict]] = defaultdict(list)
    for account in accounts:
        if account["account_type"] in (IRP, PENSION_SAVINGS_FUND):
            personal_accounts_by_user[account["user_id"]].append(account)

    monthly_limit = COMBINED_PERSONAL_PENSION_CONTRIBUTION_LIMIT_KRW // 12
    unit = 10_000
    for user_accounts in personal_accounts_by_user.values():
        total_monthly = sum(
            account["monthly_contribution_krw"] for account in user_accounts
        )
        if total_monthly <= monthly_limit:
            continue

        allocations: list[tuple[dict, int, float]] = []
        allocated = 0
        for account in user_accounts:
            exact_units = (
                account["monthly_contribution_krw"]
                * monthly_limit
                / total_monthly
                / unit
            )
            whole_units = math.floor(exact_units)
            monthly = whole_units * unit
            allocations.append((account, monthly, exact_units - whole_units))
            allocated += monthly

        remaining_units = (monthly_limit - allocated) // unit
        ranked = sorted(allocations, key=lambda item: (-item[2], item[0]["account_id"]))
        bonus_ids = {item[0]["account_id"] for item in ranked[:remaining_units]}
        for account, monthly, _ in allocations:
            if account["account_id"] in bonus_ids:
                monthly += unit
            account["monthly_contribution_krw"] = monthly
            account["annual_contribution_krw"] = monthly * 12
            account["contribution_status"] = "ACTIVE" if monthly else "INACTIVE"
            if monthly == 0:
                account["contribution_frequency"] = "NONE"


def planned_pension_tax_rate(planned_start_age: int) -> float:
    if planned_start_age < 70:
        return 5.5
    if planned_start_age < 80:
        return 4.4
    return 3.3


def sample_planned_receipt(
    rng: random.Random, age: int, payout_preference: str
) -> tuple[int, int]:
    start_age_choices = {
        "ANNUITY": ((60, 65, 70), (0.20, 0.60, 0.20)),
        "MIXED": ((60, 65, 70), (0.35, 0.50, 0.15)),
        "LUMP_SUM": ((55, 60, 65), (0.50, 0.40, 0.10)),
    }
    receipt_year_choices = {
        "ANNUITY": ((20, 25, 30), (0.30, 0.50, 0.20)),
        "MIXED": ((10, 15, 20), (0.30, 0.50, 0.20)),
        "LUMP_SUM": ((1,), (1.0,)),
    }
    ages, age_weights = start_age_choices[payout_preference]
    planned_start_age = rng.choices(ages, weights=age_weights, k=1)[0]
    next_five_year_age = max(55, math.ceil((age + 1) / 5) * 5)
    planned_start_age = max(planned_start_age, next_five_year_age)
    years, year_weights = receipt_year_choices[payout_preference]
    planned_receipt_years = rng.choices(years, weights=year_weights, k=1)[0]
    return planned_start_age, planned_receipt_years


def apply_tax_scenarios(
    users: list[dict], accounts: list[dict], rng: random.Random
) -> None:
    users_by_id = {user["user_id"]: user for user in users}
    accounts_by_user: dict[str, list[dict]] = defaultdict(list)

    for account in accounts:
        user = users_by_id[account["user_id"]]
        max_years = max(1, min(40, user["age"] - 19))
        contribution_years = max(
            1,
            round(rng.triangular(1, max_years, max(1, max_years * 0.65))),
        )
        account["contribution_years"] = contribution_years
        account["account_open_year"] = TAX_YEAR - contribution_years + 1
        account["tax_credit_eligible_contribution_krw"] = 0
        account["estimated_tax_credit_krw"] = 0
        accounts_by_user[account["user_id"]].append(account)

    for user in users:
        planned_start_age, planned_receipt_years = sample_planned_receipt(
            rng, user["age"], user["payout_preference"]
        )
        user["tax_year"] = TAX_YEAR
        user["pension_tax_credit_rate_pct"] = round(
            tax_credit_rate(
                user["tax_credit_income_basis"],
                user["tax_credit_income_amount_krw"],
            )
            * 100,
            1,
        )
        user["planned_pension_start_age"] = planned_start_age
        user["planned_receipt_years"] = planned_receipt_years
        user["planned_low_rate_pension_tax_pct"] = planned_pension_tax_rate(
            planned_start_age
        )

        user_accounts = accounts_by_user[user["user_id"]]
        pension_savings_accounts = [
            account
            for account in user_accounts
            if account["account_type"] == PENSION_SAVINGS_FUND
        ]
        irp_accounts = [
            account for account in user_accounts if account["account_type"] == IRP
        ]

        user["pension_savings_contribution_krw"] = sum(
            account["annual_contribution_krw"] for account in pension_savings_accounts
        )
        user["irp_contribution_krw"] = sum(
            account["annual_contribution_krw"] for account in irp_accounts
        )

        remaining_limit = COMBINED_PENSION_TAX_CREDIT_LIMIT_KRW
        for account in pension_savings_accounts:
            eligible = min(
                account["annual_contribution_krw"],
                PENSION_SAVINGS_TAX_CREDIT_LIMIT_KRW,
                remaining_limit,
            )
            account["tax_credit_eligible_contribution_krw"] = eligible
            remaining_limit -= eligible
        for account in irp_accounts:
            eligible = min(account["annual_contribution_krw"], remaining_limit)
            account["tax_credit_eligible_contribution_krw"] = eligible
            remaining_limit -= eligible

        rate = tax_credit_rate(
            user["tax_credit_income_basis"],
            user["tax_credit_income_amount_krw"],
        )
        for account in user_accounts:
            eligible = account["tax_credit_eligible_contribution_krw"]
            account["estimated_tax_credit_krw"] = round(eligible * rate)
            years_at_receipt = account["contribution_years"] + (
                planned_start_age - user["age"]
            )
            account["planned_contribution_years_at_receipt"] = years_at_receipt
            if user["payout_preference"] == "LUMP_SUM":
                receipt_eligibility = "NOT_APPLICABLE_LUMP_SUM"
            elif years_at_receipt >= 5:
                receipt_eligibility = "ELIGIBLE"
            elif account["account_type"] == DC:
                receipt_eligibility = "DEFERRED_RETIREMENT_EXCEPTION_REVIEW"
            else:
                receipt_eligibility = "FIVE_YEAR_REQUIREMENT_NOT_MET"
            account["pension_receipt_eligibility"] = receipt_eligibility
            if user["payout_preference"] == "LUMP_SUM":
                planned_receipt = account["balance_krw"]
            else:
                planned_receipt = round_to_10k(
                    account["balance_krw"] / planned_receipt_years
                )
            account["planned_annual_pension_receipt_krw"] = planned_receipt

        personal_receipt = sum(
            account["planned_annual_pension_receipt_krw"]
            for account in user_accounts
            if account["account_type"] in (IRP, PENSION_SAVINGS_FUND)
        )
        total_receipt = sum(
            account["planned_annual_pension_receipt_krw"] for account in user_accounts
        )
        if user["payout_preference"] == "LUMP_SUM":
            treatment = "NON_PENSION_WITHDRAWAL_REVIEW"
        elif personal_receipt <= PRIVATE_PENSION_SEPARATE_TAX_THRESHOLD_KRW:
            treatment = "LOW_RATE_SEPARATE_TAX"
        else:
            treatment = "COMPREHENSIVE_OR_16_5_SEPARATE_CHOICE"

        user["total_tax_credit_eligible_contribution_krw"] = sum(
            account["tax_credit_eligible_contribution_krw"] for account in user_accounts
        )
        user["estimated_pension_tax_credit_krw"] = sum(
            account["estimated_tax_credit_krw"] for account in user_accounts
        )
        user["planned_annual_total_pension_receipt_krw"] = total_receipt
        user["planned_annual_personal_pension_receipt_krw"] = personal_receipt
        user["planned_receipt_tax_treatment"] = treatment

        for account in user_accounts:
            if account["account_type"] == DC:
                account["planned_receipt_tax_treatment"] = (
                    "DEFERRED_RETIREMENT_INCOME_RULE"
                )
            else:
                account["planned_receipt_tax_treatment"] = treatment


def generate_records(user_count: int, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    attribute_rng = random.Random(seed + 1)
    tax_rng = random.Random(seed + 2)
    age_group_counts = allocate_counts(user_count, AGE_GROUP_WEIGHTS)
    age_groups = [
        group for group, count in age_group_counts.items() for _ in range(count)
    ]
    scenario_counts = allocate_counts(user_count, SCENARIO_WEIGHTS)
    scenarios = [
        scenario for scenario, count in scenario_counts.items() for _ in range(count)
    ]
    rng.shuffle(age_groups)
    rng.shuffle(scenarios)

    preferred_management_types = shuffled_labels(
        attribute_rng, user_count, PREFERRED_MANAGEMENT_WEIGHTS
    )
    investment_readiness = shuffled_labels(
        attribute_rng, user_count, INVESTMENT_READINESS_WEIGHTS
    )
    primary_outside_assets = shuffled_labels(
        attribute_rng, user_count, PRIMARY_OUTSIDE_ASSET_WEIGHTS
    )
    employment_types_by_scenario = {
        scenario: shuffled_labels(
            attribute_rng,
            scenario_counts[scenario],
            EMPLOYMENT_TYPE_WEIGHTS_BY_SCENARIO[scenario],
        )
        for scenario in SCENARIO_WEIGHTS
    }
    retirement_fund_attitudes = {
        group: shuffled_labels(
            attribute_rng,
            age_group_counts[group],
            RETIREMENT_FUND_ATTITUDE_WEIGHTS[group],
        )
        for group in AGE_GROUP_WEIGHTS
    }
    payout_preferences = {
        group: shuffled_labels(
            attribute_rng, age_group_counts[group], PAYOUT_PREFERENCE_WEIGHTS[group]
        )
        for group in AGE_GROUP_WEIGHTS
    }

    users: list[dict] = []
    accounts: list[dict] = []
    account_number = 1

    for index, (
        age_group,
        scenario,
        preferred_management_type,
        readiness,
        outside_asset,
    ) in enumerate(
        zip(
            age_groups,
            scenarios,
            preferred_management_types,
            investment_readiness,
            primary_outside_assets,
            strict=True,
        ),
        start=1,
    ):
        age = rng.randint(*AGE_RANGES[age_group])
        risk_profile = PREFERRED_MANAGEMENT_TO_RISK_PROFILE[preferred_management_type]
        user_id = f"USR{index:05d}"
        employment_type = employment_types_by_scenario[scenario].pop()
        if employment_type == SALARIED_EMPLOYEE:
            gross_salary = max(
                12_000_000,
                round_to_10k(
                    lognormal_with_mean(
                        rng,
                        GROSS_SALARY_MEAN_KRW[age_group],
                        INCOME_LOG_SIGMA,
                    )
                ),
            )
            comprehensive_income = None
            tax_credit_income_basis = "GROSS_SALARY"
            tax_credit_income_amount = gross_salary
        else:
            gross_salary = None
            comprehensive_income = max(
                8_000_000,
                round_to_10k(
                    lognormal_with_mean(
                        rng,
                        COMPREHENSIVE_INCOME_MEAN_KRW[employment_type][age_group],
                        INCOME_LOG_SIGMA,
                    )
                ),
            )
            tax_credit_income_basis = "COMPREHENSIVE_INCOME"
            tax_credit_income_amount = comprehensive_income
        users.append(
            {
                "user_id": user_id,
                "age": age,
                "age_group": age_group,
                "employment_type": employment_type,
                "gross_salary_krw": gross_salary,
                "comprehensive_income_krw": comprehensive_income,
                "tax_credit_income_basis": tax_credit_income_basis,
                "tax_credit_income_amount_krw": tax_credit_income_amount,
                "risk_profile": risk_profile,
                "preferred_management_type": preferred_management_type,
                "retirement_fund_attitude": retirement_fund_attitudes[age_group].pop(),
                "investment_readiness": readiness,
                "payout_preference": payout_preferences[age_group].pop(),
                "primary_outside_asset": outside_asset,
                "mock_scenario": scenario,
                "data_kind": "MOCK",
                "source_ids": (
                    "KIRI_2025_20|KEF_RETIREMENT_AWARENESS_2025|"
                    "NTS_PENSION_TAX_2025|INCOME_TAX_DECREE_PENSION_RECEIPT|"
                    "ASSUMPTION_V1|ASSUMPTION_V2|ASSUMPTION_CONTRIBUTION_V1|"
                    "ASSUMPTION_TAX_SCENARIO_V1"
                ),
            }
        )

        account_types = account_types_for_scenario(rng, scenario)
        if employment_type != SALARIED_EMPLOYEE:
            account_types = [
                account_type for account_type in account_types if account_type != DC
            ]
        for account_type in account_types:
            risky_ratio, safe_ratio, cash_ratio = sample_allocation(
                rng, account_type, age_group, risk_profile, scenario
            )
            target_balance = BALANCE_MEAN_KRW[account_type][age_group]
            raw_balance = lognormal_with_mean(
                rng, target_balance, BALANCE_LOG_SIGMA[account_type]
            )
            (
                monthly_contribution,
                annual_contribution,
                contribution_status,
                contribution_frequency,
            ) = sample_contribution(rng, account_type, tax_credit_income_amount)
            return_sensitivity = 18.0 if account_type in (DC, IRP) else 25.0
            raw_return = (
                RETURN_MEAN_PCT[account_type]
                + return_sensitivity
                * (risky_ratio - RISKY_MEAN[account_type][age_group])
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
                    "monthly_contribution_krw": monthly_contribution,
                    "annual_contribution_krw": annual_contribution,
                    "contribution_status": contribution_status,
                    "contribution_frequency": contribution_frequency,
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
    cap_personal_pension_contributions(accounts)
    apply_tax_scenarios(users, accounts, tax_rng)
    return users, accounts


def account_source_ids(account_type: str) -> str:
    if account_type == DC:
        return (
            "KIRI_2025_20|MOEL_FSS_RETIREMENT_2025|"
            "RETIREMENT_CONTRIBUTION_2024|ASSUMPTION_V1|"
            "NTS_PENSION_TAX_2025|INCOME_TAX_DECREE_PENSION_RECEIPT|"
            "ASSUMPTION_CONTRIBUTION_V1|ASSUMPTION_TAX_SCENARIO_V1"
        )
    if account_type == IRP:
        return (
            "KOSTAT_RETIREMENT_2024|MOEL_FSS_RETIREMENT_2025|"
            "RETIREMENT_CONTRIBUTION_2024|KIRI_PENSION_CONTRIBUTION_2022|"
            "KIRI_REPLACEMENT_RATE_2023|ASSUMPTION_V1|"
            "NTS_PENSION_TAX_2025|INCOME_TAX_DECREE_PENSION_RECEIPT|"
            "ASSUMPTION_CONTRIBUTION_V1|ASSUMPTION_TAX_SCENARIO_V1"
        )
    return (
        "FSC_FSS_PSA_2025|KIRI_PENSION_CONTRIBUTION_2022|"
        "NTS_PENSION_TAX_2025|INCOME_TAX_DECREE_PENSION_RECEIPT|"
        "ASSUMPTION_V1|ASSUMPTION_CONTRIBUTION_V1|"
        "ASSUMPTION_TAX_SCENARIO_V1"
    )


def calibrate_balances(accounts: list[dict]) -> None:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for account in accounts:
        groups[(account["account_type"], account["age_group"])].append(account)

    for (account_type, age_group), group in groups.items():
        raw_mean = statistics.fmean(account["raw_balance"] for account in group)
        scale = BALANCE_MEAN_KRW[account_type][age_group] / raw_mean
        for account in group:
            account["balance_krw"] = max(
                10_000, int(round(account["raw_balance"] * scale / 10_000) * 10_000)
            )
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
            (
                "BOND",
                safe
                if account["account_type"] == PENSION_SAVINGS_FUND
                else safe * 0.30,
            ),
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
    users: list[dict],
    accounts: list[dict],
    holdings: list[dict],
    expected_users: int,
    seed: int,
) -> dict:
    errors: list[str] = []
    user_ids = {user["user_id"] for user in users}
    if len(users) != expected_users or len(user_ids) != expected_users:
        errors.append("user count or uniqueness mismatch")

    for user in users:
        expected_profile = PREFERRED_MANAGEMENT_TO_RISK_PROFILE.get(
            user["preferred_management_type"]
        )
        if user["risk_profile"] != expected_profile:
            errors.append(f"risk-profile mapping mismatch: {user['user_id']}")
            break

    account_count_by_user = Counter(account["user_id"] for account in accounts)
    missing_accounts = user_ids - set(account_count_by_user)
    if missing_accounts:
        errors.append(f"users without accounts: {len(missing_accounts)}")
    unknown_users = set(account_count_by_user) - user_ids
    if unknown_users:
        errors.append(f"accounts with unknown users: {len(unknown_users)}")

    invalid_types = sorted(
        {account["account_type"] for account in accounts} - set(ALLOWED_ACCOUNT_TYPES)
    )
    if invalid_types:
        errors.append(f"invalid account types: {invalid_types}")

    tax_income_by_user = {
        user["user_id"]: user["tax_credit_income_amount_krw"] for user in users
    }
    gross_salary_by_user = {user["user_id"]: user["gross_salary_krw"] for user in users}
    user_record_by_id = {user["user_id"]: user for user in users}
    account_rows_by_user: dict[str, list[dict]] = defaultdict(list)
    for account in accounts:
        account_rows_by_user[account["user_id"]].append(account)

    for user in users:
        user_accounts = account_rows_by_user[user["user_id"]]
        is_salaried = user["employment_type"] == SALARIED_EMPLOYEE
        if is_salaried != (user["gross_salary_krw"] is not None):
            errors.append(f"gross-salary basis mismatch: {user['user_id']}")
            break
        if is_salaried == (user["comprehensive_income_krw"] is not None):
            errors.append(f"comprehensive-income basis mismatch: {user['user_id']}")
            break
        if not is_salaried and any(
            account["account_type"] == DC for account in user_accounts
        ):
            errors.append(f"non-employee owns DC account: {user['user_id']}")
            break
        eligible_total = sum(
            account["tax_credit_eligible_contribution_krw"] for account in user_accounts
        )
        pension_savings_eligible = sum(
            account["tax_credit_eligible_contribution_krw"]
            for account in user_accounts
            if account["account_type"] == PENSION_SAVINGS_FUND
        )
        pension_savings_contribution = sum(
            account["annual_contribution_krw"]
            for account in user_accounts
            if account["account_type"] == PENSION_SAVINGS_FUND
        )
        irp_contribution = sum(
            account["annual_contribution_krw"]
            for account in user_accounts
            if account["account_type"] == IRP
        )
        if (
            pension_savings_contribution + irp_contribution
            > COMBINED_PERSONAL_PENSION_CONTRIBUTION_LIMIT_KRW
        ):
            errors.append(f"combined contribution limit exceeded: {user['user_id']}")
            break
        if user["pension_savings_contribution_krw"] != pension_savings_contribution:
            errors.append(
                f"user pension-savings contribution mismatch: {user['user_id']}"
            )
            break
        if user["irp_contribution_krw"] != irp_contribution:
            errors.append(f"user IRP contribution mismatch: {user['user_id']}")
            break
        if eligible_total > COMBINED_PENSION_TAX_CREDIT_LIMIT_KRW:
            errors.append(f"combined tax-credit limit exceeded: {user['user_id']}")
            break
        if pension_savings_eligible > PENSION_SAVINGS_TAX_CREDIT_LIMIT_KRW:
            errors.append(
                f"pension-savings tax-credit limit exceeded: {user['user_id']}"
            )
            break
        if user["total_tax_credit_eligible_contribution_krw"] != eligible_total:
            errors.append(f"user tax-credit total mismatch: {user['user_id']}")
            break
        if user["estimated_pension_tax_credit_krw"] != sum(
            account["estimated_tax_credit_krw"] for account in user_accounts
        ):
            errors.append(f"user estimated tax-credit mismatch: {user['user_id']}")
            break
        if user["planned_annual_total_pension_receipt_krw"] != sum(
            account["planned_annual_pension_receipt_krw"] for account in user_accounts
        ):
            errors.append(f"user planned receipt mismatch: {user['user_id']}")
            break

    for account in accounts:
        monthly_contribution = account["monthly_contribution_krw"]
        if account["annual_contribution_krw"] != monthly_contribution * 12:
            errors.append(
                f"annual/monthly contribution mismatch: {account['account_id']}"
            )
            break
        is_active = account["contribution_status"] == "ACTIVE"
        if is_active != (monthly_contribution > 0):
            errors.append(f"contribution status mismatch: {account['account_id']}")
            break
        if (account["contribution_frequency"] == "NONE") == is_active:
            errors.append(f"contribution frequency mismatch: {account['account_id']}")
            break
        if account["account_type"] == DC:
            expected_dc_monthly = round_to_10k(
                gross_salary_by_user[account["user_id"]] / 144
            )
            if monthly_contribution != expected_dc_monthly:
                errors.append(f"DC income formula mismatch: {account['account_id']}")
                break
            if account["tax_credit_eligible_contribution_krw"] != 0:
                errors.append(
                    "DC employer contribution received tax credit: "
                    f"{account['account_id']}"
                )
                break
        if account["account_open_year"] != TAX_YEAR - account["contribution_years"] + 1:
            errors.append(f"account tenure mismatch: {account['account_id']}")
            break
        expected_years_at_receipt = account["contribution_years"] + (
            user_record_by_id[account["user_id"]]["planned_pension_start_age"]
            - user_record_by_id[account["user_id"]]["age"]
        )
        if (
            account["planned_contribution_years_at_receipt"]
            != expected_years_at_receipt
        ):
            errors.append(f"planned receipt tenure mismatch: {account['account_id']}")
            break
        expected_credit = round(
            account["tax_credit_eligible_contribution_krw"]
            * tax_credit_rate(
                user_record_by_id[account["user_id"]]["tax_credit_income_basis"],
                tax_income_by_user[account["user_id"]],
            )
        )
        if account["estimated_tax_credit_krw"] != expected_credit:
            errors.append(
                f"account estimated tax-credit mismatch: {account['account_id']}"
            )
            break
        if (
            account["account_type"] in (DC, IRP)
            and account["risky_asset_ratio"] > 0.7000001
        ):
            errors.append(f"risk cap exceeded: {account['account_id']}")
            break
        ratio_sum = (
            account["risky_asset_ratio"]
            + account["safe_asset_ratio"]
            + account["cash_ratio"]
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
        errors.append(
            f"holdings with unknown accounts: {len(unknown_holding_accounts)}"
        )
    for account in accounts:
        rows = holdings_by_account[account["account_id"]]
        if not rows:
            errors.append(f"account without holdings: {account['account_id']}")
            break
        if account["account_type"] == PENSION_SAVINGS_FUND and any(
            row["asset_class"] == "PRINCIPAL_GUARANTEED" for row in rows
        ):
            errors.append(
                "principal-guaranteed holding in pension savings fund: "
                f"{account['account_id']}"
            )
            break
        if not math.isclose(
            sum(float(row["weight"]) for row in rows), 1.0, abs_tol=1e-6
        ):
            errors.append(f"holding weights do not sum to 1: {account['account_id']}")
            break
        if sum(row["amount_krw"] for row in rows) != account["balance_krw"]:
            errors.append(
                f"holding amounts do not match balance: {account['account_id']}"
            )
            break

    type_stats = {}
    for account_type in ALLOWED_ACCOUNT_TYPES:
        group = [
            account for account in accounts if account["account_type"] == account_type
        ]
        balances = [account["balance_krw"] for account in group]
        returns = [account["trailing_12m_return_pct"] for account in group]
        monthly_contributions = [
            account["monthly_contribution_krw"] for account in group
        ]
        active_contributions = [value for value in monthly_contributions if value > 0]
        type_stats[account_type] = {
            "accounts": len(group),
            "mean_balance_krw": round(statistics.fmean(balances)),
            "balance_population_sd_krw": round(statistics.pstdev(balances)),
            "mean_monthly_contribution_krw": round(
                statistics.fmean(monthly_contributions)
            ),
            "active_contribution_rate": round(
                len(active_contributions) / len(group), 4
            ),
            "active_mean_monthly_contribution_krw": round(
                statistics.fmean(active_contributions)
            ),
            "mean_contribution_years": round(
                statistics.fmean(account["contribution_years"] for account in group),
                1,
            ),
            "mean_planned_annual_pension_receipt_krw": round(
                statistics.fmean(
                    account["planned_annual_pension_receipt_krw"] for account in group
                )
            ),
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
                if account["account_type"] == account_type
                and account["age_group"] == age_group
            ]
            age_type_mean_balance[account_type][age_group] = round(
                statistics.fmean(account["balance_krw"] for account in group)
            )

    risk_profile_by_user = {user["user_id"]: user["risk_profile"] for user in users}
    risk_profile_mean_risky_asset_ratio = {}
    for risk_profile in sorted(set(risk_profile_by_user.values())):
        group = [
            account
            for account in accounts
            if risk_profile_by_user[account["user_id"]] == risk_profile
        ]
        risk_profile_mean_risky_asset_ratio[risk_profile] = round(
            statistics.fmean(account["risky_asset_ratio"] for account in group), 4
        )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "seed": seed,
        "users": len(users),
        "accounts": len(accounts),
        "holdings": len(holdings),
        "allowed_account_types": list(ALLOWED_ACCOUNT_TYPES),
        "scenario_counts": dict(
            sorted(Counter(user["mock_scenario"] for user in users).items())
        ),
        "age_group_counts": dict(
            sorted(Counter(user["age_group"] for user in users).items())
        ),
        "risk_profile_counts": dict(
            sorted(Counter(user["risk_profile"] for user in users).items())
        ),
        "preferred_management_type_counts": dict(
            sorted(Counter(user["preferred_management_type"] for user in users).items())
        ),
        "retirement_fund_attitude_counts": dict(
            sorted(Counter(user["retirement_fund_attitude"] for user in users).items())
        ),
        "investment_readiness_counts": dict(
            sorted(Counter(user["investment_readiness"] for user in users).items())
        ),
        "payout_preference_counts": dict(
            sorted(Counter(user["payout_preference"] for user in users).items())
        ),
        "primary_outside_asset_counts": dict(
            sorted(Counter(user["primary_outside_asset"] for user in users).items())
        ),
        "employment_type_counts": dict(
            sorted(Counter(user["employment_type"] for user in users).items())
        ),
        "income_tax_credit_band_counts": dict(
            sorted(
                Counter(
                    (
                        "GROSS_SALARY_AT_OR_BELOW_55M"
                        if user["tax_credit_income_amount_krw"]
                        <= GROSS_SALARY_TAX_CREDIT_THRESHOLD_KRW
                        else "GROSS_SALARY_ABOVE_55M"
                    )
                    if user["tax_credit_income_basis"] == "GROSS_SALARY"
                    else (
                        "COMPREHENSIVE_INCOME_AT_OR_BELOW_45M"
                        if user["tax_credit_income_amount_krw"]
                        <= COMPREHENSIVE_INCOME_TAX_CREDIT_THRESHOLD_KRW
                        else "COMPREHENSIVE_INCOME_ABOVE_45M"
                    )
                    for user in users
                ).items()
            )
        ),
        "pension_tax_credit_rate_counts": dict(
            sorted(
                Counter(
                    f"{user['pension_tax_credit_rate_pct']:.1f}%" for user in users
                ).items()
            )
        ),
        "planned_pension_start_age_counts": dict(
            sorted(Counter(user["planned_pension_start_age"] for user in users).items())
        ),
        "planned_receipt_tax_treatment_counts": dict(
            sorted(
                Counter(user["planned_receipt_tax_treatment"] for user in users).items()
            )
        ),
        "tax_credit_eligible_status_counts": dict(
            sorted(
                Counter(
                    "HAS_ELIGIBLE_CONTRIBUTION"
                    if user["total_tax_credit_eligible_contribution_krw"] > 0
                    else "NO_ELIGIBLE_CONTRIBUTION"
                    for user in users
                ).items()
            )
        ),
        "mean_gross_salary_krw": round(
            statistics.fmean(
                user["gross_salary_krw"]
                for user in users
                if user["gross_salary_krw"] is not None
            )
        ),
        "mean_comprehensive_income_krw": round(
            statistics.fmean(
                user["comprehensive_income_krw"]
                for user in users
                if user["comprehensive_income_krw"] is not None
            )
        ),
        "mean_tax_credit_income_amount_krw": round(
            statistics.fmean(user["tax_credit_income_amount_krw"] for user in users)
        ),
        "mean_tax_credit_eligible_contribution_krw": round(
            statistics.fmean(
                user["total_tax_credit_eligible_contribution_krw"] for user in users
            )
        ),
        "mean_pension_savings_contribution_krw": round(
            statistics.fmean(user["pension_savings_contribution_krw"] for user in users)
        ),
        "mean_irp_contribution_krw": round(
            statistics.fmean(user["irp_contribution_krw"] for user in users)
        ),
        "mean_estimated_pension_tax_credit_krw": round(
            statistics.fmean(user["estimated_pension_tax_credit_krw"] for user in users)
        ),
        "mean_planned_annual_total_pension_receipt_krw": round(
            statistics.fmean(
                user["planned_annual_total_pension_receipt_krw"] for user in users
            )
        ),
        "mean_planned_annual_receipt_for_pension_method_krw": round(
            statistics.fmean(
                user["planned_annual_total_pension_receipt_krw"]
                for user in users
                if user["payout_preference"] != "LUMP_SUM"
            )
        ),
        "mean_planned_lump_sum_receipt_krw": round(
            statistics.fmean(
                user["planned_annual_total_pension_receipt_krw"]
                for user in users
                if user["payout_preference"] == "LUMP_SUM"
            )
        ),
        "contribution_frequency_counts": dict(
            sorted(
                Counter(
                    account["contribution_frequency"] for account in accounts
                ).items()
            )
        ),
        "pension_receipt_eligibility_counts": dict(
            sorted(
                Counter(
                    account["pension_receipt_eligibility"] for account in accounts
                ).items()
            )
        ),
        "risk_profile_mean_risky_asset_ratio": risk_profile_mean_risky_asset_ratio,
        "account_type_stats": type_stats,
        "age_type_mean_balance_krw": age_type_mean_balance,
        "assumption_note": (
            "Employment mix, income dispersion, contribution activity/frequency/"
            "dispersion, account combinations, and detailed holdings are model "
            "assumptions. The KEF "
            "four-to-five profile mapping and cross-attribute relationships are also "
            "assumptions. Account tenure and planned receipt amounts are tax-scenario "
            "assumptions; estimated tax credits are not guaranteed refunds."
        ),
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
        raise ValueError(
            "Generated data failed validation: " + "; ".join(summary["errors"])
        )

    write_csv(
        output_dir / "users.csv",
        users,
        [
            "user_id",
            "age",
            "age_group",
            "employment_type",
            "gross_salary_krw",
            "comprehensive_income_krw",
            "tax_credit_income_basis",
            "tax_credit_income_amount_krw",
            "tax_year",
            "pension_tax_credit_rate_pct",
            "total_tax_credit_eligible_contribution_krw",
            "estimated_pension_tax_credit_krw",
            "planned_pension_start_age",
            "planned_receipt_years",
            "planned_annual_total_pension_receipt_krw",
            "planned_annual_personal_pension_receipt_krw",
            "planned_low_rate_pension_tax_pct",
            "planned_receipt_tax_treatment",
            "risk_profile",
            "preferred_management_type",
            "retirement_fund_attitude",
            "investment_readiness",
            "payout_preference",
            "primary_outside_asset",
            "mock_scenario",
            "data_kind",
            "source_ids",
            "pension_savings_contribution_krw",
            "irp_contribution_krw",
        ],
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
            "annual_contribution_krw",
            "contribution_status",
            "contribution_frequency",
            "account_open_year",
            "contribution_years",
            "planned_contribution_years_at_receipt",
            "pension_receipt_eligibility",
            "tax_credit_eligible_contribution_krw",
            "estimated_tax_credit_krw",
            "planned_annual_pension_receipt_krw",
            "planned_receipt_tax_treatment",
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
        [
            "account_id",
            "asset_class",
            "weight",
            "amount_krw",
            "data_kind",
            "source_ids",
        ],
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
