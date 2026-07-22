"""Measure revisions in Fama-French annual market-return outcome vintages."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from backend.app.ingestion._files import atomic_write_json, sha256_hex
from backend.app.structural_market_evidence import parse_fama_french_annual_returns

PERCENT_QUANTUM = Decimal("0.0001")
DEFAULT_REFERENCE_PATH = Path(
    "data/reference/fama_french_outcome_vintages_2022-2025.json"
)
DEFAULT_OUTPUT_PATH = Path(
    "data/cache/planning_returns/fama_french_vintage_revision.json"
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _annualized(values: list[Decimal]) -> Decimal:
    wealth = Decimal("1")
    for value in values:
        wealth *= Decimal("1") + value / Decimal("100")
    result = math.pow(float(wealth), 1 / len(values)) - 1
    return _percent(Decimal(str(result)) * Decimal("100"))


def build_revision_report(
    *,
    reference: dict[str, Any],
    current_content: bytes,
    vintage_contents: dict[int, bytes],
) -> dict[str, Any]:
    current = parse_fama_french_annual_returns(current_content)
    rows = []
    manifests = []
    for item in reference.get("vintages") or []:
        formation_year = int(item["formation_year"])
        content = vintage_contents.get(formation_year)
        if content is None:
            raise ValueError(f"missing vintage content for {formation_year}")
        archived = parse_fama_french_annual_returns(content)
        years = list(range(formation_year + 1, formation_year + 11))
        if not all(year in archived and year in current for year in years):
            raise ValueError(f"incomplete ten-year outcome for {formation_year}")
        archived_cagr = _annualized([archived[year] for year in years])
        current_cagr = _annualized([current[year] for year in years])
        annual_revisions = [current[year] - archived[year] for year in years]
        rows.append(
            {
                "formation_year": formation_year,
                "realized_window": f"{years[0]}-{years[-1]}",
                "archived_release_month": item["release_month"],
                "archived_realized_cagr_percent": str(archived_cagr),
                "current_cut_realized_cagr_percent": str(current_cagr),
                "current_minus_archived_cagr_percent_point": str(
                    _percent(current_cagr - archived_cagr)
                ),
                "maximum_absolute_annual_revision_percent_point": str(
                    _percent(max(abs(value) for value in annual_revisions))
                ),
            }
        )
        manifests.append(
            {
                "formation_year": formation_year,
                "source_url": item["url"],
                "path": item["path"],
                "sha256": sha256_hex(content),
            }
        )
    if not rows:
        raise ValueError("at least one outcome vintage is required")
    absolute_cagr_revisions = [
        abs(Decimal(row["current_minus_archived_cagr_percent_point"]))
        for row in rows
    ]
    return {
        "report_type": "fama_french_outcome_vintage_revision",
        "generated_at": datetime.now(UTC).isoformat(),
        "usage_label": "revision_diagnostic_not_return_forecast",
        "is_forecast": False,
        "scope": {
            "vintage_count": len(rows),
            "horizon_years": 10,
        },
        "summary": {
            "mean_absolute_cagr_revision_percent_point": str(
                _percent(sum(absolute_cagr_revisions) / Decimal(len(rows)))
            ),
            "maximum_absolute_cagr_revision_percent_point": str(
                _percent(max(absolute_cagr_revisions))
            ),
            "current_cut_substitution_allowed": False,
        },
        "vintages": rows,
        "source_manifests": manifests,
        "limitations": [
            (
                "2015 formation-year outcome ending in 2025 has no later "
                "archived annual cut yet."
            ),
            (
                "The return proxy remains the Fama-French U.S. value-weight "
                "market, not the S&P 500."
            ),
            (
                "The current cut uses CRSP CIZ while pre-2025 archives use the "
                "legacy FIZ process, so differences include methodology changes."
            ),
        ],
    }


def run(
    *,
    reference_path: Path = DEFAULT_REFERENCE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    reference = _load(reference_path)
    current_content = Path(reference["current_cut_path"]).read_bytes()
    vintage_contents = {
        int(item["formation_year"]): Path(item["path"]).read_bytes()
        for item in reference["vintages"]
    }
    report = build_revision_report(
        reference=reference,
        current_content=current_content,
        vintage_contents=vintage_contents,
    )
    atomic_write_json(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    report = run(reference_path=args.reference, output_path=args.output)
    print(
        json.dumps(
            {
                "scope": report["scope"],
                "summary": report["summary"],
                "output_path": args.output.as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
