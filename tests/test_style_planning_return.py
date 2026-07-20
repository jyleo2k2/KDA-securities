import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.engine.models import SourceChip
from backend.app.engine.style_planning_return import (
    MacroRevisionSignals,
    MacroSensitivities,
    StylePlanningReturnInput,
    calculate_style_planning_return,
    style_macro_sensitivities,
)
from backend.app.etf_style_planning_report import (
    _annualized_total_return,
    build_style_planning_report,
)


def _source(label: str) -> SourceChip:
    return SourceChip(
        label=label,
        reference=f"https://example.com/{label}",
        as_of=date(2026, 7, 20),
    )


def test_style_planning_return_shrinks_and_caps_history_and_macro() -> None:
    result = calculate_style_planning_return(
        StylePlanningReturnInput(
            etf_code="TEST",
            style_key="equity:broad_market:united_states",
            cma_assumption_code="us_large_cap_equity",
            cma_percent=Decimal("6"),
            historical_annualized_return_percent=Decimal("16"),
            historical_period="5y",
            historical_peer_count=10,
            macro_signals=MacroRevisionSignals(
                region="united_states",
                growth_revision_percent_point=Decimal("1"),
                inflation_revision_percent_point=Decimal("1"),
                policy_rate_revision_percent_point=Decimal("1"),
                uncertainty_level="high",
            ),
            macro_sensitivities=MacroSensitivities(
                growth=Decimal("1"),
                inflation=Decimal("1"),
                policy_rate=Decimal("1"),
            ),
            uncertainty_discount_percent=Decimal("0.5"),
            annual_cost_drag_percent=Decimal("0.2"),
            sources=[_source("cma"), _source("history"), _source("macro")],
        )
    )

    assert result.historical_adjustment_percent_point == Decimal("1.0000")
    assert result.macro_adjustment_percent_point == Decimal("0.5000")
    assert result.net_planning_return_percent == Decimal("6.8000")
    assert result.conservative_planning_return_percent == Decimal("5.3000")
    assert result.optimistic_planning_return_percent == Decimal("8.3000")
    assert result.is_forecast is False


def test_style_macro_sensitivity_differs_by_investment_style() -> None:
    broad = style_macro_sensitivities(
        asset_class="equity", strategy="broad_market"
    )
    thematic = style_macro_sensitivities(
        asset_class="equity", strategy="sector_or_theme"
    )
    bond = style_macro_sensitivities(
        asset_class="fixed_income", strategy="government_bond"
    )

    assert thematic.growth > broad.growth
    assert thematic.policy_rate < broad.policy_rate
    assert bond.policy_rate > 0


def test_total_return_is_annualized_from_observation_count() -> None:
    product = {
        "returns": {
            "5y": {
                "status": "complete",
                "observation_count": 1261,
                "distribution_reinvested_total_return_percent": "61.051",
            }
        }
    }

    result = _annualized_total_return(product, "5y")

    assert result is not None
    assert result.quantize(Decimal("0.0001")) == Decimal("10.0000")


def test_report_builds_style_and_etf_ranges_from_verified_inputs(
    tmp_path: Path,
) -> None:
    products = []
    for index in range(5):
        products.append(
            {
                "isu_code": f"TEST{index}",
                "isu_name": f"Test ETF {index}",
                "classification": {
                    "asset_class": "equity",
                    "strategy": "broad_market",
                    "region": "united_states",
                    "classification_confidence": "high",
                    "currency_hedge": "hedged",
                },
                "cost": {"effective_total_cost_percent": "0.1"},
                "returns": {
                    "5y": {
                        "status": "complete",
                        "observation_count": 1261,
                        "distribution_reinvested_total_return_percent": "61.051",
                    }
                },
            }
        )
    return_master = tmp_path / "returns.json"
    return_master.write_text(
        json.dumps({"as_of": "2026-07-20", "products": products}),
        encoding="utf-8",
    )

    report = build_style_planning_report(
        return_master_path=return_master,
        outlook_path=Path(
            "data/reference/macro_outlook_scenarios_2026-07-20.json"
        ),
    )

    assert report["estimated_product_count"] == 5
    assert report["excluded_product_count"] == 0
    assert report["style_count"] == 1
    assert len(report["style_summaries"]) == 1
    assert all(item["is_forecast"] is False for item in report["etf_estimates"])
    first = report["etf_estimates"][0]["calculation"]
    assert first["evaluated_input"]["historical_period"] == "5y"
    assert first["evaluated_input"]["historical_peer_count"] == 5
