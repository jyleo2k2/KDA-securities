import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.engine import (
    EtfPlanningReturnInput,
    HistoricalEtfMetrics,
    KrxEtfEvidenceProduct,
    PlanningReturnSources,
    assess_etf_with_krx_evidence,
    calculate_relative_etf_risk_percentiles,
)
from backend.app.engine.models import SourceChip
from backend.app.main import app, etf_planning_assessment
from backend.app.market_evidence_repository import KrxMarketEvidenceRepository

AS_OF = date(2026, 7, 14)


def _source(label: str = "KRX ETF 일별매매정보") -> SourceChip:
    return SourceChip(
        label=label,
        reference="https://example.com/source",
        as_of=AS_OF,
    )


def _metrics(
    volatility: str,
    drawdown: str,
    liquidity: str,
    *,
    size: str | None = "1000",
    nav: str | None = "0.5",
    tracking: str | None = "2",
) -> HistoricalEtfMetrics:
    return HistoricalEtfMetrics(
        engine_name="historical_etf_evidence",
        engine_version="test",
        history_start=date(2025, 7, 1),
        history_end=AS_OF,
        observation_count=253,
        trailing_return_3m_percent=Decimal("1"),
        trailing_return_6m_percent=Decimal("2"),
        trailing_return_12m_percent=Decimal("3"),
        annualized_volatility_percent=Decimal(volatility),
        max_drawdown_percent=Decimal(drawdown),
        median_daily_trading_value_krw=Decimal(liquidity),
        median_net_assets_krw=Decimal(size) if size is not None else None,
        median_abs_premium_discount_percent=(
            Decimal(nav) if nav is not None else None
        ),
        tracking_error_proxy_percent=(
            Decimal(tracking) if tracking is not None else None
        ),
        source=_source(),
        warnings=[],
    )


def _product(code: str, metrics: HistoricalEtfMetrics) -> KrxEtfEvidenceProduct:
    return KrxEtfEvidenceProduct(
        isu_code=code,
        isu_name=f"ETF {code}",
        benchmark_name="broad index",
        active_on_report_date=True,
        usable_on_report_date=True,
        blocked_name_pattern=False,
        eligibility_status="verification_required",
        historical_metrics=metrics,
    )


def _assumption(code: str = "A") -> EtfPlanningReturnInput:
    return EtfPlanningReturnInput(
        etf_code=code,
        as_of=AS_OF,
        horizon_years=10,
        asset_class_cma_percent=Decimal("6"),
        industry_excess_earnings_growth_percent=Decimal("0"),
        industry_growth_confidence=Decimal("0"),
        industry_growth_persistence=Decimal("0"),
        current_valuation_multiple=None,
        normal_valuation_multiple=None,
        uncertainty_discount_percent=Decimal("0.5"),
        annual_cost_drag_percent=Decimal("0.3"),
        sources=PlanningReturnSources(
            asset_class_cma=_source("CMA"),
            industry_growth=_source("industry"),
            uncertainty=_source("uncertainty"),
            annual_cost=_source("cost"),
        ),
    )


def test_relative_risk_uses_current_universe_without_composite_ranking() -> None:
    low = _metrics("10", "5", "1000", size="3000", nav="0.1", tracking="1")
    middle = _metrics(
        "20", "10", "100", size="2000", nav="0.5", tracking="2"
    )
    high = _metrics("30", "20", "10", size="1000", nav="1.0", tracking="3")

    result = calculate_relative_etf_risk_percentiles(middle, [low, middle, high])

    assert result.universe_count == 3
    assert result.volatility_risk_percentile == Decimal("66.6667")
    assert result.drawdown_risk_percentile == Decimal("66.6667")
    assert result.low_liquidity_risk_percentile == Decimal("66.6667")
    assert result.small_size_risk_percentile == Decimal("66.6667")
    assert result.nav_deviation_risk_percentile == Decimal("66.6667")
    assert result.tracking_error_risk_percentile == Decimal("66.6667")


def test_assessment_keeps_krx_returns_out_of_planning_return() -> None:
    target = _product("A", _metrics("20", "10", "100"))
    result = assess_etf_with_krx_evidence(
        _assumption(),
        product=target,
        universe=[target.historical_metrics],
    )

    assert result.planning_return.net_planning_return_percent == Decimal("5.7000")
    assert result.planning_return.historical_performance_used is False
    assert "trailing_return_12m_percent" in result.excluded_from_planning_return
    assert result.relative_risk.volatility_risk_percentile == Decimal("100.0000")
    assert (
        result.portfolio_candidate_status
        == "account_eligibility_verification_required"
    )


def test_repository_loads_only_contract_valid_current_products(tmp_path) -> None:
    products = [
        _product("A", _metrics("10", "5", "100")),
        _product("B", _metrics("20", "10", "200")),
    ]
    payload = {
        "report_type": "current_listed_historical_market_evidence",
        "as_of": AS_OF.isoformat(),
        "product_count": 2,
        "current_listed_universe_count": 4,
        "excluded_insufficient_observations_count": 1,
        "excluded_not_currently_listed_count": 1,
        "minimum_candidate_observations": 253,
        "products": [item.model_dump(mode="json") for item in products],
    }
    path = tmp_path / "etf_market_evidence_2026-07-14.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    repository = KrxMarketEvidenceRepository.from_path(path)

    assert repository.report.product_count == 2
    assert repository.get("B").isu_name == "ETF B"
    with pytest.raises(KeyError, match="not current and observation-sufficient"):
        repository.get("C")


def test_api_combines_planning_assumption_with_repository_evidence() -> None:
    product = _product("A", _metrics("20", "10", "100"))

    class Repository:
        universe = [product.historical_metrics]

        def get(self, isu_code: str) -> KrxEtfEvidenceProduct:
            if isu_code != "A":
                raise KeyError(isu_code)
            return product

    result = etf_planning_assessment(_assumption(), Repository())

    assert "/engine/etf-planning-assessment" in {
        route.path for route in app.routes
    }
    assert result.krx_product.isu_code == "A"
    assert result.relative_risk.universe_count == 1


def test_api_rejects_etf_excluded_from_current_krx_report(caplog) -> None:
    class EmptyRepository:
        universe = []

        def get(self, isu_code: str) -> KrxEtfEvidenceProduct:
            raise KeyError(isu_code)

    with pytest.raises(HTTPException) as exc_info:
        etf_planning_assessment(_assumption("MISSING"), EmptyRepository())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "RESOURCE_NOT_FOUND",
        "message": "Requested ETF is not in the KRX evidence universe",
    }
    assert "krx_evidence_etf_not_found etf_code=MISSING" in caplog.messages
