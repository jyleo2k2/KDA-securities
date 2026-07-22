from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import SourceChip

ENGINE_NAME = "etf_long_term_planning_return"
ENGINE_VERSION = "2026-07-22.1"
POLICY_VERSION = "2026-07-22"
PERCENT_QUANTUM = Decimal("0.0001")
INDUSTRY_ADJUSTMENT_CAP = Decimal("1.0000")
VALUATION_ADJUSTMENT_CAP = Decimal("1.5000")
FACTOR_ADJUSTMENT_CAP = Decimal("0.5000")
CURRENCY_ADJUSTMENT_CAP = Decimal("1.0000")
UNCERTAINTY_DISCOUNT_CAP = Decimal("1.5000")


class PlanningReturnSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_class_cma: SourceChip
    industry_growth: SourceChip
    valuation: SourceChip | None = None
    factor: SourceChip | None = None
    currency: SourceChip | None = None
    uncertainty: SourceChip
    annual_cost: SourceChip


class EtfPlanningReturnInput(BaseModel):
    """Approved planning assumptions. Historical ETF returns are not inputs."""

    model_config = ConfigDict(extra="forbid")

    etf_code: str = Field(min_length=1)
    as_of: date
    horizon_years: int = Field(ge=1, le=40)
    asset_class_cma_percent: Decimal = Field(
        ge=Decimal("-20"),
        le=Decimal("30"),
        allow_inf_nan=False,
    )
    industry_excess_earnings_growth_percent: Decimal = Field(
        ge=Decimal("-20"),
        le=Decimal("20"),
        allow_inf_nan=False,
    )
    industry_growth_confidence: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("1"),
        allow_inf_nan=False,
    )
    industry_growth_persistence: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("1"),
        allow_inf_nan=False,
    )
    current_valuation_multiple: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    normal_valuation_multiple: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    factor_adjustment_percent: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("-5"),
        le=Decimal("5"),
        allow_inf_nan=False,
    )
    currency_adjustment_percent: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("-5"),
        le=Decimal("5"),
        allow_inf_nan=False,
    )
    uncertainty_discount_percent: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("5"),
        allow_inf_nan=False,
    )
    annual_cost_drag_percent: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("10"),
        allow_inf_nan=False,
    )
    sources: PlanningReturnSources

    @model_validator(mode="after")
    def require_component_evidence(self) -> "EtfPlanningReturnInput":
        has_current = self.current_valuation_multiple is not None
        has_normal = self.normal_valuation_multiple is not None
        if has_current != has_normal:
            raise ValueError(
                "current_valuation_multiple and normal_valuation_multiple "
                "must be provided together"
            )
        if has_current and self.sources.valuation is None:
            raise ValueError("valuation source is required when multiples are used")
        if self.factor_adjustment_percent != 0 and self.sources.factor is None:
            raise ValueError("factor source is required for a non-zero adjustment")
        if self.currency_adjustment_percent != 0 and self.sources.currency is None:
            raise ValueError("currency source is required for a non-zero adjustment")
        return self


class PlanningReturnComponent(BaseModel):
    code: str
    operation: str
    raw_percent: Decimal
    applied_percent: Decimal
    absolute_cap_percent: Decimal | None
    source: SourceChip | None


class EtfPlanningReturnEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    policy_version: str
    usage_label: str
    evaluated_input: EtfPlanningReturnInput
    components: list[PlanningReturnComponent]
    gross_planning_return_percent: Decimal
    net_planning_return_percent: Decimal
    is_forecast: bool
    historical_performance_used: bool
    risk_adjustment_included: bool
    warnings: list[str]


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _cap(value: Decimal, absolute_limit: Decimal) -> Decimal:
    return max(min(value, absolute_limit), -absolute_limit)


def _component(
    *,
    code: str,
    operation: str,
    raw: Decimal,
    applied: Decimal,
    cap: Decimal | None,
    source: SourceChip | None,
) -> PlanningReturnComponent:
    return PlanningReturnComponent(
        code=code,
        operation=operation,
        raw_percent=_percent(raw),
        applied_percent=_percent(applied),
        absolute_cap_percent=_percent(cap) if cap is not None else None,
        source=source,
    )


def calculate_etf_planning_return(
    assumption: EtfPlanningReturnInput,
) -> EtfPlanningReturnEvaluation:
    """Calculate the approved CMA-minus-verified-cost planning assumption.

    The historical, valuation, factor, currency, and uncertainty fields remain in
    the input contract for diagnostic compatibility.  They are deliberately not
    applied to the central value unless a separately versioned evidence gate is
    approved for production.
    """

    cma = assumption.asset_class_cma_percent
    industry_raw = (
        assumption.industry_excess_earnings_growth_percent
        * assumption.industry_growth_confidence
        * assumption.industry_growth_persistence
    )
    industry = _cap(industry_raw, INDUSTRY_ADJUSTMENT_CAP)

    valuation_raw = Decimal("0")
    valuation_source = None
    if (
        assumption.current_valuation_multiple is not None
        and assumption.normal_valuation_multiple is not None
    ):
        valuation_raw = (
            (
                assumption.normal_valuation_multiple
                / assumption.current_valuation_multiple
            ).ln()
            / Decimal(assumption.horizon_years)
            * Decimal("100")
        )
        valuation_source = assumption.sources.valuation
    valuation = _cap(valuation_raw, VALUATION_ADJUSTMENT_CAP)

    factor = _cap(
        assumption.factor_adjustment_percent,
        FACTOR_ADJUSTMENT_CAP,
    )
    currency = _cap(
        assumption.currency_adjustment_percent,
        CURRENCY_ADJUSTMENT_CAP,
    )
    uncertainty = min(
        assumption.uncertainty_discount_percent,
        UNCERTAINTY_DISCOUNT_CAP,
    )
    cost = assumption.annual_cost_drag_percent

    components = [
        _component(
            code="asset_class_cma",
            operation="add",
            raw=cma,
            applied=cma,
            cap=None,
            source=assumption.sources.asset_class_cma,
        ),
        _component(
            code="industry_excess_growth",
            operation="diagnostic_not_applied",
            raw=industry_raw,
            applied=Decimal("0"),
            cap=INDUSTRY_ADJUSTMENT_CAP,
            source=assumption.sources.industry_growth,
        ),
        _component(
            code="valuation_normalization",
            operation="diagnostic_not_applied",
            raw=valuation_raw,
            applied=Decimal("0"),
            cap=VALUATION_ADJUSTMENT_CAP,
            source=valuation_source,
        ),
        _component(
            code="factor",
            operation="diagnostic_not_applied",
            raw=assumption.factor_adjustment_percent,
            applied=Decimal("0"),
            cap=FACTOR_ADJUSTMENT_CAP,
            source=assumption.sources.factor,
        ),
        _component(
            code="currency",
            operation="diagnostic_not_applied",
            raw=assumption.currency_adjustment_percent,
            applied=Decimal("0"),
            cap=CURRENCY_ADJUSTMENT_CAP,
            source=assumption.sources.currency,
        ),
        _component(
            code="model_uncertainty",
            operation="diagnostic_not_applied",
            raw=assumption.uncertainty_discount_percent,
            applied=Decimal("0"),
            cap=UNCERTAINTY_DISCOUNT_CAP,
            source=assumption.sources.uncertainty,
        ),
        _component(
            code="annual_cost_drag",
            operation="subtract",
            raw=cost,
            applied=cost,
            cap=None,
            source=assumption.sources.annual_cost,
        ),
    ]

    gross = cma
    net = gross - cost
    warnings = [
        "standardized_planning_assumption_not_return_forecast",
        "historical_etf_returns_not_used_as_forward_return",
        "risk_is_reported_separately_from_planning_return",
        "central_value_is_cma_minus_verified_annual_cost_only",
    ]
    if any(
        value != 0
        for value in (
            industry,
            valuation,
            factor,
            currency,
            uncertainty,
        )
    ):
        warnings.append("unvalidated_overlay_inputs_retained_for_diagnostic_only")
    if assumption.current_valuation_multiple is None:
        warnings.append("valuation_adjustment_omitted_missing_verified_multiples")

    return EtfPlanningReturnEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        policy_version=POLICY_VERSION,
        usage_label="standardized_long_term_planning_assumption",
        evaluated_input=assumption,
        components=components,
        gross_planning_return_percent=_percent(gross),
        net_planning_return_percent=_percent(net),
        is_forecast=False,
        historical_performance_used=False,
        risk_adjustment_included=False,
        warnings=warnings,
    )
