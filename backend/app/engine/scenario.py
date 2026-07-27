"""Mock-scenario diagnostic built on the shared engines (아키텍처.md §10 통합).

자산군 집계·백분율 계산은 ``aggregate_accounts``(모듈 4)에, 계좌별 위험자산
판정은 ``evaluate_risk_cap``(모듈 2)에 위임한다. 이 모듈은 시나리오 입력을
공용 엔진 입력으로 변환하고 결과를 시나리오 계약으로 재배열만 한다.
"""

from datetime import date
from decimal import Decimal

from .aggregation import AggregationInput, aggregate_accounts
from .diagnostics import AccountHolding, AccountInput
from .models import (
    AssetAllocation,
    AssetClass,
    ScenarioEvaluation,
    ScenarioPortfolioInput,
    SourceChip,
)
from .portfolio import evaluate_risk_cap

ENGINE_NAME = "mock_scenario_diagnostic"
ENGINE_VERSION = "2026-07-15.1"
MOCK_SOURCE = SourceChip(
    label="연금 코파일럿 계좌 시나리오",
    reference="data/mock/chatbot_scenarios.json",
    as_of=date(2026, 7, 14),
)


def _to_account_input(portfolio: ScenarioPortfolioInput) -> list[AccountInput]:
    """Convert scenario accounts to the shared engine input.

    시나리오 자산군 코드는 seed ``asset_classes.code``(=AssetClass enum)와
    일치해야 하며, 아닌 값은 여기서 즉시 실패한다.
    """
    return [
        AccountInput(
            account_id=account.account_id,
            account_type=account.account_type,
            holdings=[
                AccountHolding(
                    holding_id=holding.holding_id,
                    amount_krw=holding.amount_krw,
                    risk_treatment=holding.risk_treatment,
                    statutory_exception=holding.statutory_exception,
                    instrument_name=holding.instrument_name,
                    asset_class=AssetClass(holding.asset_class_code),
                )
                for holding in account.holdings
            ],
        )
        for account in portfolio.accounts
    ]


def evaluate_mock_scenario(portfolio: ScenarioPortfolioInput) -> ScenarioEvaluation:
    """Aggregate a versioned mock scenario without inferring product eligibility."""

    accounts = _to_account_input(portfolio)
    aggregation = aggregate_accounts(AggregationInput(accounts=accounts))
    account_evaluations = [
        evaluate_risk_cap(account.to_portfolio_input()) for account in accounts
    ]

    duplicate_counts = {
        overlap.asset_class: len(overlap.account_ids)
        for overlap in aggregation.overlaps
    }
    allocations = sorted(
        (
            AssetAllocation(
                asset_class_code=weight.asset_class.value,
                amount_krw=weight.amount_krw,
                allocation_percent=weight.weight_percent,
                account_count=duplicate_counts.get(weight.asset_class, 1),
            )
            for weight in aggregation.asset_class_totals
        ),
        key=lambda item: (-item.amount_krw, item.asset_class_code),
    )
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
        overlap.asset_class.value for overlap in aggregation.overlaps
    )

    return ScenarioEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        scenario_code=portfolio.scenario_code,
        data_boundary="mock",
        total_amount_krw=aggregation.total_amount_krw,
        account_evaluations=account_evaluations,
        asset_allocations=allocations,
        duplicated_asset_classes=duplicated,
        source=MOCK_SOURCE,
    )
