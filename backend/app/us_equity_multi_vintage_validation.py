"""Compare U.S. equity CMA and structural anchors over complete 10y vintages."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from backend.app.ingestion._files import atomic_write_json

ENGINE_NAME = "us_equity_multi_vintage_validation"
ENGINE_VERSION = "2026-07-20.1"
PERCENT_QUANTUM = Decimal("0.0001")
DEFAULT_VINTAGE_PATH = Path(
    "data/reference/us_equity_cma_vintages_2012-2016.json"
)
DEFAULT_EVIDENCE_PATH = Path(
    "data/cache/planning_returns/structural_market_evidence_latest.json"
)
DEFAULT_OUTPUT_PATH = Path(
    "data/cache/planning_returns/us_equity_multi_vintage_validation.json"
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _metrics(errors: list[Decimal]) -> dict[str, str | int]:
    if not errors:
        raise ValueError("metrics require at least one error")
    count = Decimal(len(errors))
    return {
        "observation_count": len(errors),
        "mae_percent_point": str(
            _percent(sum(abs(value) for value in errors) / count)
        ),
        "rmse_percent_point": str(
            _percent((sum(value * value for value in errors) / count).sqrt())
        ),
        "mean_bias_percent_point": str(_percent(sum(errors) / count)),
    }


def _validate_vintages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    vintages = payload.get("vintages")
    if not isinstance(vintages, list) or len(vintages) < 3:
        raise ValueError("at least three CMA vintages are required")
    years = []
    for item in vintages:
        if not isinstance(item, dict):
            raise ValueError("each CMA vintage must be an object")
        year = item.get("formation_year")
        if not isinstance(year, int):
            raise ValueError("formation_year must be an integer")
        Decimal(item["expected_return_percent"])
        years.append(year)
    if len(years) != len(set(years)):
        raise ValueError("formation years must be unique")
    return vintages


def build_validation_report(
    *,
    vintage_payload: dict[str, Any],
    structural_evidence: dict[str, Any],
) -> dict[str, Any]:
    vintages = _validate_vintages(vintage_payload)
    diagnostic_rows = {
        item["formation_year"]: item
        for item in structural_evidence["long_horizon_diagnostics"]["vintages"]
    }
    current_confidence = Decimal(
        structural_evidence["asset_inputs"]["us_large_cap_equity"][
            "view_confidence"
        ]
    )
    rows = []
    for vintage in vintages:
        formation_year = vintage["formation_year"]
        diagnostic = diagnostic_rows.get(formation_year)
        if diagnostic is None:
            raise ValueError(
                f"structural evidence missing formation year {formation_year}"
            )
        cma = Decimal(vintage["expected_return_percent"])
        structural = Decimal(diagnostic["structural_percent"])
        equilibrium = Decimal(diagnostic["equilibrium_percent"])
        realized = Decimal(diagnostic["realized_return_percent"])
        robust_view = (cma + structural) / Decimal("2")
        ensemble = equilibrium + current_confidence * (robust_view - equilibrium)
        estimates = {
            "cma": cma,
            "structural": structural,
            "equilibrium": equilibrium,
            "trailing_10y": Decimal(diagnostic["trailing_return_percent"]),
            "current_ensemble_rule": ensemble,
        }
        rows.append(
            {
                "cma_label_year": vintage["cma_label_year"],
                "formation_year": formation_year,
                "cma_as_of": vintage["as_of"],
                "realized_window": diagnostic["realized_window"],
                "estimates_percent": {
                    name: str(_percent(value)) for name, value in estimates.items()
                },
                "realized_return_percent": str(_percent(realized)),
                "errors_percent_point": {
                    name: str(_percent(value - realized))
                    for name, value in estimates.items()
                },
                "source_url": vintage["source_url"],
            }
        )

    model_names = list(rows[0]["errors_percent_point"])
    metrics = {
        name: _metrics(
            [Decimal(row["errors_percent_point"][name]) for row in rows]
        )
        for name in model_names
    }
    cma_metrics = metrics["cma"]
    ensemble_metrics = metrics["current_ensemble_rule"]
    equilibrium_metrics = metrics["equilibrium"]
    ensemble_beats_cma = (
        Decimal(ensemble_metrics["mae_percent_point"])
        < Decimal(cma_metrics["mae_percent_point"])
        and Decimal(ensemble_metrics["rmse_percent_point"])
        < Decimal(cma_metrics["rmse_percent_point"])
    )
    equilibrium_beats_cma = (
        Decimal(equilibrium_metrics["mae_percent_point"])
        < Decimal(cma_metrics["mae_percent_point"])
        and Decimal(equilibrium_metrics["rmse_percent_point"])
        < Decimal(cma_metrics["rmse_percent_point"])
    )
    return {
        "report_type": "us_equity_cma_structural_multi_vintage_validation",
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION},
        "generated_at": datetime.now(UTC).isoformat(),
        "usage_label": "retrospective_diagnostic_not_return_forecast",
        "is_forecast": False,
        "scope": {
            "vintage_count": len(rows),
            "horizon_years": 10,
            "overlapping_forward_windows": True,
            "independent_vintage_count": 1,
            "current_ensemble_view_confidence": str(current_confidence),
        },
        "metrics": metrics,
        "vintages": rows,
        "decision": {
            "current_ensemble_beats_cma_mae_and_rmse": ensemble_beats_cma,
            "equilibrium_anchor_beats_cma_mae_and_rmse": equilibrium_beats_cma,
            "strict_external_validation_passed": False,
            "production_parameter_change_authorized": False,
            "reason": (
                "현재 앙상블 규칙이 CMA를 이기지 못하고, 연속 10년 구간이 "
                "중첩되며 당시 배포본 구조 입력도 없으므로 채택하지 않는다."
            ),
        },
        "sources": {
            "cma_archive": vintage_payload.get("archive"),
            "structural_evidence_report": structural_evidence.get("report_type"),
        },
        "limitations": vintage_payload.get("limitations") or [],
    }


def run(
    *,
    vintage_path: Path = DEFAULT_VINTAGE_PATH,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    report = build_validation_report(
        vintage_payload=_load(vintage_path),
        structural_evidence=_load(evidence_path),
    )
    atomic_write_json(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintages", type=Path, default=DEFAULT_VINTAGE_PATH)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    report = run(
        vintage_path=args.vintages,
        evidence_path=args.evidence,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "vintage_count": report["scope"]["vintage_count"],
                "metrics": report["metrics"],
                "decision": report["decision"],
                "output_path": args.output.as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
