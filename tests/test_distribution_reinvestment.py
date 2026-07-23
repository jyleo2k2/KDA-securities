from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.engine.distribution_reinvestment import (
    DistributionEventInput,
    DistributionHoldingInput,
    DistributionReinvestmentInput,
    DistributionStatus,
    calculate_distribution_reinvestment,
)


def _input() -> DistributionReinvestmentInput:
    return DistributionReinvestmentInput(
        as_of=date(2026, 7, 1),
        rebalance_on=date(2026, 7, 31),
        holdings=[
            DistributionHoldingInput(
                isu_code="069500",
                quantity=Decimal("10"),
                reinvestment_price_krw=Decimal("30"),
            )
        ],
        events=[
            DistributionEventInput(
                event_id="confirmed-1",
                isu_code="069500",
                payment_date=date(2026, 7, 2),
                cash_per_share_krw=Decimal("10"),
                status=DistributionStatus.CONFIRMED_CASH_FLOW,
            ),
            DistributionEventInput(
                event_id="confirmed-2",
                isu_code="069500",
                payment_date=date(2026, 7, 10),
                cash_per_share_krw=Decimal("10"),
                status=DistributionStatus.CONFIRMED_CASH_FLOW,
            ),
            DistributionEventInput(
                event_id="scheduled-1",
                isu_code="069500",
                payment_date=date(2026, 8, 1),
                cash_per_share_krw=Decimal("20"),
                status=DistributionStatus.REFERENCE_ONLY,
            ),
        ],
    )


def test_reinvests_confirmed_cash_in_payment_date_order() -> None:
    evaluation = calculate_distribution_reinvestment(_input())

    assert evaluation.confirmed_cash_krw == Decimal("230")
    assert evaluation.reference_only_cash_krw == Decimal("340")
    assert evaluation.available_for_rebalance_krw == Decimal("230")
    assert evaluation.reinvested_quantity == Decimal("7")
    assert evaluation.remaining_cash_krw == Decimal("20")
    assert evaluation.lines[0].quantity_after_reinvestment == Decimal("13")
    assert evaluation.lines[1].quantity_after_reinvestment == Decimal("17")
    assert evaluation.lines[2].quantity_after_reinvestment == Decimal("17")
    assert evaluation.lines[2].gross_cash_krw == Decimal("340")
    assert evaluation.lines[2].reinvested_quantity == Decimal("0")
    assert evaluation.lines[2].limitation is not None


def test_excludes_paid_cash_outside_rebalance_window() -> None:
    input_data = _input().model_copy(update={"rebalance_on": date(2026, 7, 5)})

    evaluation = calculate_distribution_reinvestment(input_data)

    assert evaluation.confirmed_cash_krw == Decimal("230")
    assert evaluation.available_for_rebalance_krw == Decimal("100")
    assert evaluation.reinvested_quantity == Decimal("3")
    assert evaluation.lines[1].reinvested_quantity == Decimal("0")
    assert evaluation.lines[1].quantity_after_reinvestment == Decimal("13")


def test_rejects_event_for_unknown_holding() -> None:
    input_data = _input().model_copy(
        update={
            "events": [
                DistributionEventInput(
                    event_id="unknown",
                    isu_code="123456",
                    payment_date=date(2026, 7, 2),
                    cash_per_share_krw=Decimal("10"),
                    status=DistributionStatus.CONFIRMED_CASH_FLOW,
                )
            ]
        }
    )

    with pytest.raises(ValidationError, match="must match a holding"):
        DistributionReinvestmentInput.model_validate(input_data.model_dump())
