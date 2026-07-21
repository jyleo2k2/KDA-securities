import json

from scripts.build_demo_public_portfolio_metrics import OUTPUT_PATH, build


def test_demo_public_portfolio_metrics_are_current_and_not_forecasts() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    assert payload == build()
    assert payload["return_metric"]["is_forecast"] is False
    assert payload["return_metric"]["official_ranking_metric"] is False
    assert payload["like_metric"]["is_synthetic"] is True
    assert payload["like_metric"]["performance_based"] is False
    assert len(payload["profiles"]) == 6
    assert len({item["like_count"] for item in payload["profiles"]}) == 6
    assert {item["return_period_end"] for item in payload["profiles"]} == {
        "2025-12-31"
    }
