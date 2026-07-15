from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.aggregation import (
    AGGREGATION_NOTICE,
    AggregationInput,
    aggregate_accounts,
)
from backend.app.engine.models import AssetClass
from tests.scenario_fixtures import (
    overlap_dc_account,
    overlap_irp_account,
    overlap_pension_savings_account,
)


def overlap_scenario_input() -> AggregationInput:
    return AggregationInput(
        accounts=[
            overlap_dc_account(),
            overlap_irp_account(),
            overlap_pension_savings_account(),
        ]
    )


def test_overlap_scenario_totals_match_seed_amounts() -> None:
    evaluation = aggregate_accounts(overlap_scenario_input())
    assert evaluation.total_amount_krw == Decimal("190000000.00")
    contributions = {
        contribution.account_id: contribution
        for contribution in evaluation.per_account
    }
    assert contributions["overlap_risk_concentration/dc"].amount_krw == Decimal(
        "100000000.00"
    )
    assert contributions["overlap_risk_concentration/irp"].amount_krw == Decimal(
        "50000000.00"
    )
    assert contributions[
        "overlap_risk_concentration/pension_savings"
    ].amount_krw == Decimal("40000000.00")


def test_overlap_scenario_flags_global_equity_across_three_accounts() -> None:
    evaluation = aggregate_accounts(overlap_scenario_input())
    assert len(evaluation.overlaps) == 1
    overlap = evaluation.overlaps[0]
    assert overlap.asset_class == AssetClass.GLOBAL_EQUITY
    assert len(overlap.account_ids) == 3
    assert overlap.combined_amount_krw == Decimal("130000000.00")
    assert overlap.combined_weight_percent == Decimal("68.42")


def test_asset_class_amounts_sum_to_total() -> None:
    evaluation = aggregate_accounts(overlap_scenario_input())
    class_sum = sum(
        (weight.amount_krw for weight in evaluation.asset_class_totals),
        Decimal("0"),
    )
    assert class_sum == evaluation.total_amount_krw


def test_no_combined_rule_judgement_is_made() -> None:
    evaluation = aggregate_accounts(overlap_scenario_input())
    assert evaluation.notice == AGGREGATION_NOTICE
    dumped = evaluation.model_dump(mode="json")
    assert "status" not in dumped
    assert "limit_percent" not in dumped


def test_single_account_has_no_overlap() -> None:
    evaluation = aggregate_accounts(
        AggregationInput(accounts=[overlap_dc_account()])
    )
    assert evaluation.overlaps == []


def test_duplicate_account_ids_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AggregationInput(accounts=[overlap_dc_account(), overlap_dc_account()])


def test_aggregation_is_deterministic() -> None:
    first = aggregate_accounts(overlap_scenario_input()).model_dump(mode="json")
    second = aggregate_accounts(overlap_scenario_input()).model_dump(mode="json")
    assert first == second
