import json
from pathlib import Path

from backend.app.accuracy_first_style_planning_report import (
    build_accuracy_first_report,
)


def test_report_rejects_current_overlay_and_keeps_cma_cost_center(
    tmp_path: Path,
) -> None:
    source = {
        "label": "source",
        "reference": "https://example.com/source",
        "as_of": "2026-07-20",
    }
    style_path = tmp_path / "style.json"
    style_path.write_text(
        json.dumps(
            {
                "as_of": "2026-07-20",
                "etf_estimates": [
                    {
                        "isu_code": "TEST",
                        "isu_name": "Test ETF",
                        "asset_class": "equity",
                        "strategy": "broad_market",
                        "region": "global",
                        "classification_style_key": "equity:broad_market:global",
                        "cma_proxy_used": False,
                        "calculation": {
                            "historical_adjustment_percent_point": "0.8",
                            "macro_adjustment_percent_point": "0.2",
                            "range_width_percent_point": "1.2",
                            "evaluated_input": {
                                "cma_percent": "7.1",
                                "annual_cost_drag_percent": "0.3",
                                "sources": [source, source, source],
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    backtest_path = tmp_path / "backtest.json"
    backtest_path.write_text(
        json.dumps(
            {
                "scope": {"holdout_vintage_count": 1},
                "adoption_gate": {"short_horizon_gate_passed": False},
                "model_comparison": {
                    "holdout": {
                        "cma_only": {
                            "style_vintage_level": {
                                "mae_percent_point": "29.3439",
                                "rmse_percent_point": "32.4362",
                            }
                        },
                        "combined": {
                            "style_vintage_level": {
                                "mae_percent_point": "29.7764",
                                "rmse_percent_point": "32.8798",
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    long_path = tmp_path / "long.json"
    long_path.write_text(
        json.dumps(
            {
                "scope": {"evidence_independence": "vendor_self_evaluation"},
                "decision": {"general_cma_accuracy": "not_validated"},
            }
        ),
        encoding="utf-8",
    )

    result = build_accuracy_first_report(
        style_report_path=style_path,
        backtest_path=backtest_path,
        long_validation_path=long_path,
    )

    calculation = result["etf_estimates"][0]["calculation"]
    assert result["overlay_adopted"] is False
    assert calculation["applied_adjustment_percent_point"] == "0.0000"
    assert calculation["net_planning_return_percent"] == "6.8000"
    assert result["is_forecast"] is False
