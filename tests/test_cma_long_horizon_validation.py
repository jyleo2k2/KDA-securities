import json
from pathlib import Path

import pytest

from backend.app.cma_long_horizon_validation import (
    calculate_validation,
    run,
    validate_reference,
)

REFERENCE_PATH = Path("data/reference/cma_long_horizon_validation_2011-2025.json")


def _reference() -> dict:
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def test_official_case_reports_path_coverage_and_both_horizon_conventions() -> None:
    result = calculate_validation(_reference())
    metrics = result["metrics"]

    assert metrics["path_inside_90_percent_interval_count"] == 15
    assert metrics["path_observation_count"] == 15
    assert metrics["path_coverage_percent"] == 100.0
    assert metrics["publisher_15y_realized_cagr_percent"] == pytest.approx(6.8458)
    assert metrics["publisher_15y_point_error_percent_point"] == pytest.approx(0.3458)
    assert metrics["calendar_14_75y_realized_cagr_percent"] == pytest.approx(6.9658)
    assert metrics["calendar_14_75y_point_error_percent_point"] == pytest.approx(0.4658)
    assert metrics["terminal_realized_vs_median_percent"] == pytest.approx(5.0584)
    assert result["decision"]["general_cma_accuracy"] == "not_validated"
    assert result["decision"]["production_parameter_change_authorized"] is False


def test_invalid_percentile_order_is_rejected() -> None:
    payload = _reference()
    payload["path"][0]["median"] = 90

    with pytest.raises(ValueError, match="p5 <= median <= p95"):
        validate_reference(payload)


def test_run_writes_reproducible_result(tmp_path: Path) -> None:
    output_path = tmp_path / "result.json"
    result = run(REFERENCE_PATH, output_path)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["metrics"] == result["metrics"]
    assert saved["is_forecast"] is False
