"""Reproduce a disclosed long-horizon CMA validation case."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENGINE_NAME = "cma_long_horizon_validation"
ENGINE_VERSION = "2026-07-20.1"
DEFAULT_REFERENCE_PATH = Path(
    "data/reference/cma_long_horizon_validation_2011-2025.json"
)
DEFAULT_OUTPUT_PATH = Path(
    "data/cache/planning_returns/cma_long_horizon_validation_2025-09-30.json"
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("reference root must be an object")
    return payload


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    parsed = float(value)
    if positive and parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _cagr(initial: float, terminal: float, years: float) -> float:
    return ((terminal / initial) ** (1 / years) - 1) * 100


def validate_reference(payload: dict[str, Any]) -> None:
    scenario = payload.get("scenario")
    path = payload.get("path")
    if not isinstance(scenario, dict) or not isinstance(path, list) or not path:
        raise ValueError("scenario object and non-empty path are required")

    _number(scenario.get("initial_wealth_usd_million"), "initial wealth", positive=True)
    _number(scenario.get("publisher_horizon_years"), "publisher horizon", positive=True)
    _number(
        scenario.get("calendar_elapsed_years_through_2025_09"),
        "calendar elapsed years",
        positive=True,
    )
    _number(scenario.get("cma_compound_return_percent"), "CMA return")

    labels: set[str] = set()
    for index, point in enumerate(path):
        if not isinstance(point, dict):
            raise ValueError(f"path[{index}] must be an object")
        label = point.get("label")
        if not isinstance(label, str) or not label or label in labels:
            raise ValueError(f"path[{index}] label must be unique")
        labels.add(label)
        low = _number(point.get("percentile_5"), f"path[{index}] percentile_5")
        median = _number(point.get("median"), f"path[{index}] median")
        high = _number(point.get("percentile_95"), f"path[{index}] percentile_95")
        _number(point.get("realized"), f"path[{index}] realized")
        if not low <= median <= high:
            raise ValueError(f"path[{index}] must satisfy p5 <= median <= p95")


def calculate_validation(payload: dict[str, Any]) -> dict[str, Any]:
    validate_reference(payload)
    scenario = payload["scenario"]
    path = payload["path"]
    initial = float(scenario["initial_wealth_usd_million"])
    publisher_years = float(scenario["publisher_horizon_years"])
    calendar_years = float(scenario["calendar_elapsed_years_through_2025_09"])
    cma_return = float(scenario["cma_compound_return_percent"])
    terminal = path[-1]
    terminal_realized = float(terminal["realized"])
    terminal_median = float(terminal["median"])
    terminal_low = float(terminal["percentile_5"])
    terminal_high = float(terminal["percentile_95"])

    path_results = []
    for point in path:
        realized = float(point["realized"])
        inside = float(point["percentile_5"]) <= realized <= float(
            point["percentile_95"]
        )
        path_results.append(
            {"label": point["label"], "inside_90_percent_interval": inside}
        )
    inside_count = sum(point["inside_90_percent_interval"] for point in path_results)

    publisher_cagr = _cagr(initial, terminal_realized, publisher_years)
    calendar_cagr = _cagr(initial, terminal_realized, calendar_years)
    return {
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION},
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of_date": payload.get("as_of_date"),
        "is_forecast": False,
        "source": payload.get("source"),
        "scope": {
            "vintage": scenario.get("vintage"),
            "allocation": scenario.get("allocation"),
            "observation_count": len(path),
            "evidence_independence": "vendor_self_evaluation",
        },
        "metrics": {
            "path_inside_90_percent_interval_count": inside_count,
            "path_observation_count": len(path),
            "path_coverage_percent": round(inside_count / len(path) * 100, 4),
            "terminal_initial_wealth_usd_million": initial,
            "terminal_realized_wealth_usd_million": terminal_realized,
            "terminal_median_wealth_usd_million": terminal_median,
            "terminal_percentile_5_wealth_usd_million": terminal_low,
            "terminal_percentile_95_wealth_usd_million": terminal_high,
            "terminal_realized_vs_median_percent": round(
                (terminal_realized / terminal_median - 1) * 100, 4
            ),
            "cma_compound_return_percent": cma_return,
            "publisher_15y_realized_cagr_percent": round(publisher_cagr, 4),
            "publisher_15y_point_error_percent_point": round(
                publisher_cagr - cma_return, 4
            ),
            "calendar_14_75y_realized_cagr_percent": round(calendar_cagr, 4),
            "calendar_14_75y_point_error_percent_point": round(
                calendar_cagr - cma_return, 4
            ),
            "terminal_percentile_5_implied_cagr_percent": round(
                _cagr(initial, terminal_low, publisher_years), 4
            ),
            "terminal_percentile_95_implied_cagr_percent": round(
                _cagr(initial, terminal_high, publisher_years), 4
            ),
        },
        "path_checks": path_results,
        "decision": {
            "single_case_range_calibration": "supported",
            "single_case_point_estimate": "close_but_no_predeclared_accuracy_threshold",
            "general_cma_accuracy": "not_validated",
            "reason": (
                "단일 공급자 자기평가·단일 빈티지·단일 배분 사례이므로 "
                "일반화할 수 없다."
            ),
            "production_parameter_change_authorized": False,
        },
        "limitations": payload.get("limitations") or [],
    }


def run(reference_path: Path, output_path: Path) -> dict[str, Any]:
    result = calculate_validation(_load(reference_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    result = run(args.reference, args.output)
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
