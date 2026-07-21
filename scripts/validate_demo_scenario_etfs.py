"""Validate the six demo portfolios against account-specific ETF evidence."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXPECTED_ISSUERS = {"ACE", "HANARO", "KODEX", "RISE", "SOL", "TIGER"}


def _latest(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no files match {directory / pattern}")
    return matches[-1]


def validate() -> dict[str, object]:
    scenarios = json.loads(
        (DATA / "mock" / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )
    classification_dir = DATA / "cache" / "classification"
    eligible_by_account: dict[str, set[str]] = {}
    classification_files: dict[str, str] = {}
    for account_type in ("dc", "irp", "pension_savings"):
        path = _latest(classification_dir, f"{account_type}_eligible_etfs_*.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        eligible_by_account[account_type] = {
            product["isu_code"]
            for product in payload["products"]
            if product["account_eligibility"]["eligible"]
        }
        classification_files[account_type] = path.name

    market_path = _latest(DATA / "cache" / "krx", "etf_market_evidence_*.json")
    market_payload = json.loads(market_path.read_text(encoding="utf-8"))
    market_ready = {
        product["isu_code"]
        for product in market_payload["products"]
        if product["active_on_report_date"]
        and product["usable_on_report_date"]
        and not product["blocked_name_pattern"]
        and product["historical_metrics"]["observation_count"] >= 253
    }

    account_count = 0
    holding_count = 0
    etf_holding_count = 0
    unique_etfs: set[str] = set()
    issuers: set[str] = set()
    errors: list[str] = []
    for scenario in scenarios:
        for account in scenario["accounts"]:
            account_count += 1
            account_type = account["account_type"]
            holdings = account["holdings"]
            holding_count += len(holdings)
            total = sum(Decimal(item["amount_krw"]) for item in holdings)
            risky = sum(
                Decimal(item["amount_krw"])
                for item in holdings
                if item["risk_treatment"] == "general_risky"
            )
            if account_type in {"dc", "irp"} and risky > total * Decimal("0.70"):
                errors.append(f"{account['account_id']}: risk cap exceeded")

            for holding in holdings:
                isu_code = holding.get("etf_isu_code")
                if not isu_code:
                    continue
                etf_holding_count += 1
                unique_etfs.add(isu_code)
                issuer = holding["instrument_name"].split()[0]
                if issuer in EXPECTED_ISSUERS:
                    issuers.add(issuer)
                if isu_code not in eligible_by_account[account_type]:
                    errors.append(
                        f"{account['account_id']}/{isu_code}: "
                        f"not eligible for {account_type}"
                    )
                if isu_code not in market_ready:
                    errors.append(
                        f"{account['account_id']}/{isu_code}: market evidence not ready"
                    )

    missing_issuers = sorted(EXPECTED_ISSUERS - issuers)
    if missing_issuers:
        errors.append(f"missing issuers: {', '.join(missing_issuers)}")
    if len(scenarios) != 6:
        errors.append(f"expected 6 scenarios, found {len(scenarios)}")

    result: dict[str, object] = {
        "scenario_count": len(scenarios),
        "account_count": account_count,
        "holding_count": holding_count,
        "etf_holding_count": etf_holding_count,
        "unique_etf_count": len(unique_etfs),
        "issuer_count": len(issuers),
        "issuers": sorted(issuers),
        "classification_files": classification_files,
        "market_evidence_file": market_path.name,
        "risk_cap_violation_count": sum(
            1 for error in errors if "risk cap exceeded" in error
        ),
        "validation_error_count": len(errors),
        "errors": errors,
    }
    return result


def main() -> None:
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["validation_error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
