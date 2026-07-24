from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest

import backend.app.engine.educational_portfolio as portfolio_module
from backend.app.engine.educational_portfolio import (
    CandidateQuality,
    CurrentHolding,
    EducationalEtfCandidate,
    EducationalPortfolioInput,
    RiskProfile,
    StressLossPolicyStatus,
    _build_asset_class_allocation,
    _candidate_counts,
    _display_asset_class,
    _percentile,
    build_educational_portfolio,
    calculate_rebalancing_guidance,
    calculate_return_correlation,
    calculate_target_allocation,
    rebalancing_cadence,
    select_educational_candidates,
)
from backend.app.engine.models import AccountType, AssetClass


def _request(
    *,
    account: AccountType = AccountType.DC,
    age: int = 25,
    profile: RiskProfile = RiskProfile.AGGRESSIVE,
    loss: str = "40",
    holdings: list[CurrentHolding] | None = None,
    contribution: str = "0",
) -> EducationalPortfolioInput:
    return EducationalPortfolioInput(
        account_type=account,
        age=age,
        risk_profile=profile,
        loss_tolerance_percent=Decimal(loss),
        current_holdings=holdings or [],
        new_contribution_krw=Decimal(contribution),
    )


def _product(
    code: str,
    *,
    asset_class: str,
    strategy: str,
    allocation_bucket: str = "general_risky_70_cap",
    fee: str = "0.2",
    liquidity: int = 1_000_000_000,
    region: str = "south_korea",
) -> dict[str, object]:
    return {
        "isu_code": code,
        "isu_name": f"ETF {code}",
        "classification": {
            "asset_class": asset_class,
            "strategy": strategy,
            "region": region,
            "classification_confidence": "high",
        },
        "account_eligibility": {
            "eligible": True,
            "allocation_bucket": allocation_bucket,
        },
        "cost": {"kis_total_expense_ratio_percent": fee},
        "implementation_metrics": {
            "median_daily_trading_value_krw": liquidity,
            "median_net_assets_krw": 100_000_000_000,
            "median_abs_premium_discount_percent": "0.1",
            "kis_current_tracking_error_percent": "0.2",
            "tracking_error_proxy_percent": "0.3",
        },
        "observation_count": 756,
        "returns": {"1y": {"distribution_reinvested_total_return_percent": "999"}},
    }


def _history(multiplier: str = "1") -> dict[date, Decimal]:
    start = date(2026, 1, 1)
    factor = Decimal(multiplier)
    return {
        start + timedelta(days=index): Decimal("100")
        + Decimal(index) * factor
        + Decimal(index % 3)
        for index in range(90)
    }


def test_dc_aggressive_target_is_capped_but_pension_savings_is_not() -> None:
    _, dc = calculate_target_allocation(_request(account=AccountType.DC))
    _, pension = calculate_target_allocation(
        _request(account=AccountType.PENSION_SAVINGS)
    )

    assert dc["final_risk"] <= Decimal("70")
    assert dc["account_cap_binding"] is True
    assert pension["final_risk"] > dc["final_risk"]
    assert pension["account_cap"] is None


def test_loss_tolerance_reduces_risk_and_stress_proxy() -> None:
    _, normal = calculate_target_allocation(_request(loss="40"))
    _, constrained = calculate_target_allocation(_request(loss="8"))

    assert constrained["loss_tolerance_binding"] is True
    assert constrained["final_risk"] < normal["final_risk"]
    assert constrained["stress_loss"] <= Decimal("8.0001")


def test_correlation_requires_enough_overlap_and_detects_similarity() -> None:
    correlation = calculate_return_correlation(_history(), _history())

    assert correlation is not None
    assert correlation > Decimal("0.99")


def test_percentile_preserves_favorable_ties_in_both_directions() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("2"), Decimal("3")]

    assert _percentile(Decimal("2"), values, higher_is_better=True) == Decimal("75")
    assert _percentile(Decimal("2"), values, higher_is_better=False) == Decimal("75")


def test_candidate_selection_calculates_each_daily_return_series_once(
    monkeypatch,
) -> None:
    products = [
        _product(
            "CORE01",
            asset_class="equity",
            strategy="broad_market",
            region="south_korea",
        ),
        _product(
            "CORE02",
            asset_class="equity",
            strategy="broad_market",
            region="united_states",
        ),
        _product(
            "CORE03",
            asset_class="equity",
            strategy="broad_market",
            region="japan",
        ),
        _product("TACT01", asset_class="equity", strategy="sector_or_theme"),
        _product("TACT02", asset_class="equity", strategy="covered_call"),
        _product(
            "BOND01",
            asset_class="fixed_income",
            strategy="government_bond",
            allocation_bucket="full_allocation_eligible",
        ),
        _product(
            "CASH01",
            asset_class="cash_equivalent",
            strategy="money_market",
            allocation_bucket="full_allocation_eligible",
        ),
    ]
    histories = {
        product["isu_code"]: _history(str(index + 1))
        for index, product in enumerate(products)
    }
    calls: Counter[int] = Counter()
    correlation_calls: Counter[tuple[int, int]] = Counter()
    original = portfolio_module._daily_returns
    original_correlation = (
        portfolio_module._calculate_return_correlation_from_returns
    )
    original_score = portfolio_module._score_candidates
    score_calls: Counter[tuple[str, ...]] = Counter()

    def counted(history):
        calls[id(history)] += 1
        return original(history)

    def counted_correlation(first, second):
        correlation_calls[tuple(sorted((id(first), id(second))))] += 1
        return original_correlation(first, second)

    def counted_score(pool):
        score_calls[tuple(product["isu_code"] for product in pool)] += 1
        return original_score(pool)

    monkeypatch.setattr(portfolio_module, "_daily_returns", counted)
    monkeypatch.setattr(
        portfolio_module,
        "_calculate_return_correlation_from_returns",
        counted_correlation,
    )
    monkeypatch.setattr(portfolio_module, "_score_candidates", counted_score)

    selection_args = {
        "products": products,
        "histories": histories,
        "sleeves": {
            "core_equity": Decimal("55"),
            "tactical": Decimal("15"),
            "real_assets": Decimal("0"),
            "fixed_income": Decimal("25"),
            "cash": Decimal("5"),
        },
        "request": _request(),
    }
    score_cache = {}
    candidates = select_educational_candidates(
        **selection_args,
        score_cache=score_cache,
    )

    assert calls
    assert max(calls.values()) == 1
    assert correlation_calls
    assert max(correlation_calls.values()) == 1
    assert len({candidate.isu_code for candidate in candidates}) == len(candidates)

    select_educational_candidates(
        **selection_args,
        score_cache=score_cache,
    )

    assert score_calls
    assert max(score_calls.values()) == 1


def test_large_tactical_sleeve_is_split_across_two_candidates() -> None:
    counts = _candidate_counts(
        {
            "core_equity": Decimal("60"),
            "tactical": Decimal("15"),
            "real_assets": Decimal("5"),
            "fixed_income": Decimal("17"),
            "cash": Decimal("3"),
        },
        7,
    )

    assert counts["core_equity"] == 2
    assert counts["tactical"] == 2


def test_portfolio_uses_full_allocation_products_for_defensive_sleeves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = [
        _product("CORE01", asset_class="equity", strategy="broad_market"),
        _product(
            "CORE02",
            asset_class="equity",
            strategy="broad_market",
            region="united_states",
        ),
        _product(
            "BOND01",
            asset_class="fixed_income",
            strategy="government_bond",
            allocation_bucket="full_allocation_eligible",
        ),
        _product(
            "BOND02",
            asset_class="fixed_income",
            strategy="high_yield_bond",
            allocation_bucket="general_risky_70_cap",
            liquidity=9_000_000_000,
        ),
        _product(
            "CASH01",
            asset_class="cash_equivalent",
            strategy="money_market",
            allocation_bucket="full_allocation_eligible",
        ),
    ]
    histories = {product["isu_code"]: _history() for product in products}
    request = _request(
        age=52,
        profile=RiskProfile.STABLE_SEEKING,
        loss="15",
        holdings=[CurrentHolding(isu_code="CORE01", amount_krw=1_000_000)],
        contribution="300000",
    )

    result = build_educational_portfolio(
        request,
        products=products,
        histories=histories,
        source_as_of=date(2026, 7, 16),
        history_sources={
            product["isu_code"]: "kis_adjusted_close" for product in products
        },
    )

    codes = {candidate.isu_code for candidate in result.candidates}
    assert "BOND01" in codes
    assert "BOND02" not in codes
    assert result.rebalancing.contribution_first is True
    assert result.rebalancing.sell_instruction_produced is False
    assert result.rebalancing.cadence.review_interval_months == 6
    assert result.rebalancing.cadence.drift_threshold_percent_points == Decimal("5")
    assert all(
        "historical_return_not_used_for_ranking" in candidate.reasons
        for candidate in result.candidates
    )
    assert all(
        candidate.price_history_source == "kis_adjusted_close"
        for candidate in result.candidates
    )
    assert result.portfolio_risk.status == "complete"
    assert result.portfolio_risk.is_return_forecast is False
    assert result.portfolio_risk.stress_loss_limit_percent == Decimal("15")
    assert (
        result.portfolio_risk.stress_loss_policy_status
        == StressLossPolicyStatus.WITHIN_USER_LIMIT
    )
    assert result.planning_return.is_forecast is False
    assert result.planning_return.historical_performance_used is False
    assert result.planning_horizon_years == 3
    assert result.current_holdings_planning_return is not None
    assert result.current_holdings_planning_return.components[0].isu_code == "CORE01"
    assert result.current_holdings_planning_return.components[0].target_percent == 100

    def unavailable_current_holdings_planning(**_: object) -> None:
        raise ValueError("verified ETF cost is unavailable: CORE01")

    monkeypatch.setattr(
        portfolio_module,
        "calculate_current_holdings_planning_return",
        unavailable_current_holdings_planning,
    )
    unavailable = build_educational_portfolio(
        request,
        products=products,
        histories=histories,
        source_as_of=date(2026, 7, 16),
    )

    assert unavailable.current_holdings_planning_return is None
    assert unavailable.rebalancing.status == "calculated"
    assert any(
        warning.startswith("current_holdings_planning_return_unavailable:")
        for warning in unavailable.warnings
    )


@pytest.mark.parametrize(
    ("profile", "months", "threshold"),
    [
        (RiskProfile.STABLE, 12, Decimal("5")),
        (RiskProfile.STABLE_SEEKING, 6, Decimal("5")),
        (RiskProfile.RISK_NEUTRAL, 3, Decimal("5")),
        (RiskProfile.ACTIVE, 2, Decimal("3")),
        (RiskProfile.AGGRESSIVE, 1, Decimal("3")),
    ],
)
def test_rebalancing_cadence_follows_risk_profile(
    profile: RiskProfile, months: int, threshold: Decimal
) -> None:
    cadence = rebalancing_cadence(profile)

    assert cadence.review_interval_months == months
    assert cadence.drift_threshold_percent_points == threshold
    assert cadence.rationale


def test_rebalancing_uses_snapshot_cash_and_bond_in_actual_weights() -> None:
    request = _request(
        holdings=[
            CurrentHolding(
                isu_code="CORE01",
                amount_krw=Decimal("6000000"),
                asset_class=AssetClass.DOMESTIC_EQUITY,
            ),
            CurrentHolding(
                isu_code="snapshot:cash-1",
                amount_krw=Decimal("2000000"),
                asset_class=AssetClass.CASH,
            ),
            CurrentHolding(
                isu_code="snapshot:bond-1",
                amount_krw=Decimal("2000000"),
                asset_class=AssetClass.BOND,
            ),
        ]
    )
    products = {
        "CORE01": _product(
            "CORE01", asset_class="equity", strategy="broad_market"
        )
    }

    guidance = calculate_rebalancing_guidance(
        request=request,
        products=products,
        sleeves={
            "core_equity": Decimal("60"),
            "real_assets": Decimal("0"),
            "tactical": Decimal("0"),
            "fixed_income": Decimal("20"),
            "cash": Decimal("20"),
        },
    )

    current = {item.sleeve: item.current_percent for item in guidance.sleeves}
    drift = {
        item.sleeve: item.drift_before_percent_points
        for item in guidance.sleeves
    }
    assert guidance.current_total_krw == Decimal("10000000")
    assert guidance.unclassified_holding_amount_krw == Decimal("0")
    assert current == {
        "core_equity": Decimal("60"),
        "real_assets": Decimal("0"),
        "tactical": Decimal("0"),
        "fixed_income": Decimal("20"),
        "cash": Decimal("20"),
    }
    assert drift["core_equity"] == Decimal("0")


def test_asset_class_allocation_includes_all_display_buckets_and_corrects_rounding(
) -> None:
    quality = CandidateQuality(
        total_score=Decimal("100"),
        fee_efficiency=Decimal("100"),
        liquidity=Decimal("100"),
        size=Decimal("100"),
        nav_quality=Decimal("100"),
        tracking_quality=Decimal("100"),
        history_depth=Decimal("100"),
    )
    candidates = [
        EducationalEtfCandidate(
            isu_code="DOMESTIC",
            isu_name="국내 ETF",
            sleeve="core_equity",
            target_percent=Decimal("50"),
            quality=quality,
            asset_class=AssetClass.DOMESTIC_EQUITY,
            region="south_korea",
            strategy="broad_market",
            max_correlation_with_selected=None,
            price_history_source="test",
            account_eligibility={},
            reasons=[],
        ),
        EducationalEtfCandidate(
            isu_code="GLOBAL",
            isu_name="해외 ETF",
            sleeve="core_equity",
            target_percent=Decimal("49.9999"),
            quality=quality,
            asset_class=AssetClass.GLOBAL_EQUITY,
            region="united_states",
            strategy="broad_market",
            max_correlation_with_selected=None,
            price_history_source="test",
            account_eligibility={},
            reasons=[],
        ),
    ]

    allocation, warnings = _build_asset_class_allocation(candidates)

    assert [item.asset_class for item in allocation] == [
        AssetClass.DOMESTIC_EQUITY,
        AssetClass.GLOBAL_EQUITY,
        AssetClass.BOND,
        AssetClass.ALTERNATIVE,
        AssetClass.CASH,
    ]
    assert sum((item.target_percent for item in allocation), Decimal("0")) == 100
    assert warnings == []


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        (
            {"asset_class": "equity", "region": "south_korea"},
            AssetClass.DOMESTIC_EQUITY,
        ),
        (
            {"asset_class": "equity", "region": "united_states"},
            AssetClass.GLOBAL_EQUITY,
        ),
        ({"asset_class": "fixed_income"}, AssetClass.BOND),
        ({"asset_class": "real_estate"}, AssetClass.ALTERNATIVE),
        ({"asset_class": "cash_equivalent"}, AssetClass.CASH),
        ({"asset_class": "equity"}, None),
    ],
)
def test_candidate_asset_class_uses_existing_product_classification(
    classification: dict[str, str], expected: AssetClass | None
) -> None:
    assert _display_asset_class(classification) == expected


def test_retirement_start_age_changes_horizon_and_glidepath() -> None:
    early_request = _request(age=52, profile=RiskProfile.ACTIVE, loss="40")
    later_request = early_request.model_copy(update={"retirement_start_age": 60})

    _, early = calculate_target_allocation(early_request)
    _, later = calculate_target_allocation(later_request)

    assert later["raw_risk"] > early["raw_risk"]
    assert later_request.retirement_start_age - later_request.age == 8
