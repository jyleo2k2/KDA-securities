from datetime import date, timedelta
from decimal import Decimal

from backend.app.engine.educational_portfolio import (
    CurrentHolding,
    EducationalPortfolioInput,
    RiskProfile,
    _candidate_counts,
    build_educational_portfolio,
    calculate_return_correlation,
    calculate_target_allocation,
)
from backend.app.engine.models import AccountType


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


def test_portfolio_uses_full_allocation_products_for_defensive_sleeves() -> None:
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
    assert all(
        "historical_return_not_used_for_ranking" in candidate.reasons
        for candidate in result.candidates
    )
    assert all(
        candidate.price_history_source == "kis_adjusted_close"
        for candidate in result.candidates
    )
