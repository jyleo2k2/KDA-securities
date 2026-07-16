import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from backend.app.engine.asset_classification import (
    EtfClassificationInput,
    classify_etf,
)
from backend.app.engine.etf_disclosure_overrides import (
    ETF_DISCLOSURE_OVERRIDES,
)

DEFAULT_KRX_ROOT = Path("data/cache/krx")
DEFAULT_KIS_ROOT = Path("data/cache/kis")
DEFAULT_FSC_ROOT = Path("data/cache/fsc")
DEFAULT_OUTPUT_ROOT = Path("data/cache/classification")


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


def _fsc_suggestion(
    match_key: str,
    funds: list[dict[str, Any]],
) -> dict[str, Any] | None:
    scored = sorted(
        (
            (
                SequenceMatcher(None, match_key, fund["match_key"]).ratio(),
                fund,
            )
            for fund in funds
            if fund.get("match_key")
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored:
        return None
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second_score
    if best_score >= 0.92 and margin >= 0.03:
        status = "probable_name_candidate"
    elif best_score >= 0.84:
        status = "possible_name_candidate"
    else:
        return None
    return {
        "status": status,
        "similarity": round(best_score, 4),
        "runner_up_margin": round(margin, 4),
        "fund_standard_code": best["fund_standard_code"],
        "fund_name": best["fund_name"],
        "fund_type": best["fund_type"],
        "coarse_asset_class": best["coarse_asset_class"],
        "product_classification_code": best["product_classification_code"],
    }


def _compatible(asset_class: str, fsc_class: str) -> bool:
    compatible = {
        "equity": {"equity"},
        "fixed_income": {"fixed_income"},
        "multi_asset": {"mixed_asset", "fund_of_funds"},
        "real_estate": {"real_estate"},
        "commodity": {"real_asset"},
        "cash_equivalent": {"cash_equivalent", "fixed_income"},
    }
    return fsc_class in compatible.get(asset_class, set())


def _component_holdings(
    rows: object,
) -> tuple[tuple[str, str, float], ...]:
    if not isinstance(rows, list):
        return ()
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("stck_shrn_iscd") or "").strip()
        name = str(row.get("hts_kor_isnm") or "").strip()
        try:
            weight = float(row.get("etf_cnfg_issu_rlim") or 0)
        except (TypeError, ValueError):
            weight = 0.0
        if name and weight > 0:
            normalized.append((code, name, weight))
    return tuple(normalized)


def build_classification_report(
    *,
    krx_path: Path,
    kis_path: Path,
    fsc_fund_path: Path,
    fsc_join_path: Path,
    as_of: date,
) -> dict[str, Any]:
    krx = _load(krx_path)
    kis = _load(kis_path)
    fsc_funds = _load(fsc_fund_path)
    fsc_join = _load(fsc_join_path)
    krx_products = krx.get("products")
    kis_products = kis.get("products")
    fund_rows = fsc_funds.get("funds")
    join_rows = fsc_join.get("products")
    source_rows = (krx_products, kis_products, fund_rows, join_rows)
    if not all(isinstance(rows, list) for rows in source_rows):
        raise ValueError("classification inputs must contain product arrays")

    kis_by_code = {row["isu_code"]: row for row in kis_products}
    join_by_code = {row["isu_code"]: row for row in join_rows}
    products = []
    for krx_product in krx_products:
        code = krx_product["isu_code"]
        kis_product = kis_by_code.get(code)
        join_product = join_by_code.get(code)
        if kis_product is None or join_product is None:
            raise ValueError(f"classification source is missing ETF {code}")
        price = kis_product.get("price")
        if not isinstance(price, dict):
            raise ValueError(f"KIS price must be an object for ETF {code}")

        exact_fund = join_product.get("fund")
        if exact_fund is not None and not isinstance(exact_fund, dict):
            raise ValueError(f"FSC fund must be an object for ETF {code}")
        disclosure = ETF_DISCLOSURE_OVERRIDES.get(code)
        holdings = _component_holdings(kis_product.get("components"))
        source = EtfClassificationInput(
            isu_code=code,
            isu_name=krx_product["isu_name"],
            benchmark_name=krx_product.get("benchmark_name") or "",
            kis_index_name=price.get("etf_rprs_bstp_kor_isnm") or "",
            kis_industry_name=price.get("bstp_kor_isnm") or "",
            fsc_fund_type=exact_fund.get("fund_type") if exact_fund else None,
            fsc_coarse_asset_class=(
                exact_fund.get("coarse_asset_class") if exact_fund else None
            ),
            kis_currency_code=price.get("crcd") or "",
            component_holdings=holdings,
            disclosure_currency_hedge=(
                disclosure.get("currency_hedge") if disclosure else None
            ),
            disclosure_confidence=(
                disclosure.get("confidence") if disclosure else None
            ),
        )
        classification = classify_etf(source)
        suggestion = None
        if join_product["match_status"] != "matched_exact_normalized_name":
            suggestion = _fsc_suggestion(join_product["match_key"], fund_rows)

        fsc_support = "exact" if exact_fund else "none"
        if suggestion and suggestion["status"] == "probable_name_candidate":
            if _compatible(
                str(classification["asset_class"]),
                suggestion["coarse_asset_class"],
            ):
                fsc_support = "probable_compatible_name_candidate"
            else:
                fsc_support = "candidate_conflicts_with_market_classification"

        warnings = []
        if classification["currency_hedge_confidence"] in {"medium", "low"}:
            warnings.append("currency_hedge_is_inferred")
        if classification["replication_confidence"] == "medium":
            warnings.append("replication_method_is_inferred")
        if "domestic_by_absence_of_foreign_marker" in classification["reason_codes"]:
            warnings.append("domestic_region_is_inferred")
        if fsc_support.startswith("candidate_conflicts"):
            warnings.append("fsc_name_candidate_not_used_due_to_conflict")
        component_profile = classification["component_profile"]
        if component_profile["status"] == "not_available":
            warnings.append("kis_components_not_available")
        if component_profile["asset_class_signal"] == "conflicts":
            warnings.append("kis_components_conflict_with_primary_asset_class")
        if component_profile["region_signal"] == "conflicts":
            warnings.append("kis_components_conflict_with_primary_region")
        if (
            classification["source_agreement"]["fsc_exact_type_asset_class"]
            == "conflicts"
        ):
            warnings.append("fsc_exact_type_conflicts_with_market_classification")

        evidence = [
            {
                "source": "KRX",
                "field": "isu_name",
                "value": source.isu_name,
            },
            {
                "source": "KRX",
                "field": "benchmark_name",
                "value": source.benchmark_name,
            },
            {
                "source": "KIS",
                "field": "etf_rprs_bstp_kor_isnm",
                "value": source.kis_index_name,
            },
            {
                "source": "KIS",
                "field": "bstp_kor_isnm",
                "value": source.kis_industry_name,
            },
            {
                "source": "KIS",
                "field": "crcd",
                "value": source.kis_currency_code,
                "note": "listing settlement currency; not underlying FX exposure",
            },
            {
                "source": "KIS",
                "field": "components",
                "value": [
                    {"code": item[0], "name": item[1], "weight_percent": item[2]}
                    for item in holdings[:10]
                ],
                "component_count": len(holdings),
                "note": "top 10 stored here; component profile uses all returned rows",
            },
        ]
        if exact_fund:
            evidence.append(
                {
                    "source": "FSC",
                    "field": "fund_standard_code_and_type",
                    "value": {
                        "fund_standard_code": exact_fund.get("fund_standard_code"),
                        "fund_type": exact_fund.get("fund_type"),
                        "coarse_asset_class": exact_fund.get(
                            "coarse_asset_class"
                        ),
                    },
                }
            )
        if disclosure:
            evidence.append(
                {
                    "source": "ISSUER_DISCLOSURE",
                    "field": "currency_hedge",
                    "value": disclosure["currency_hedge"],
                    "confidence": disclosure["confidence"],
                    "verified_as_of": disclosure["verified_as_of"],
                    "source_type": disclosure["source_type"],
                    "title": disclosure["source_title"],
                    "reference": disclosure["source_url"],
                    "basis": disclosure["basis"],
                }
            )

        products.append(
            {
                "isu_code": code,
                "isu_name": source.isu_name,
                "classification": classification,
                "fsc_join_status": join_product["match_status"],
                "fsc_support": fsc_support,
                "fsc_exact_fund": exact_fund,
                "fsc_name_candidate": suggestion,
                "disclosure_verification": (
                    {"status": "verified", **disclosure}
                    if disclosure
                    else {"status": "not_required"}
                ),
                "evidence": evidence,
                "warnings": warnings,
            }
        )

    target = [row for row in products if row["fsc_join_status"] == "unmatched"]
    target_assets = Counter(
        row["classification"]["asset_class"] for row in target
    )
    target_confidence = Counter(
        row["classification"]["classification_confidence"] for row in target
    )
    target_regions = Counter(row["classification"]["region"] for row in target)
    replication = Counter(
        row["classification"]["replication_method"] for row in target
    )
    all_assets = Counter(
        row["classification"]["asset_class"] for row in products
    )
    all_confidence = Counter(
        row["classification"]["classification_confidence"] for row in products
    )
    all_hedge = Counter(
        row["classification"]["currency_hedge"] for row in products
    )
    all_style = Counter(
        row["classification"]["management_style"] for row in products
    )
    component_status = Counter(
        row["classification"]["component_profile"]["status"]
        for row in products
    )
    component_asset_signal = Counter(
        row["classification"]["component_profile"]["asset_class_signal"]
        for row in products
    )
    generated_at = datetime.now(UTC).isoformat()
    return {
        "as_of": as_of.isoformat(),
        "generated_at": generated_at,
        "engine_name": "rule_based_etf_asset_classification",
        "engine_version": "2026-07-15.2",
        "source_files": {
            "krx": krx_path.as_posix(),
            "kis": kis_path.as_posix(),
            "fsc_funds": fsc_fund_path.as_posix(),
            "fsc_join": fsc_join_path.as_posix(),
        },
        "product_count": len(products),
        "asset_class_counts": dict(sorted(all_assets.items())),
        "classification_confidence_counts": dict(sorted(all_confidence.items())),
        "currency_hedge_counts": dict(sorted(all_hedge.items())),
        "management_style_counts": dict(sorted(all_style.items())),
        "component_status_counts": dict(sorted(component_status.items())),
        "component_asset_signal_counts": dict(
            sorted(component_asset_signal.items())
        ),
        "issuer_disclosure_verification_count": sum(
            row["disclosure_verification"]["status"] == "verified"
            for row in products
        ),
        "unknown_currency_hedge_count": all_hedge.get("unknown", 0),
        "inferred_management_style_count": sum(
            row["classification"]["management_style_confidence"] != "high"
            for row in products
        ),
        "fsc_unmatched_target_count": len(target),
        "fsc_unmatched_classified_count": sum(
            row["classification"]["asset_class"] != "unknown" for row in target
        ),
        "fsc_unmatched_asset_class_counts": dict(sorted(target_assets.items())),
        "fsc_unmatched_region_counts": dict(sorted(target_regions.items())),
        "fsc_unmatched_confidence_counts": dict(sorted(target_confidence.items())),
        "fsc_unmatched_replication_counts": dict(sorted(replication.items())),
        "fsc_probable_compatible_candidate_count": sum(
            row["fsc_support"] == "probable_compatible_name_candidate"
            for row in target
        ),
        "limitations": [
            "FSC name candidates do not replace exact fund identity matches",
            "unhedged status without an explicit marker is an inference",
            "domestic region without a foreign marker is an inference",
            "KIS component arrays are unavailable for some ETFs",
            "component holdings may be collateral for derivatives and therefore "
            "do not override an explicit benchmark classification",
            "KIS crcd is the KRW listing currency, not underlying currency exposure",
            "classification is deterministic and must be reviewed when source "
            "names change",
        ],
        "products": products,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify the KRX ETF universe using KRX, KIS, and FSC evidence."
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--krx", type=Path)
    parser.add_argument("--kis", type=Path)
    parser.add_argument("--fsc-funds", type=Path)
    parser.add_argument("--fsc-join", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = build_classification_report(
        krx_path=args.krx or _latest(DEFAULT_KRX_ROOT, "etf_market_evidence_*.json"),
        kis_path=args.kis or _latest(DEFAULT_KIS_ROOT, "etf_snapshot_*.json"),
        fsc_fund_path=args.fsc_funds
        or _latest(DEFAULT_FSC_ROOT, "fund_product_basic_*.json"),
        fsc_join_path=args.fsc_join
        or _latest(DEFAULT_FSC_ROOT, "krx_etf_fund_join_*.json"),
        as_of=args.as_of,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"etf_asset_classification_{args.as_of}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    public = {key: value for key, value in report.items() if key != "products"}
    public["output_path"] = path.as_posix()
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
