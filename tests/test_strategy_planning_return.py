from decimal import Decimal

from backend.app.engine.strategy_planning_return import (
    calculate_strategy_planning_returns,
)


def test_home_strategy_returns_are_calculated_from_complete_reference_baskets() -> None:
    outcomes = calculate_strategy_planning_returns()

    assert len(outcomes) == 10
    by_id = {outcome.strategy_id: outcome for outcome in outcomes}
    assert by_id["market_beta"].net_planning_return_percent == Decimal("6.7500")
    assert by_id["top_down"].net_planning_return_percent == Decimal("5.6500")
    assert by_id["barbell"].net_planning_return_percent == Decimal("4.7500")
    assert by_id["volatility_managed"].net_planning_return_percent == Decimal("4.6300")
    assert by_id["market_neutral"].net_planning_return_percent == Decimal("3.4000")
    assert by_id["event_driven"].net_planning_return_percent == Decimal("4.3000")
    assert all(
        outcome.stress_risk.worst_scenario_code == "equity_drawdown"
        for outcome in outcomes
    )
    assert all(
        outcome.stress_risk.worst_estimated_loss_percent == Decimal("15.0000")
        for outcome in outcomes
    )
    assert {
        tuple(
            (scenario.scenario_code, scenario.estimated_loss_percent)
            for scenario in outcome.stress_risk.scenarios
        )
        for outcome in outcomes
    } == {
        (
            ("equity_drawdown", Decimal("15.0000")),
            ("rate_inflation_shock", Decimal("10.0000")),
            ("stagflation", Decimal("12.0000")),
        )
    }
    assert all(
        sum(component.target_percent for component in outcome.components)
        == Decimal("100")
        for outcome in outcomes
    )
    assert all(outcome.annual_review_required for outcome in outcomes)
    assert all(outcome.is_forecast is False for outcome in outcomes)
    assert all(len(outcome.stress_risk.scenarios) == 3 for outcome in outcomes)
    assert all(outcome.stress_risk.is_forecast is False for outcome in outcomes)
    assert all(
        outcome.stress_risk.representative_basket_only is False for outcome in outcomes
    )
    assert all(
        "shared_stress_policy_across_strategies" in outcome.warnings
        for outcome in outcomes
    )
