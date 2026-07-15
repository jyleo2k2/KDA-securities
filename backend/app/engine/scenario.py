from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .models import (
    AssetAllocation,
    HoldingInput,
    PortfolioInput,
    ScenarioEvaluation,
    ScenarioPortfolioInput,
    SourceChip,
)
from .portfolio import evaluate_risk_cap

ENGINE_NAME = "mock_scenario_diagnostic"
ENGINE_VERSION = "2026-07-14.1"
MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")
MOCK_SOURCE = SourceChip(
    label="연금 코파일럿 목계좌 시나리오",
    reference="data/mock/chatbot_scenarios.json",
    as_of=date(2026, 7, 14),
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def evaluate_mock_scenario(portfolio: ScenarioPortfolioInput) -> ScenarioEvaluation:
    """Aggregate a versioned mock scenario without inferring product eligibility."""

    account_evaluations = []
    asset_amounts: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    asset_accounts: dict[str, set[str]] = defaultdict(set)

    for account in portfolio.accounts:
        engine_input = PortfolioInput(
            account_type=account.account_type,
            holdings=[
                HoldingInput(
                    holding_id=holding.holding_id,
                    amount_krw=holding.amount_krw,
                    risk_treatment=holding.risk_treatment,
                    statutory_exception=holding.statutory_exception,
                )
                for holding in account.holdings
            ],
        )
        account_evaluations.append(evaluate_risk_cap(engine_input))
        for holding in account.holdings:
            asset_amounts[holding.asset_class_code] += holding.amount_krw
            asset_accounts[holding.asset_class_code].add(account.account_id)

    total = _money(sum(asset_amounts.values(), start=Decimal("0")))
    allocations = [
        AssetAllocation(
            asset_class_code=asset_class,
            amount_krw=_money(amount),
            allocation_percent=_percent(amount / total * Decimal("100")),
            account_count=len(asset_accounts[asset_class]),
        )
        for asset_class, amount in sorted(
            asset_amounts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    rounding_delta = Decimal("100.00") - sum(
        (item.allocation_percent for item in allocations), start=Decimal("0")
    )
    if allocations and rounding_delta:
        allocations[0] = allocations[0].model_copy(
            update={
                "allocation_percent": (
                    allocations[0].allocation_percent + rounding_delta
                )
            }
        )
    duplicated = sorted(
        asset_class
        for asset_class, accounts in asset_accounts.items()
        if len(accounts) > 1
    )

    return ScenarioEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        scenario_code=portfolio.scenario_code,
        data_boundary="mock",
        total_amount_krw=total,
        account_evaluations=account_evaluations,
        asset_allocations=allocations,
        duplicated_asset_classes=duplicated,
        source=MOCK_SOURCE,
    )
