"""Build the six detailed demo portfolios from their 10k benchmark records."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"

ACCOUNT_TYPE_MAP = {
    "DC": "dc",
    "IRP": "irp",
    "PENSION_SAVINGS_FUND": "pension_savings",
}
ASSET_CLASS_ORDER = (
    "domestic_equity",
    "global_equity",
    "bond",
    "deposit",
    "cash",
)
LEGACY_RISK_PROFILE_MAP = {
    "stable": "conservative",
    "stable_seeking": "conservative",
    "risk_neutral": "balanced",
    "active": "growth",
    "aggressive": "growth",
}
LEGACY_SCENARIO_METADATA = {
    "dc_dormant": {
        "name": "DC형 방치",
        "description": (
            "회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객\n"
            "비고: 납입액에 대한 세액공제혜택 대상인 연금저축펀드와 개인 IRP계좌가 없음"
        ),
    },
    "tax_contribution_uninvested": {
        "name": "세액공제 후 미운용",
        "description": (
            "세액공제를 위해 납입했지만 IRP·연금저축을 실제 운용하지 않은 고객\n"
            "비고: 각 계좌별 납입액 세액공제한도를 고려하지 않고 납입했음"
        ),
    },
    "overlap_risk_concentration": {
        "name": "계좌별 중복·위험 편중",
        "description": (
            "DC·IRP·연금저축에 글로벌주식형 자산이 중복되어 위험자산 편중이 있는 고객"
        ),
    },
    "young_retirement_distance": {
        "name": "연금이 멀게 느껴지는 청년층",
        "description": (
            "노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 청년층 고객"
        ),
    },
    "family_budget_pressure": {
        "name": "가계지출로 납입이 빠듯한 중년층",
        "description": (
            "자녀·주거비로 추가 납입은 빠듯하지만 "
            "노후 준비를 걱정하기 시작한 중년층 고객"
        ),
    },
    "pension_payout_transition": {
        "name": "연금 수령을 시작하는 55세 이상",
        "description": (
            "55세 이상으로 연금 수령을 시작했거나 수령 직전이라 "
            "수령 기간·세금·자산 안정성을 실제로 검토하는 설명용 시나리오"
        ),
    },
}

# Every code below was checked against the latest ready ETF universe: eligible
# for all three pension account types and backed by 253 return observations.
BOND_ETFS = (
    ("436140", "SOL 종합채권(AA-이상)액티브"),
    ("385540", "RISE 종합채권(A-이상)액티브"),
    ("356540", "ACE 종합채권(AA-이상)액티브"),
    ("461500", "HANARO 종합채권(AA-이상)액티브"),
)
GLOBAL_EQUITY_PAIRS = (
    (("360200", "ACE 미국S&P500"), ("379800", "KODEX 미국S&P500")),
    (("453330", "RISE 미국S&P500(H)"), ("423170", "SOL 글로벌AI반도체탑픽액티브")),
    (("432840", "HANARO 미국S&P500"), ("248270", "TIGER S&P글로벌헬스케어(합성)")),
    (("360200", "ACE 미국S&P500"), ("469060", "RISE 미국반도체NYSE")),
    (("458730", "TIGER 미국배당다우존스"), ("446770", "ACE 글로벌반도체TOP4 Plus")),
    (("432840", "HANARO 미국S&P500"), ("479620", "SOL 미국AI반도체칩메이커")),
)
DOMESTIC_EQUITY_PAIRS = (
    (("332930", "HANARO 200TR"), ("455850", "SOL AI반도체소부장")),
    (("411540", "SOL 200 Top10"), ("465330", "RISE 2차전지TOP10")),
    (("322410", "HANARO K고배당"), ("143860", "TIGER 헬스케어")),
    (("469150", "ACE AI반도체TOP3+"), ("314700", "HANARO 농업융복합산업")),
    (("332930", "HANARO 200TR"), ("484880", "SOL 금융지주플러스고배당")),
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _split_amount(
    amount: int, products: tuple[tuple[str | None, str], ...]
) -> list[int]:
    if len(products) == 1:
        return [amount]
    first = round(amount * 0.7)
    return [first, amount - first]


def _allocate_by_percent(total: int, allocations: dict[str, int]) -> dict[str, int]:
    if set(allocations) - set(ASSET_CLASS_ORDER):
        raise ValueError("unsupported target asset class")
    if sum(allocations.values()) != 100:
        raise ValueError("target allocation must sum to 100")
    ordered = [asset for asset in ASSET_CLASS_ORDER if asset in allocations]
    result: dict[str, int] = {}
    assigned = 0
    for asset_class in ordered[:-1]:
        amount = total * allocations[asset_class] // 100
        result[asset_class] = amount
        assigned += amount
    result[ordered[-1]] = total - assigned
    return result


def _products_for_asset(
    asset_class: str,
    *,
    scenario_code: str,
    scenario_index: int,
    account_index: int,
) -> tuple[tuple[str | None, str], ...]:
    selection_index = (
        scenario_index
        if scenario_code == "overlap_risk_concentration"
        else scenario_index + account_index
    )
    if asset_class == "domestic_equity":
        return DOMESTIC_EQUITY_PAIRS[
            selection_index % len(DOMESTIC_EQUITY_PAIRS)
        ]
    if asset_class == "global_equity":
        return GLOBAL_EQUITY_PAIRS[selection_index % len(GLOBAL_EQUITY_PAIRS)]
    if asset_class == "bond":
        return (BOND_ETFS[selection_index % len(BOND_ETFS)],)
    if asset_class == "deposit":
        return ((None, "원리금보장 상품"),)
    if asset_class == "cash":
        return ((None, "현금성 자산"),)
    raise ValueError(f"unsupported asset class: {asset_class}")


def build() -> list[dict]:
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    existing = json.loads(
        (MOCK_DIR / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )
    existing_by_code = {item["scenario_code"]: item for item in existing}
    profile_payload = json.loads(
        (MOCK_DIR / "demo_investor_profiles.json").read_text(encoding="utf-8")
    )
    profiles_by_code = {
        item["scenario_code"]: item for item in profile_payload["profiles"]
    }
    users = {row["user_id"]: row for row in _read_csv(MOCK_DIR / "users.csv")}

    accounts_by_user: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(MOCK_DIR / "accounts.csv"):
        accounts_by_user[row["user_id"]].append(row)

    scenario_codes = {item["scenario_code"] for item in manifest}
    if set(profiles_by_code) != scenario_codes:
        raise ValueError("demo profile scenarios must match the hero manifest")

    output: list[dict] = []
    issuer_names: set[str] = set()
    for scenario_index, manifest_user in enumerate(manifest):
        scenario_code = manifest_user["scenario_code"]
        source_user = users[manifest_user["benchmark_user_id"]]
        metadata = LEGACY_SCENARIO_METADATA[scenario_code]
        profile = profiles_by_code[scenario_code]
        source_accounts = sorted(
            accounts_by_user[source_user["user_id"]],
            key=lambda row: tuple(ACCOUNT_TYPE_MAP).index(row["account_type"]),
        )
        existing_labels = {
            account["account_type"]: account["label"]
            for account in existing_by_code[scenario_code]["accounts"]
        }
        scenario_accounts: list[dict] = []
        for account_index, source_account in enumerate(source_accounts):
            account_type = ACCOUNT_TYPE_MAP[source_account["account_type"]]
            target_allocations = profile["portfolio_allocations"].get(account_type)
            if target_allocations is None:
                raise ValueError(
                    f"missing target allocation: {scenario_code}/{account_type}"
                )
            allocated_amounts = _allocate_by_percent(
                int(source_account["balance_krw"]), target_allocations
            )
            detailed_holdings: list[dict] = []
            for asset_class, amount in allocated_amounts.items():
                if amount == 0:
                    continue
                products = _products_for_asset(
                    asset_class,
                    scenario_code=scenario_code,
                    scenario_index=scenario_index,
                    account_index=account_index,
                )
                risk_treatment = (
                    "general_risky"
                    if asset_class in {"domestic_equity", "global_equity"}
                    else "capital_preservation"
                )
                amounts = _split_amount(amount, products)
                for product_index, ((isu_code, name), product_amount) in enumerate(
                    zip(products, amounts, strict=True), start=1
                ):
                    item = {
                        "holding_id": (
                            f"{scenario_code}_{account_type}_{asset_class}_{product_index}"
                        ),
                        "instrument_name": name,
                        "asset_class_code": asset_class,
                        "amount_krw": str(product_amount),
                        "risk_treatment": risk_treatment,
                    }
                    if isu_code is not None:
                        item["etf_isu_code"] = isu_code
                        issuer_names.add(name.split()[0])
                    detailed_holdings.append(item)

            if sum(int(item["amount_krw"]) for item in detailed_holdings) != int(
                source_account["balance_krw"]
            ):
                raise ValueError(f"balance mismatch: {source_account['account_id']}")
            scenario_accounts.append(
                {
                    "account_id": f"{scenario_code}_{account_type}",
                    "account_type": account_type,
                    "label": existing_labels[account_type],
                    "holdings": detailed_holdings,
                }
            )

        output.append(
            {
                "scenario_code": scenario_code,
                "name": metadata["name"],
                "description": metadata["description"],
                "age_band": manifest_user["age_band"],
                "risk_profile": LEGACY_RISK_PROFILE_MAP[
                    profile["investor_profile"]
                ],
                "investment_horizon_years": max(
                    1,
                    int(source_user["planned_pension_start_age"])
                    - int(source_user["age"]),
                ),
                "accounts": scenario_accounts,
            }
        )

    required_issuers = {"KODEX", "TIGER", "ACE", "RISE", "SOL", "HANARO"}
    if not required_issuers.issubset(issuer_names):
        raise ValueError(f"missing ETF issuers: {required_issuers - issuer_names}")
    return output


def _complete_customer(user_id: str) -> dict:
    users = {row["user_id"]: row for row in _read_csv(MOCK_DIR / "users.csv")}
    accounts = [
        row for row in _read_csv(MOCK_DIR / "accounts.csv") if row["user_id"] == user_id
    ]
    account_ids = {row["account_id"] for row in accounts}
    holdings_by_account: dict[str, list[dict]] = defaultdict(list)
    for row in _read_csv(MOCK_DIR / "holdings.csv"):
        if row["account_id"] in account_ids:
            holdings_by_account[row["account_id"]].append(row)
    return {
        "customer": users[user_id],
        "accounts": [
            {**account, "holdings": holdings_by_account[account["account_id"]]}
            for account in accounts
        ],
    }


def main() -> None:
    output = build()
    (MOCK_DIR / "chatbot_scenarios.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    representative = next(
        item
        for item in manifest
        if item["scenario_code"] == "overlap_risk_concentration"
    )
    representative_scenario = next(
        item
        for item in output
        if item["scenario_code"] == representative["scenario_code"]
    )
    profile_payload = json.loads(
        (MOCK_DIR / "demo_investor_profiles.json").read_text(encoding="utf-8")
    )
    representative_profile = next(
        item
        for item in profile_payload["profiles"]
        if item["scenario_code"] == representative["scenario_code"]
    )
    public_metric_payload = json.loads(
        (MOCK_DIR / "demo_public_portfolio_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    representative_public_metric = next(
        item
        for item in public_metric_payload["profiles"]
        if item["scenario_code"] == representative["scenario_code"]
    )
    examples = {
        "schema_version": 1,
        "contract_counts": {
            "customer_columns": 29,
            "account_columns_excluding_nested_holdings": 23,
            "benchmark_holding_columns": 6,
            "detailed_etf_holding_columns": 7,
        },
        "benchmark_customer_example": _complete_customer("USR00001"),
        "representative_customer_example": {
            "demo_identity": representative,
            "investor_profile_assessment": {
                "rule_version": profile_payload["rule_version"],
                "source_documents": profile_payload["source_documents"],
                "data_boundary": profile_payload["data_boundary"],
                "notice": profile_payload["notice"],
                **representative_profile,
            },
            "public_portfolio_metrics": {
                "notice": public_metric_payload["notice"],
                "return_metric": public_metric_payload["return_metric"],
                "like_metric": public_metric_payload["like_metric"],
                **representative_public_metric,
            },
            "benchmark_contract": _complete_customer(
                representative["benchmark_user_id"]
            ),
            "detailed_etf_portfolio": representative_scenario,
        },
    }
    (MOCK_DIR / "customer_data_examples.json").write_text(
        json.dumps(examples, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(output)} detailed demo customer portfolios")


if __name__ == "__main__":
    main()
