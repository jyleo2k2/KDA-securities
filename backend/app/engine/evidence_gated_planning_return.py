"""Accuracy-first planning assumptions with evidence-gated overlays."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from .models import SourceChip

ENGINE_NAME = "evidence_gated_style_planning_return"
ENGINE_VERSION = "2026-07-20.1"
POLICY_VERSION = "evidence-gated-planning-return-2026-07-20.1"
PERCENT_QUANTUM = Decimal("0.0001")
MINIMUM_HOLDOUT_VINTAGES = 3


class OverlayValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    short_horizon_holdout_passed: bool
    holdout_vintage_count: int = Field(ge=0)
    long_horizon_independent_validation_passed: bool
    cma_holdout_mae_percent_point: Decimal = Field(ge=0)
    candidate_holdout_mae_percent_point: Decimal = Field(ge=0)
    cma_holdout_rmse_percent_point: Decimal = Field(ge=0)
    candidate_holdout_rmse_percent_point: Decimal = Field(ge=0)


class EvidenceGatedPlanningReturnInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    etf_code: str = Field(min_length=1)
    style_key: str = Field(min_length=1)
    cma_percent: Decimal = Field(ge=Decimal("-20"), le=Decimal("30"))
    candidate_historical_adjustment_percent_point: Decimal
    candidate_macro_adjustment_percent_point: Decimal
    annual_cost_drag_percent: Decimal = Field(ge=0, le=Decimal("10"))
    diagnostic_band_width_percent_point: Decimal = Field(ge=0, le=Decimal("10"))
    validation: OverlayValidationEvidence
    sources: list[SourceChip] = Field(min_length=3)


class EvidenceGatedPlanningReturnEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    evaluated_input: EvidenceGatedPlanningReturnInput
    overlay_gate_passed: bool
    overlay_gate_failures: list[str]
    candidate_adjustment_percent_point: Decimal
    applied_adjustment_percent_point: Decimal
    gross_planning_return_percent: Decimal
    net_planning_return_percent: Decimal
    conservative_planning_return_percent: Decimal
    optimistic_planning_return_percent: Decimal
    historical_performance_used_for_central_estimate: bool
    macro_outlook_used_for_central_estimate: bool
    is_forecast: bool
    warnings: list[str]


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _gate_failures(evidence: OverlayValidationEvidence) -> list[str]:
    failures = []
    if not evidence.short_horizon_holdout_passed:
        failures.append("short_horizon_holdout_not_improved")
    if evidence.holdout_vintage_count < MINIMUM_HOLDOUT_VINTAGES:
        failures.append("fewer_than_three_holdout_vintages")
    if (
        evidence.candidate_holdout_mae_percent_point
        >= evidence.cma_holdout_mae_percent_point
    ):
        failures.append("candidate_mae_not_better_than_cma")
    if (
        evidence.candidate_holdout_rmse_percent_point
        >= evidence.cma_holdout_rmse_percent_point
    ):
        failures.append("candidate_rmse_not_better_than_cma")
    if not evidence.long_horizon_independent_validation_passed:
        failures.append("no_independent_long_horizon_validation")
    return failures


def calculate_evidence_gated_planning_return(
    assumption: EvidenceGatedPlanningReturnInput,
) -> EvidenceGatedPlanningReturnEvaluation:
    """Use an overlay only after it beats CMA out of sample at both horizons."""

    candidate = (
        assumption.candidate_historical_adjustment_percent_point
        + assumption.candidate_macro_adjustment_percent_point
    )
    failures = _gate_failures(assumption.validation)
    gate_passed = not failures
    applied = candidate if gate_passed else Decimal("0")
    gross = assumption.cma_percent + applied
    net = gross - assumption.annual_cost_drag_percent
    width = assumption.diagnostic_band_width_percent_point

    warnings = [
        "planning_assumption_not_return_forecast",
        "diagnostic_band_has_no_probability_attached",
        "past_performance_does_not_adjust_central_value_without_validation",
        "annual_review_required",
    ]
    if not gate_passed:
        warnings.append("candidate_overlay_rejected_cma_only_center_used")

    return EvidenceGatedPlanningReturnEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        usage_label="evidence_gated_long_term_planning_assumption",
        evaluated_input=assumption,
        overlay_gate_passed=gate_passed,
        overlay_gate_failures=failures,
        candidate_adjustment_percent_point=_percent(candidate),
        applied_adjustment_percent_point=_percent(applied),
        gross_planning_return_percent=_percent(gross),
        net_planning_return_percent=_percent(net),
        conservative_planning_return_percent=_percent(net - width),
        optimistic_planning_return_percent=_percent(net + width),
        historical_performance_used_for_central_estimate=gate_passed,
        macro_outlook_used_for_central_estimate=gate_passed,
        is_forecast=False,
        warnings=warnings,
    )
