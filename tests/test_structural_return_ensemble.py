from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.models import SourceChip
from backend.app.engine.structural_return_ensemble import (
    CmaEstimate,
    CommodityBuildingBlocks,
    EquilibriumPrior,
    EquityBuildingBlocks,
    FixedIncomeBuildingBlocks,
    RealAssetBuildingBlocks,
    StatisticalEstimate,
    StructuralEnsembleInput,
    StructuralEstimate,
    calculate_commodity_building_block,
    calculate_equity_building_block,
    calculate_fixed_income_building_block,
    calculate_real_asset_building_block,
    calculate_structural_ensemble,
    simulate_resampled_scenarios,
)


def _source(label: str) -> SourceChip:
    return SourceChip(
        label=label,
        reference=f"https://example.com/{label}",
        as_of=date(2026, 7, 20),
    )


def _cmas() -> list[CmaEstimate]:
    return [
        CmaEstimate(
            provider="one",
            expected_return_percent=Decimal("6.7"),
            source=_source("one"),
        ),
        CmaEstimate(
            provider="two",
            expected_return_percent=Decimal("5.8"),
            source=_source("two"),
        ),
    ]


def test_asset_class_building_blocks_are_transparent_sums() -> None:
    assert calculate_equity_building_block(
        EquityBuildingBlocks(
            dividend_yield_percent=Decimal("1.5"),
            nominal_revenue_growth_percent=Decimal("4.5"),
            margin_change_percent_point=Decimal("-0.2"),
            net_dilution_percent_point=Decimal("0.3"),
            valuation_change_annualized_percent_point=Decimal("-0.5"),
        )
    ) == Decimal("5.0000")
    assert calculate_fixed_income_building_block(
        FixedIncomeBuildingBlocks(
            coupon_income_percent=Decimal("4.5"),
            duration_impact_percent_point=Decimal("0.2"),
            curve_roll_down_percent_point=Decimal("0.1"),
            default_and_loss_percent_point=Decimal("0.3"),
        )
    ) == Decimal("4.5000")
    assert calculate_real_asset_building_block(
        RealAssetBuildingBlocks(
            net_operating_yield_percent=Decimal("5"),
            maintenance_capex_percent_point=Decimal("0.5"),
            net_cash_flow_growth_percent=Decimal("2"),
            exit_yield_adjustment_percent_point=Decimal("-0.4"),
            leverage_adjustment_percent_point=Decimal("0.3"),
            fee_drag_percent_point=Decimal("0.4"),
        )
    ) == Decimal("6.0000")
    assert calculate_commodity_building_block(
        CommodityBuildingBlocks(
            cash_return_percent=Decimal("3"),
            spot_premium_percent_point=Decimal("1"),
            roll_yield_percent_point=Decimal("-0.5"),
        )
    ) == Decimal("3.5000")


def test_partial_inputs_calculate_consensus_but_block_adoption() -> None:
    result = calculate_structural_ensemble(
        StructuralEnsembleInput(
            asset_code="us_large_cap_equity",
            horizon_years=10,
            cma_estimates=_cmas(),
            annual_cost_drag_percent=Decimal("0.2"),
        )
    )

    assert result.cma_consensus_percent == Decimal("6.2500")
    assert result.net_planning_return_percent == Decimal("6.0500")
    assert result.readiness_status == "partial_inputs"
    assert result.adoption_authorized is False
    assert result.is_forecast is False


def test_full_inputs_use_robust_categories_and_equilibrium_shrinkage() -> None:
    result = calculate_structural_ensemble(
        StructuralEnsembleInput(
            asset_code="us_large_cap_equity",
            horizon_years=10,
            cma_estimates=_cmas(),
            structural_estimate=StructuralEstimate(
                expected_return_percent=Decimal("5.5"),
                method="equity_building_blocks",
                source=_source("building"),
            ),
            statistical_estimate=StatisticalEstimate(
                expected_return_percent=Decimal("7.0"),
                holdout_vintage_count=3,
                beats_cma_mae=True,
                beats_cma_rmse=True,
                independent_long_horizon_passed=True,
                source=_source("statistical"),
            ),
            equilibrium_prior=EquilibriumPrior(
                expected_return_percent=Decimal("6.0"),
                view_confidence=Decimal("0.5"),
                source=_source("equilibrium"),
            ),
            annual_cost_drag_percent=Decimal("0.2"),
            tracking_drag_percent=Decimal("0.1"),
            ensemble_external_validation_passed=True,
        )
    )

    assert result.robust_view_percent == Decimal("6.2500")
    assert result.equilibrium_shrunk_percent == Decimal("6.1250")
    assert result.net_planning_return_percent == Decimal("5.8250")
    assert result.statistical_estimate_used is True
    assert result.readiness_status == "full_inputs_validated"
    assert result.adoption_authorized is True


def test_empirical_resampling_is_deterministic_and_non_parametric() -> None:
    residuals = [Decimal(value) for value in range(-9, 11)]

    first = simulate_resampled_scenarios(
        center_percent=Decimal("6"),
        historical_annual_residuals_percent=residuals,
        horizon_years=10,
        scenario_count=200,
        seed=7,
    )
    second = simulate_resampled_scenarios(
        center_percent=Decimal("6"),
        historical_annual_residuals_percent=residuals,
        horizon_years=10,
        scenario_count=200,
        seed=7,
    )

    assert first == second
    assert first.p10_annualized_percent < first.p50_annualized_percent
    assert first.p50_annualized_percent < first.p90_annualized_percent
    assert first.is_forecast is False


def test_resampling_requires_enough_long_horizon_residuals() -> None:
    with pytest.raises(ValueError, match="at least 10"):
        simulate_resampled_scenarios(
            center_percent=Decimal("6"),
            historical_annual_residuals_percent=[Decimal("0")] * 9,
            horizon_years=10,
        )


def test_duplicate_cma_provider_is_rejected() -> None:
    duplicate = _cmas()
    duplicate[1] = duplicate[1].model_copy(update={"provider": "one"})

    with pytest.raises(ValidationError, match="providers must be distinct"):
        StructuralEnsembleInput(
            asset_code="us_large_cap_equity",
            horizon_years=10,
            cma_estimates=duplicate,
            annual_cost_drag_percent=Decimal("0.2"),
        )
