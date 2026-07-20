from datetime import date
from decimal import Decimal

from backend.app.engine.evidence_gated_planning_return import (
    EvidenceGatedPlanningReturnInput,
    OverlayValidationEvidence,
    calculate_evidence_gated_planning_return,
)
from backend.app.engine.models import SourceChip


def _sources() -> list[SourceChip]:
    return [
        SourceChip(
            label=f"source-{index}",
            reference=f"https://example.com/{index}",
            as_of=date(2026, 7, 20),
        )
        for index in range(3)
    ]


def _validation(**overrides) -> OverlayValidationEvidence:
    values = {
        "short_horizon_holdout_passed": False,
        "holdout_vintage_count": 1,
        "long_horizon_independent_validation_passed": False,
        "cma_holdout_mae_percent_point": Decimal("29.3439"),
        "candidate_holdout_mae_percent_point": Decimal("29.7764"),
        "cma_holdout_rmse_percent_point": Decimal("32.4362"),
        "candidate_holdout_rmse_percent_point": Decimal("32.8798"),
    }
    values.update(overrides)
    return OverlayValidationEvidence(**values)


def _assumption(**overrides) -> EvidenceGatedPlanningReturnInput:
    values = {
        "etf_code": "TEST",
        "style_key": "equity:broad_market:global",
        "cma_percent": Decimal("7.1"),
        "candidate_historical_adjustment_percent_point": Decimal("0.8"),
        "candidate_macro_adjustment_percent_point": Decimal("0.2"),
        "annual_cost_drag_percent": Decimal("0.3"),
        "diagnostic_band_width_percent_point": Decimal("1.2"),
        "validation": _validation(),
        "sources": _sources(),
    }
    values.update(overrides)
    return EvidenceGatedPlanningReturnInput(**values)


def test_rejected_overlay_uses_cma_minus_cost_as_center() -> None:
    result = calculate_evidence_gated_planning_return(_assumption())

    assert result.overlay_gate_passed is False
    assert result.candidate_adjustment_percent_point == Decimal("1.0000")
    assert result.applied_adjustment_percent_point == Decimal("0.0000")
    assert result.gross_planning_return_percent == Decimal("7.1000")
    assert result.net_planning_return_percent == Decimal("6.8000")
    assert result.conservative_planning_return_percent == Decimal("5.6000")
    assert result.optimistic_planning_return_percent == Decimal("8.0000")
    assert result.historical_performance_used_for_central_estimate is False
    assert result.macro_outlook_used_for_central_estimate is False
    assert result.is_forecast is False


def test_overlay_requires_every_accuracy_gate() -> None:
    validation = _validation(
        short_horizon_holdout_passed=True,
        holdout_vintage_count=3,
        long_horizon_independent_validation_passed=True,
        candidate_holdout_mae_percent_point=Decimal("28"),
        candidate_holdout_rmse_percent_point=Decimal("31"),
    )

    result = calculate_evidence_gated_planning_return(
        _assumption(validation=validation)
    )

    assert result.overlay_gate_passed is True
    assert result.overlay_gate_failures == []
    assert result.applied_adjustment_percent_point == Decimal("1.0000")
    assert result.net_planning_return_percent == Decimal("7.8000")
    assert result.historical_performance_used_for_central_estimate is True
    assert result.macro_outlook_used_for_central_estimate is True
