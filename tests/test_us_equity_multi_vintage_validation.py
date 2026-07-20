from backend.app.us_equity_multi_vintage_validation import build_validation_report


def test_multi_vintage_report_rejects_current_ensemble_rule():
    vintage_payload = {
        "archive": {"reference": "https://example.test/archive"},
        "vintages": [
            {
                "cma_label_year": year + 1,
                "formation_year": year,
                "as_of": f"{year}-09-30",
                "expected_return_percent": "6.0",
                "source_url": "https://example.test/report",
            }
            for year in range(2011, 2014)
        ],
        "limitations": ["test limitation"],
    }
    evidence = {
        "report_type": "structural_market_evidence",
        "asset_inputs": {
            "us_large_cap_equity": {"view_confidence": "0.5"}
        },
        "long_horizon_diagnostics": {
            "vintages": [
                {
                    "formation_year": year,
                    "realized_window": f"{year + 1}-{year + 10}",
                    "structural_percent": "5.0",
                    "equilibrium_percent": "7.0",
                    "trailing_return_percent": "4.0",
                    "realized_return_percent": "8.0",
                }
                for year in range(2011, 2014)
            ]
        },
    }

    report = build_validation_report(
        vintage_payload=vintage_payload,
        structural_evidence=evidence,
    )

    assert report["scope"]["vintage_count"] == 3
    assert report["metrics"]["cma"]["mae_percent_point"] == "2.0000"
    assert report["metrics"]["equilibrium"]["mae_percent_point"] == "1.0000"
    assert report["metrics"]["current_ensemble_rule"][
        "mae_percent_point"
    ] == "1.7500"
    assert report["decision"]["equilibrium_anchor_beats_cma_mae_and_rmse"]
    assert report["decision"]["strict_external_validation_passed"] is False
    assert report["decision"]["production_parameter_change_authorized"] is False
