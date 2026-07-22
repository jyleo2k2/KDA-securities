from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine import (
    EtfPlanningReturnInput,
    PlanningReturnSources,
    calculate_etf_planning_return,
)
from backend.app.engine.models import SourceChip
from backend.app.main import app, etf_planning_return

AS_OF = date(2026, 7, 15)


def _source(label: str) -> SourceChip:
    return SourceChip(
        label=label,
        reference=f"https://example.com/{label}",
        as_of=AS_OF,
    )


def _sources(
    *,
    valuation: bool = True,
    factor: bool = True,
    currency: bool = False,
) -> PlanningReturnSources:
    return PlanningReturnSources(
        asset_class_cma=_source("cma"),
        industry_growth=_source("industry"),
        valuation=_source("valuation") if valuation else None,
        factor=_source("factor") if factor else None,
        currency=_source("currency") if currency else None,
        uncertainty=_source("uncertainty"),
        annual_cost=_source("cost"),
    )


def _assumption(**overrides) -> EtfPlanningReturnInput:
    values = {
        "etf_code": "TEST123",
        "as_of": AS_OF,
        "horizon_years": 10,
        "asset_class_cma_percent": Decimal("6.0"),
        "industry_excess_earnings_growth_percent": Decimal("3.0"),
        "industry_growth_confidence": Decimal("0.5"),
        "industry_growth_persistence": Decimal("0.5"),
        "current_valuation_multiple": Decimal("25"),
        "normal_valuation_multiple": Decimal("20"),
        "factor_adjustment_percent": Decimal("0.2"),
        "currency_adjustment_percent": Decimal("0"),
        "uncertainty_discount_percent": Decimal("0.5"),
        "annual_cost_drag_percent": Decimal("0.3"),
        "sources": _sources(),
    }
    values.update(overrides)
    return EtfPlanningReturnInput(**values)


def test_planning_return_uses_cma_minus_verified_cost_as_central_value() -> None:
    result = calculate_etf_planning_return(_assumption())
    components = {item.code: item for item in result.components}

    assert components["industry_excess_growth"].raw_percent == Decimal("0.7500")
    assert components["industry_excess_growth"].applied_percent == Decimal("0.0000")
    assert components["valuation_normalization"].raw_percent == Decimal(
        "-2.2314"
    )
    assert components["valuation_normalization"].applied_percent == Decimal("0.0000")
    assert components["factor"].applied_percent == Decimal("0.0000")
    assert components["model_uncertainty"].applied_percent == Decimal("0.0000")
    assert result.gross_planning_return_percent == Decimal("6.0000")
    assert result.net_planning_return_percent == Decimal("5.7000")
    assert "central_value_is_cma_minus_verified_annual_cost_only" in result.warnings
    assert "unvalidated_overlay_inputs_retained_for_diagnostic_only" in result.warnings
    assert result.is_forecast is False
    assert result.historical_performance_used is False
    assert result.risk_adjustment_included is False


def test_diagnostic_overlays_are_bounded_but_never_change_cma_minus_cost() -> None:
    result = calculate_etf_planning_return(
        _assumption(
            industry_excess_earnings_growth_percent=Decimal("10"),
            industry_growth_confidence=Decimal("1"),
            industry_growth_persistence=Decimal("1"),
            current_valuation_multiple=Decimal("5"),
            normal_valuation_multiple=Decimal("50"),
            factor_adjustment_percent=Decimal("2"),
            currency_adjustment_percent=Decimal("2"),
            uncertainty_discount_percent=Decimal("3"),
            annual_cost_drag_percent=Decimal("2"),
            sources=_sources(currency=True),
        )
    )
    components = {item.code: item for item in result.components}

    assert components["industry_excess_growth"].applied_percent == Decimal("0.0000")
    assert components["valuation_normalization"].applied_percent == Decimal("0.0000")
    assert components["factor"].applied_percent == Decimal("0.0000")
    assert components["currency"].applied_percent == Decimal("0.0000")
    assert components["model_uncertainty"].applied_percent == Decimal("0.0000")
    assert components["annual_cost_drag"].applied_percent == Decimal("2.0000")
    assert result.gross_planning_return_percent == Decimal("6.0000")
    assert result.net_planning_return_percent == Decimal("4.0000")


def test_missing_valuation_is_explicit_and_does_not_infer_from_price_history() -> None:
    result = calculate_etf_planning_return(
        _assumption(
            current_valuation_multiple=None,
            normal_valuation_multiple=None,
            sources=_sources(valuation=False),
        )
    )

    assert result.components[2].applied_percent == Decimal("0.0000")
    assert "valuation_adjustment_omitted_missing_verified_multiples" in (
        result.warnings
    )


def test_nonzero_adjustment_requires_its_own_source_chip() -> None:
    with pytest.raises(ValidationError, match="factor source is required"):
        _assumption(sources=_sources(factor=False))


def test_historical_return_cannot_be_smuggled_into_planning_input() -> None:
    payload = _assumption().model_dump()
    payload["trailing_return_12m_percent"] = Decimal("40")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EtfPlanningReturnInput.model_validate(payload)


def test_api_exposes_same_deterministic_rule_engine() -> None:
    assumption = _assumption()

    assert "/engine/etf-planning-return" in {route.path for route in app.routes}
    assert etf_planning_return(assumption) == calculate_etf_planning_return(
        assumption
    )
