"""Per-account diagnostics (아키텍처.md §2 module 3).

Risk-cap judgement is delegated to ``evaluate_risk_cap`` so DC/IRP limits and
pension-savings eligibility stay in one place; this module never re-implements
account rules. Thresholds below are provisional.
TODO: 확인 필요 — 현금성 방치·자산군 편중 임계값은 팀 승인 후 확정한다.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    AccountType,
    AssetClass,
    AssetClassWeight,
    HoldingInput,
    PortfolioInput,
    RiskCapEvaluation,
    RuleStatus,
    SourceChip,
)
from .portfolio import MONEY_QUANTUM, PERCENT_QUANTUM, evaluate_risk_cap

ENGINE_NAME = "account_diagnostics"
ENGINE_VERSION = "2026-07-15.1"
CASH_IDLE_THRESHOLD_PERCENT = Decimal("80.00")
CONCENTRATION_THRESHOLD_PERCENT = Decimal("50.00")
CASH_LIKE_CLASSES = frozenset({AssetClass.CASH, AssetClass.DEPOSIT})
DIAGNOSTICS_SOURCE = SourceChip(
    label="아키텍처 §2 모듈 3 (잠정 임계값)",
    reference="docs/30_스펙/아키텍처.md#2-규칙-엔진-6모듈--계산판단의-단일-소스",
    as_of=date(2026, 7, 15),
)

CHECK_CASH_IDLE = "CASH_IDLE"
CHECK_RISK_CAP = "GENERAL_RISK_ASSET_CAP"
CHECK_CONCENTRATION = "SINGLE_CLASS_CONCENTRATION"


class AccountHolding(HoldingInput):
    instrument_name: str = Field(min_length=1)
    asset_class: AssetClass


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    account_type: AccountType
    holdings: list[AccountHolding] = Field(min_length=1)

    @model_validator(mode="after")
    def apply_portfolio_rules(self) -> "AccountInput":
        # Reuses PortfolioInput validation (account-rule separation, total > 0).
        self.to_portfolio_input()
        return self

    def to_portfolio_input(self) -> PortfolioInput:
        return PortfolioInput(
            account_type=self.account_type,
            holdings=[
                HoldingInput(
                    holding_id=holding.holding_id,
                    amount_krw=holding.amount_krw,
                    risk_treatment=holding.risk_treatment,
                    statutory_exception=holding.statutory_exception,
                )
                for holding in self.holdings
            ],
        )


class DiagnosticFinding(BaseModel):
    check_code: str
    status: RuleStatus
    measured_percent: Decimal
    threshold_percent: Decimal | None
    subject_asset_class: AssetClass | None = None
    message: str
    source: SourceChip


class AccountDiagnosticsEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    account_id: str
    account_type: AccountType
    total_amount_krw: Decimal
    asset_class_weights: list[AssetClassWeight]
    findings: list[DiagnosticFinding]
    risk_cap: RiskCapEvaluation


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _asset_class_weights(
    account: AccountInput, total: Decimal
) -> list[AssetClassWeight]:
    amounts: dict[AssetClass, Decimal] = {}
    for holding in account.holdings:
        amounts[holding.asset_class] = (
            amounts.get(holding.asset_class, Decimal("0")) + holding.amount_krw
        )
    return [
        AssetClassWeight(
            asset_class=asset_class,
            amount_krw=_money(amount),
            weight_percent=_percent(amount / total * Decimal("100")),
        )
        for asset_class, amount in sorted(amounts.items())
    ]


def evaluate_account_diagnostics(
    account: AccountInput,
) -> AccountDiagnosticsEvaluation:
    """Run the per-account checks without an LLM and with rule delegation."""

    total = _money(
        sum((holding.amount_krw for holding in account.holdings), Decimal("0"))
    )
    weights = _asset_class_weights(account, total)
    risk_cap = evaluate_risk_cap(account.to_portfolio_input())
    findings: list[DiagnosticFinding] = []

    cash_like = sum(
        (
            weight.amount_krw
            for weight in weights
            if weight.asset_class in CASH_LIKE_CLASSES
        ),
        Decimal("0"),
    )
    cash_like_percent = _percent(cash_like / total * Decimal("100"))
    cash_idle = cash_like_percent >= CASH_IDLE_THRESHOLD_PERCENT
    findings.append(
        DiagnosticFinding(
            check_code=CHECK_CASH_IDLE,
            status=RuleStatus.FAIL if cash_idle else RuleStatus.PASS,
            measured_percent=cash_like_percent,
            threshold_percent=CASH_IDLE_THRESHOLD_PERCENT,
            message=(
                f"현금성 자산 비중 {cash_like_percent}%"
                f" (점검 기준 {CASH_IDLE_THRESHOLD_PERCENT}% 이상 여부)"
            ),
            source=DIAGNOSTICS_SOURCE,
        )
    )

    findings.append(
        DiagnosticFinding(
            check_code=CHECK_RISK_CAP,
            status=risk_cap.status,
            measured_percent=risk_cap.general_risky_ratio_percent,
            threshold_percent=risk_cap.limit_percent,
            message=(
                "연금저축에는 위험자산 총량 한도가 적용되지 않음"
                if risk_cap.status == RuleStatus.NOT_APPLICABLE
                else (
                    f"일반 위험자산 비중 {risk_cap.general_risky_ratio_percent}%"
                    f" (한도 {risk_cap.limit_percent}%)"
                )
            ),
            source=DIAGNOSTICS_SOURCE,
        )
    )

    non_cash_weights = [
        weight
        for weight in weights
        if weight.asset_class not in CASH_LIKE_CLASSES
    ]
    if non_cash_weights:
        top = max(non_cash_weights, key=lambda weight: weight.weight_percent)
        concentrated = top.weight_percent >= CONCENTRATION_THRESHOLD_PERCENT
        findings.append(
            DiagnosticFinding(
                check_code=CHECK_CONCENTRATION,
                status=RuleStatus.FAIL if concentrated else RuleStatus.PASS,
                measured_percent=top.weight_percent,
                threshold_percent=CONCENTRATION_THRESHOLD_PERCENT,
                subject_asset_class=top.asset_class,
                message=(
                    f"단일 자산군({top.asset_class}) 비중 {top.weight_percent}%"
                    f" (점검 기준 {CONCENTRATION_THRESHOLD_PERCENT}% 이상 여부)"
                ),
                source=DIAGNOSTICS_SOURCE,
            )
        )
    else:
        findings.append(
            DiagnosticFinding(
                check_code=CHECK_CONCENTRATION,
                status=RuleStatus.NOT_APPLICABLE,
                measured_percent=Decimal("0.00"),
                threshold_percent=CONCENTRATION_THRESHOLD_PERCENT,
                message="현금성 외 자산군이 없어 편중 점검 대상 아님",
                source=DIAGNOSTICS_SOURCE,
            )
        )

    return AccountDiagnosticsEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        account_id=account.account_id,
        account_type=account.account_type,
        total_amount_krw=total,
        asset_class_weights=weights,
        findings=findings,
        risk_cap=risk_cap,
    )
