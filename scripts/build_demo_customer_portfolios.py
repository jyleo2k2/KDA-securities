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
ASSET_CLASS_MAP = {
    "CASH": ("cash", "현금성 자산", "capital_preservation"),
    "PRINCIPAL_GUARANTEED": (
        "deposit",
        "원리금보장 상품",
        "capital_preservation",
    ),
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


def _split_amount(amount: int, products: tuple[tuple[str, str], ...]) -> list[int]:
    if len(products) == 1:
        return [amount]
    first = round(amount * 0.7)
    return [first, amount - first]


def build() -> list[dict]:
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    existing = json.loads(
        (MOCK_DIR / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )
    metadata_by_code = {item["scenario_code"]: item for item in existing}
    users = {row["user_id"]: row for row in _read_csv(MOCK_DIR / "users.csv")}

    accounts_by_user: dict[str, list[dict[str, str]]] = defaultdict(list)
    accounts_by_id: dict[str, dict[str, str]] = {}
    for row in _read_csv(MOCK_DIR / "accounts.csv"):
        accounts_by_user[row["user_id"]].append(row)
        accounts_by_id[row["account_id"]] = row

    holdings_by_account: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(MOCK_DIR / "holdings.csv"):
        holdings_by_account[row["account_id"]].append(row)

    output: list[dict] = []
    issuer_names: set[str] = set()
    for scenario_index, manifest_user in enumerate(manifest):
        scenario_code = manifest_user["scenario_code"]
        source_user = users[manifest_user["benchmark_user_id"]]
        metadata = metadata_by_code[scenario_code]
        source_accounts = sorted(
            accounts_by_user[source_user["user_id"]],
            key=lambda row: tuple(ACCOUNT_TYPE_MAP).index(row["account_type"]),
        )
        existing_labels = {
            account["account_type"]: account["label"]
            for account in metadata["accounts"]
        }
        scenario_accounts: list[dict] = []
        for account_index, source_account in enumerate(source_accounts):
            account_type = ACCOUNT_TYPE_MAP[source_account["account_type"]]
            detailed_holdings: list[dict] = []
            for holding_index, source_holding in enumerate(
                holdings_by_account[source_account["account_id"]]
            ):
                asset_class = source_holding["asset_class"]
                amount = int(source_holding["amount_krw"])
                if asset_class in ASSET_CLASS_MAP:
                    engine_class, name, risk_treatment = ASSET_CLASS_MAP[asset_class]
                    products: tuple[tuple[str, str] | tuple[None, str], ...] = (
                        (None, name),
                    )
                elif asset_class == "BOND":
                    engine_class = "bond"
                    risk_treatment = "capital_preservation"
                    products = (
                        BOND_ETFS[(scenario_index + account_index) % len(BOND_ETFS)],
                    )
                elif asset_class == "EQUITY_GLOBAL":
                    engine_class = "global_equity"
                    risk_treatment = "general_risky"
                    products = GLOBAL_EQUITY_PAIRS[
                        (scenario_index + account_index) % len(GLOBAL_EQUITY_PAIRS)
                    ]
                elif asset_class == "EQUITY_KR":
                    engine_class = "domestic_equity"
                    risk_treatment = "general_risky"
                    products = DOMESTIC_EQUITY_PAIRS[
                        (scenario_index + account_index) % len(DOMESTIC_EQUITY_PAIRS)
                    ]
                else:
                    raise ValueError(f"unsupported asset class: {asset_class}")

                amounts = _split_amount(amount, products)
                for product_index, ((isu_code, name), product_amount) in enumerate(
                    zip(products, amounts, strict=True), start=1
                ):
                    item = {
                        "holding_id": (
                            f"{scenario_code}_{account_type}_{engine_class}_{holding_index}_{product_index}"
                        ),
                        "instrument_name": name,
                        "asset_class_code": engine_class,
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

        profile_map = {
            "STABLE": "conservative",
            "STABLE_SEEKING": "balanced",
            "RISK_NEUTRAL": "balanced",
            "ACTIVE": "growth",
        }
        output.append(
            {
                "scenario_code": scenario_code,
                "name": metadata["name"],
                "description": metadata["description"],
                "age_band": manifest_user["age_band"],
                "risk_profile": profile_map[source_user["risk_profile"]],
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
