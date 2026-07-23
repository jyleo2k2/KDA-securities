"""교육용 ETF 분배금 현금흐름·재투자 계산.

확정된 현금분배만 재투자 수량 계산에 사용할 수 있다. 예정 KIS 일정은
리밸런싱 점검용 참고 금액으로만 분리하며 주문·자동매매를 만들지 않는다.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DistributionStatus(StrEnum):
    CONFIRMED_CASH_FLOW = "confirmed_cash_flow"
    REFERENCE_ONLY = "reference_only"


class DistributionHoldingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isu_code: str = Field(pattern=r"^[0-9A-Z]{6}$")
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    reinvestment_price_krw: Decimal = Field(gt=0, allow_inf_nan=False)


class DistributionEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    isu_code: str = Field(pattern=r"^[0-9A-Z]{6}$")
    payment_date: date
    cash_per_share_krw: Decimal = Field(gt=0, allow_inf_nan=False)
    status: DistributionStatus


class DistributionReinvestmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: date
    rebalance_on: date
    holdings: list[DistributionHoldingInput] = Field(min_length=1)
    events: list[DistributionEventInput] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_holdings_and_matching_events(
        self,
    ) -> DistributionReinvestmentInput:
        holding_codes = [holding.isu_code for holding in self.holdings]
        if len(holding_codes) != len(set(holding_codes)):
            raise ValueError("holdings must not contain duplicate isu_code")
        if any(event.isu_code not in holding_codes for event in self.events):
            raise ValueError("every distribution event must match a holding")
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("events must not contain duplicate event_id")
        return self


class DistributionReinvestmentLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    isu_code: str
    payment_date: date
    status: DistributionStatus
    gross_cash_krw: Decimal
    available_for_rebalance_krw: Decimal
    reinvested_quantity: Decimal
    remaining_cash_krw: Decimal
    quantity_after_reinvestment: Decimal
    limitation: str | None = None


class DistributionReinvestmentEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str = "distribution_reinvestment_guide"
    engine_version: str = "2026-07-23.1"
    evaluated_input: DistributionReinvestmentInput
    confirmed_cash_krw: Decimal
    reference_only_cash_krw: Decimal
    available_for_rebalance_krw: Decimal
    reinvested_quantity: Decimal
    remaining_cash_krw: Decimal
    lines: list[DistributionReinvestmentLine]
    limitations: list[str]


def calculate_distribution_reinvestment(
    input_data: DistributionReinvestmentInput,
) -> DistributionReinvestmentEvaluation:
    """Calculate only confirmed distribution cash into whole ETF units."""

    holdings = {holding.isu_code: holding for holding in input_data.holdings}
    quantities = {holding.isu_code: holding.quantity for holding in input_data.holdings}
    lines: list[DistributionReinvestmentLine] = []
    confirmed_cash = Decimal("0")
    reference_only_cash = Decimal("0")
    available_for_rebalance = Decimal("0")
    reinvested_quantity = Decimal("0")
    remaining_cash = Decimal("0")

    for event in sorted(
        input_data.events,
        key=lambda item: (item.payment_date, item.event_id),
    ):
        holding = holdings[event.isu_code]
        gross_cash = quantities[event.isu_code] * event.cash_per_share_krw
        if event.status is DistributionStatus.REFERENCE_ONLY:
            reference_only_cash += gross_cash
            lines.append(
                DistributionReinvestmentLine(
                    event_id=event.event_id,
                    isu_code=event.isu_code,
                    payment_date=event.payment_date,
                    status=event.status,
                    gross_cash_krw=gross_cash,
                    available_for_rebalance_krw=Decimal("0"),
                    reinvested_quantity=Decimal("0"),
                    remaining_cash_krw=Decimal("0"),
                    quantity_after_reinvestment=quantities[event.isu_code],
                    limitation=(
                        "예정 일정은 확정 분배금·재투자 계산에 포함하지 않습니다."
                    ),
                )
            )
            continue

        confirmed_cash += gross_cash
        is_available = input_data.as_of <= event.payment_date <= input_data.rebalance_on
        available = gross_cash if is_available else Decimal("0")
        if not is_available:
            lines.append(
                DistributionReinvestmentLine(
                    event_id=event.event_id,
                    isu_code=event.isu_code,
                    payment_date=event.payment_date,
                    status=event.status,
                    gross_cash_krw=gross_cash,
                    available_for_rebalance_krw=Decimal("0"),
                    reinvested_quantity=Decimal("0"),
                    remaining_cash_krw=Decimal("0"),
                    quantity_after_reinvestment=quantities[event.isu_code],
                    limitation=(
                        "Payment date is outside the requested rebalance window."
                    ),
                )
            )
            continue
        whole_units = (gross_cash / holding.reinvestment_price_krw).to_integral_value(
            rounding=ROUND_FLOOR
        )
        invested_cash = whole_units * holding.reinvestment_price_krw
        leftover = gross_cash - invested_cash
        quantities[event.isu_code] += whole_units
        available_for_rebalance += available
        reinvested_quantity += whole_units
        remaining_cash += leftover
        lines.append(
            DistributionReinvestmentLine(
                event_id=event.event_id,
                isu_code=event.isu_code,
                payment_date=event.payment_date,
                status=event.status,
                gross_cash_krw=gross_cash,
                available_for_rebalance_krw=available,
                reinvested_quantity=whole_units,
                remaining_cash_krw=leftover,
                quantity_after_reinvestment=quantities[event.isu_code],
            )
        )

    return DistributionReinvestmentEvaluation(
        evaluated_input=input_data,
        confirmed_cash_krw=confirmed_cash,
        reference_only_cash_krw=reference_only_cash,
        available_for_rebalance_krw=available_for_rebalance,
        reinvested_quantity=reinvested_quantity,
        remaining_cash_krw=remaining_cash,
        lines=lines,
        limitations=[
            (
                "사용자 입력 수량·재투자 단가와 공식 이벤트 금액을 사용한 "
                "계산입니다."
            ),
            "예정 일정은 참고용이며 확정 분배금, 미래 수익 또는 주문 지시가 아닙니다.",
            "자동 재투자·주문은 수행하지 않습니다.",
        ],
    )
