import json
from pathlib import Path

from backend.app.structural_ensemble_candidate_report import (
    build_candidate_report,
)


def test_candidate_report_uses_only_comparable_official_cmas(tmp_path: Path) -> None:
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
                        "region": "united_states",
                        "classification_style_key": (
                            "equity:broad_market:united_states"
                        ),
                        "cma_proxy_used": False,
                        "calculation": {
                            "evaluated_input": {
                                "cma_assumption_code": "us_large_cap_equity",
                                "annual_cost_drag_percent": "0.2",
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_candidate_report(
        style_report_path=style_path, structural_evidence_path=None
    )
    calculation = report["etf_estimates"][0]["calculation"]

    assert report["multi_cma_product_count"] == 1
    assert report["full_input_product_count"] == 0
    assert report["adoption_authorized"] is False
    assert calculation["cma_consensus_percent"] == "6.2500"
    assert calculation["net_planning_return_percent"] == "6.0500"
    assert calculation["readiness_status"] == "partial_inputs"
    assert calculation["is_forecast"] is False


def test_candidate_report_connects_structural_market_evidence(tmp_path: Path) -> None:
    style_path = tmp_path / "style.json"
    evidence_path = tmp_path / "evidence.json"
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
                        "region": "united_states",
                        "classification_style_key": (
                            "equity:broad_market:united_states"
                        ),
                        "cma_proxy_used": False,
                        "calculation": {
                            "evaluated_input": {
                                "cma_assumption_code": "us_large_cap_equity",
                                "annual_cost_drag_percent": "0.2",
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(
            {
                "asset_inputs": {
                    "us_large_cap_equity": {
                        "structural_estimate_percent": "5.7600",
                        "structural_method": "dividend_yield_plus_smoothed_growth",
                        "equilibrium_prior_percent": "8.4100",
                        "view_confidence": "0.4623",
                        "source": {
                            "label": "Academic source",
                            "reference": "https://example.test/source",
                            "as_of": "2025-12-31",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_candidate_report(
        style_report_path=style_path,
        structural_evidence_path=evidence_path,
    )
    calculation = report["etf_estimates"][0]["calculation"]

    assert report["structural_input_product_count"] == 1
    assert report["equilibrium_input_product_count"] == 1
    assert calculation["component_category_count"] == 2
    assert calculation["equilibrium_shrunk_percent"] == "7.2982"
    assert calculation["net_planning_return_percent"] == "7.0982"
    assert calculation["adoption_authorized"] is False
