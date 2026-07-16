import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from backend.app.engine.pension_eligibility import (
    KIS_RETIREMENT_NOTICE_URL,
    KIS_RETIREMENT_RESTRICTION_URL,
    PENSION_SAVINGS_RULE_URL,
    classify_pension_account_eligibility,
)
from backend.app.ingestion.kis_pension_eligibility import (
    load_kis_retirement_etfs,
)

DEFAULT_CLASSIFICATION_ROOT = Path("data/cache/classification")
DEFAULT_KIS_RETIREMENT_ROOT = Path("data/raw/kis")
DEFAULT_LAW_RULES_ROOT = Path("data/cache/law_open")
DEFAULT_OUTPUT_ROOT = Path("data/cache/classification")
ACCOUNT_TYPES = ("dc", "irp", "pension_savings")


def _latest(root: Path, pattern: str) -> Path:
    candidates = sorted(root.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"no files matching {pattern} under {root}")
    return candidates[-1]


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _latest_optional(root: Path, pattern: str) -> Path | None:
    candidates = sorted(root.glob(pattern))
    return candidates[-1] if candidates else None


def _regulatory_summary(master: dict[str, Any] | None) -> dict[str, Any] | None:
    if master is None:
        return None
    if master.get("report_type") != "pension_account_regulatory_rules":
        raise ValueError("law rule master has an invalid report type")
    rules = master.get("rules")
    if not isinstance(rules, list):
        raise ValueError("law rule master must contain rules")
    rule_ids = {
        rule.get("rule_id")
        for rule in rules
        if isinstance(rule, dict) and isinstance(rule.get("rule_id"), str)
    }
    required = {
        "DC_IRP_GENERAL_RISK_ASSET_CAP",
        "DC_IRP_LOWER_RISK_METHOD_CAP_EXCLUSION",
        "DC_IRP_QUALIFIED_TDF_CRITERIA",
        "DC_IRP_DEFAULT_OPTION_APPROVAL",
    }
    if not required.issubset(rule_ids):
        raise ValueError("law rule master is missing required pension rules")
    return {
        "snapshot_date": master.get("snapshot_date"),
        "source": master.get("source"),
        "rule_ids": sorted(rule_ids),
        "product_level_tdf_verification_required": True,
    }


def build_pension_eligibility_report(
    *,
    classification_report: dict[str, Any],
    kis_retirement_products: list[dict[str, object]],
    classification_path: Path,
    kis_retirement_path: Path,
    as_of: date,
    eligibility_as_of: date,
    regulatory_master: dict[str, Any] | None = None,
    regulatory_master_path: Path | None = None,
) -> dict[str, Any]:
    products = classification_report.get("products")
    if not isinstance(products, list):
        raise ValueError("classification report must contain products")
    kis_by_code = {
        str(product["isu_code"]): product for product in kis_retirement_products
    }

    eligible_products = []
    account_counts = Counter()
    asset_class_counts: dict[str, Counter[str]] = {
        account: Counter() for account in ACCOUNT_TYPES
    }
    allocation_counts: dict[str, Counter[str]] = {
        account: Counter() for account in ACCOUNT_TYPES
    }
    excluded_counts = Counter()
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("classification product must be an object")
        code = product.get("isu_code")
        classification = product.get("classification")
        if not isinstance(code, str) or not isinstance(classification, dict):
            raise ValueError("classification product has invalid fields")
        evaluations = classify_pension_account_eligibility(
            classification,
            kis_by_code.get(code),
        )
        eligible_accounts = {
            account: result
            for account, result in evaluations.items()
            if result["eligible"]
        }
        for account, result in evaluations.items():
            if result["eligible"]:
                account_counts[account] += 1
                asset_class_counts[account][
                    str(classification["asset_class"])
                ] += 1
                allocation_counts[account][result["allocation_bucket"]] += 1
            else:
                excluded_counts[f"{account}:{result['reason_code']}"] += 1
        if not eligible_accounts:
            continue
        eligible_products.append(
            {
                "isu_code": code,
                "isu_name": product["isu_name"],
                "classification": classification,
                "account_eligibility": eligible_accounts,
                "fsc_join_status": product.get("fsc_join_status"),
                "fsc_support": product.get("fsc_support"),
                "evidence": product.get("evidence", []),
            }
        )

    source_files = {
        "classification": classification_path.as_posix(),
        "kis_retirement_etf_list": kis_retirement_path.as_posix(),
    }
    if regulatory_master_path is not None:
        source_files["law_open_regulatory_rules"] = (
            regulatory_master_path.as_posix()
        )
    return {
        "report_type": "pension_account_eligible_etfs",
        "algorithm_input": False,
        "product_scope": "eligible_in_at_least_one_pension_account",
        "intended_use": "cross_account_audit_and_account_export_source",
        "as_of": as_of.isoformat(),
        "eligibility_as_of": eligibility_as_of.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_name": "pension_etf_account_eligibility",
        "engine_version": "2026-07-16.1",
        "source_files": source_files,
        "source_urls": {
            "kis_dc_irp_official_list": KIS_RETIREMENT_NOTICE_URL,
            "dc_irp_leverage_inverse_restriction": (
                KIS_RETIREMENT_RESTRICTION_URL
            ),
            "pension_savings_account_rule": PENSION_SAVINGS_RULE_URL,
            "law_open_api_guide": (
                "https://open.law.go.kr/LSO/openApi/guideResult.do"
                "?htmlName=admrulInfoGuide"
            ),
        },
        "regulatory_rules": _regulatory_summary(regulatory_master),
        "universe_product_count": len(products),
        "kis_retirement_source_product_count": len(kis_retirement_products),
        "eligible_union_product_count": len(eligible_products),
        "eligible_product_counts": {
            account: account_counts[account] for account in ACCOUNT_TYPES
        },
        "eligible_asset_class_counts": {
            account: dict(sorted(asset_class_counts[account].items()))
            for account in ACCOUNT_TYPES
        },
        "allocation_bucket_counts": {
            account: dict(sorted(allocation_counts[account].items()))
            for account in ACCOUNT_TYPES
        },
        "excluded_reason_counts": dict(sorted(excluded_counts.items())),
        "limitations": [
            "portfolio engines must load an account-specific eligible export, "
            "not this cross-account union or the 945-product source universe",
            "DC and IRP eligibility is KIS-specific and may differ by provider",
            "pension-savings eligibility is an account-rule classification, not a "
            "KIS order-system inventory confirmation",
            "a 100 percent retirement allocation limit does not mean principal "
            "protection",
            "a provider-confirmed 100 percent limit does not by itself prove that "
            "the product is a qualified TDF; product-level prospectus or provider "
            "classification is still required",
            "only the current KRX listed and sufficiently observed ETF universe is "
            "included",
        ],
        "products": eligible_products,
    }


def _account_report(report: dict[str, Any], account: str) -> dict[str, Any]:
    products = []
    for product in report["products"]:
        eligibility = product["account_eligibility"].get(account)
        if eligibility is None:
            continue
        products.append(
            {
                **{
                    key: value
                    for key, value in product.items()
                    if key != "account_eligibility"
                },
                "account_eligibility": eligibility,
            }
        )
    account_report = {
        **{key: value for key, value in report.items() if key != "products"},
        "report_type": "pension_account_eligible_etfs_by_account",
        "algorithm_input": True,
        "product_scope": "account_eligible_only",
        "intended_use": "pension_portfolio_engine_input",
        "account_type": account,
        "product_count": len(products),
        "source_universe_product_count": report["universe_product_count"],
        "excluded_product_count": report["universe_product_count"]
        - len(products),
        "products": products,
    }
    return account_report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Save only ETFs eligible for DC, IRP, or pension savings."
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--eligibility-as-of",
        type=date.fromisoformat,
        default=date(2026, 6, 30),
    )
    parser.add_argument("--classification", type=Path)
    parser.add_argument("--kis-retirement-list", type=Path)
    parser.add_argument("--law-rules", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    classification_path = args.classification or _latest(
        DEFAULT_CLASSIFICATION_ROOT,
        "etf_asset_classification_*.json",
    )
    kis_retirement_path = args.kis_retirement_list or _latest(
        DEFAULT_KIS_RETIREMENT_ROOT,
        "retirement_etf_list_*.xlsx",
    )
    law_rules_path = args.law_rules or _latest_optional(
        DEFAULT_LAW_RULES_ROOT,
        "pension_regulatory_rules_*.json",
    )
    report = build_pension_eligibility_report(
        classification_report=_load(classification_path),
        kis_retirement_products=load_kis_retirement_etfs(kis_retirement_path),
        classification_path=classification_path,
        kis_retirement_path=kis_retirement_path,
        as_of=args.as_of,
        eligibility_as_of=args.eligibility_as_of,
        regulatory_master=_load(law_rules_path) if law_rules_path else None,
        regulatory_master_path=law_rules_path,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    union_path = args.output / f"pension_account_eligible_etfs_{args.as_of}.json"
    _write_json(union_path, report)
    account_paths = {}
    for account in ACCOUNT_TYPES:
        path = args.output / f"{account}_eligible_etfs_{args.as_of}.json"
        _write_json(path, _account_report(report, account))
        account_paths[account] = path.as_posix()

    public = {key: value for key, value in report.items() if key != "products"}
    public["output_path"] = union_path.as_posix()
    public["account_output_paths"] = account_paths
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
