"""Rule-based pension tax-credit and non-pension withdrawal estimates.

The Markdown knowledge document is explanatory evidence, never executable
configuration.  All calculations live in this pure module so the chatbot and
REST API share one versioned, testable source of truth.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import AccountType, SourceChip
from .portfolio import MONEY_QUANTUM

ENGINE_NAME = "pension_tax_guidance"
ENGINE_VERSION = "2026-07-15.1"
RULE_VERSION = "PENSION_TAX_2026_07_15_V1"
SUPPORTED_TAX_YEAR = 2026

PENSION_SAVINGS_CREDIT_LIMIT_KRW = Decimal("6000000")
COMBINED_CREDIT_LIMIT_KRW = Decimal("9000000")
GROSS_SALARY_THRESHOLD_KRW = Decimal("55000000")
COMPREHENSIVE_INCOME_THRESHOLD_KRW = Decimal("45000000")
LOW_INCOME_TAX_CREDIT_RATE_PERCENT = Decimal("15")
HIGH_INCOME_TAX_CREDIT_RATE_PERCENT = Decimal("12")
LOW_INCOME_DISPLAY_RATE_PERCENT = Decimal("16.5")
HIGH_INCOME_DISPLAY_RATE_PERCENT = Decimal("13.2")
NON_PENSION_OTHER_INCOME_RATE_PERCENT = Decimal("16.5")

DOCUMENT_SOURCE = SourceChip(
    label="연금계좌 세액공제 및 과세방법",
    reference="project://docs/연금계좌세액공제 및 과세방법.md",
    as_of=date(2026, 7, 15),
)
TAX_CREDIT_SOURCE = SourceChip(
    label="소득세법 제59조의3 연금계좌세액공제",
    reference="https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1032884269",
    as_of=date(2026, 7, 15),
)
WITHDRAWAL_ORDER_SOURCE = SourceChip(
    label="소득세법 시행령 제40조의3 연금계좌 인출순서",
    reference=(
        "https://www.law.go.kr/lsLawLinkInfo.do?"
        "chrClsCd=010202&lsJoLnkSeq=1001061005"
    ),
    as_of=date(2026, 7, 15),
)
WITHDRAWAL_TAX_SOURCE = SourceChip(
    label="국세청 연금계좌 원천징수세율",
    reference=(
        "https://www.nts.go.kr/nts/cm/cntnts/"
        "cntntsView.do?cntntsId=7888&mi=6608"
    ),
    as_of=date(2026, 7, 15),
)


class IncomeBasis(StrEnum):
    GROSS_SALARY = "gross_salary"
    COMPREHENSIVE_INCOME = "comprehensive_income"
    UNKNOWN = "unknown"


class WithdrawalReason(StrEnum):
    GENERAL = "general"
    UNAVOIDABLE = "unavoidable"
    UNKNOWN = "unknown"


class IrpDeferredIncomeStatus(StrEnum):
    NONE = "none"
    KNOWN = "known"
    UNKNOWN = "unknown"


class WithdrawalCalculationMode(StrEnum):
    SOURCE_AWARE = "source_aware_estimate"
    SIMPLIFIED_MAX = "simplified_max_other_income_estimate"


class WithdrawalCalculationStatus(StrEnum):
    ESTIMATED = "estimated"
    REQUIRES_REVIEW = "requires_review"


class PensionAccountTaxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balance_krw: Decimal = Field(
        ge=0, max_digits=20, decimal_places=2, allow_inf_nan=False
    )
    current_year_contribution_krw: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    # This excludes current-year contributions, which have their own statutory
    # withdrawal-order treatment.
    prior_year_non_deducted_principal_krw: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )


class PensionTaxCreditInput(BaseModel):
    """Only the fields required by the tax-credit calculation Tool."""

    model_config = ConfigDict(extra="forbid")

    tax_year: int = Field(default=SUPPORTED_TAX_YEAR, ge=2026, le=2026)
    income_basis: IncomeBasis = IncomeBasis.UNKNOWN
    income_amount_krw: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    pension_savings_contribution_krw: Decimal = Field(
        ge=0, max_digits=20, decimal_places=2, allow_inf_nan=False
    )
    irp_contribution_krw: Decimal = Field(
        ge=0, max_digits=20, decimal_places=2, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def require_consistent_income(self) -> "PensionTaxCreditInput":
        if self.income_basis == IncomeBasis.UNKNOWN:
            if self.income_amount_krw is not None:
                raise ValueError(
                    "income_amount_krw requires a non-unknown income_basis"
                )
        elif self.income_amount_krw is None:
            raise ValueError("income_amount_krw is required for the income_basis")
        return self


class NonPensionWithdrawalInput(BaseModel):
    """Fields required by the non-pension withdrawal Tool.

    Account balances are required only for a general withdrawal estimate.
    An unavoidable or unknown reason can be routed to review without asking for
    amounts that must not be used to manufacture a tax estimate.
    """

    model_config = ConfigDict(extra="forbid")

    tax_year: int = Field(default=SUPPORTED_TAX_YEAR, ge=2026, le=2026)
    pension_savings: PensionAccountTaxInput | None = None
    irp: PensionAccountTaxInput | None = None
    withdrawal_reason: WithdrawalReason = WithdrawalReason.GENERAL
    irp_deferred_income_status: IrpDeferredIncomeStatus = (
        IrpDeferredIncomeStatus.UNKNOWN
    )
    irp_deferred_retirement_income_krw: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def require_only_reason_relevant_facts(self) -> "NonPensionWithdrawalInput":
        if self.withdrawal_reason == WithdrawalReason.GENERAL and (
            self.pension_savings is None or self.irp is None
        ):
            raise ValueError(
                "general withdrawal requires both pension account inputs"
            )

        deferred = self.irp_deferred_retirement_income_krw
        if self.irp_deferred_income_status == IrpDeferredIncomeStatus.KNOWN:
            if self.irp is None or deferred is None:
                raise ValueError(
                    "known IRP deferred income requires an IRP account and amount"
                )
            if deferred > self.irp.balance_krw:
                raise ValueError("IRP deferred income cannot exceed IRP balance")
        elif deferred is not None and deferred != 0:
            raise ValueError(
                "IRP deferred income amount is allowed only when status is known"
            )
        return self


class PensionTaxScenarioInput(BaseModel):
    """Combined UI/backwards-compatible input; Tools use the split schemas."""

    model_config = ConfigDict(extra="forbid")

    tax_year: int = Field(default=SUPPORTED_TAX_YEAR, ge=2026, le=2026)
    income_basis: IncomeBasis = IncomeBasis.UNKNOWN
    income_amount_krw: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    pension_savings: PensionAccountTaxInput
    irp: PensionAccountTaxInput
    withdrawal_reason: WithdrawalReason = WithdrawalReason.GENERAL
    irp_deferred_income_status: IrpDeferredIncomeStatus = (
        IrpDeferredIncomeStatus.UNKNOWN
    )
    irp_deferred_retirement_income_krw: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def require_consistent_optional_facts(self) -> "PensionTaxScenarioInput":
        try:
            self.to_tax_credit_input()
            self.to_withdrawal_input()
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self

    def to_tax_credit_input(self) -> PensionTaxCreditInput:
        return PensionTaxCreditInput(
            tax_year=self.tax_year,
            income_basis=self.income_basis,
            income_amount_krw=self.income_amount_krw,
            pension_savings_contribution_krw=(
                self.pension_savings.current_year_contribution_krw
            ),
            irp_contribution_krw=self.irp.current_year_contribution_krw,
        )

    def to_withdrawal_input(self) -> NonPensionWithdrawalInput:
        return NonPensionWithdrawalInput(
            tax_year=self.tax_year,
            pension_savings=self.pension_savings,
            irp=self.irp,
            withdrawal_reason=self.withdrawal_reason,
            irp_deferred_income_status=self.irp_deferred_income_status,
            irp_deferred_retirement_income_krw=(
                self.irp_deferred_retirement_income_krw
            ),
        )


class TaxCreditRateScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    income_tax_rate_percent: Decimal
    local_inclusive_display_rate_percent: Decimal
    estimated_tax_credit_krw: Decimal


class PensionTaxCreditEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    rule_version: str
    tax_year: int
    pension_savings_contribution_krw: Decimal
    irp_contribution_krw: Decimal
    pension_savings_eligible_contribution_krw: Decimal
    irp_eligible_contribution_krw: Decimal
    total_eligible_contribution_krw: Decimal
    unused_combined_limit_krw: Decimal
    rate_determined: bool
    rate_scenarios: list[TaxCreditRateScenario]
    assumption_notice: str
    evidence: list[SourceChip]


class WithdrawalAccountBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_type: AccountType
    balance_krw: Decimal
    current_year_contribution_excluded_krw: Decimal
    prior_year_non_deducted_principal_excluded_krw: Decimal
    deferred_retirement_income_excluded_krw: Decimal
    assumed_other_income_tax_base_krw: Decimal


class NonPensionWithdrawalEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_name: str
    engine_version: str
    rule_version: str
    tax_year: int
    status: WithdrawalCalculationStatus
    calculation_mode: WithdrawalCalculationMode | None
    total_balance_krw: Decimal | None
    total_current_year_contribution_excluded_krw: Decimal
    total_prior_year_non_deducted_principal_excluded_krw: Decimal
    total_deferred_retirement_income_excluded_krw: Decimal
    assumed_other_income_tax_base_krw: Decimal | None
    other_income_rate_percent: Decimal | None
    estimated_max_other_income_withholding_krw: Decimal | None
    account_breakdowns: list[WithdrawalAccountBreakdown]
    assumptions: list[str]
    limitations: list[str]
    evidence: list[SourceChip]


class PensionTaxToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tax_credit: PensionTaxCreditEvaluation | None = None
    withdrawal: NonPensionWithdrawalEvaluation | None = None

    @model_validator(mode="after")
    def require_at_least_one_result(self) -> "PensionTaxToolResult":
        if self.tax_credit is None and self.withdrawal is None:
            raise ValueError("at least one pension tax result is required")
        return self


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _rate_scenarios(
    inputs: PensionTaxCreditInput,
) -> list[tuple[str, Decimal, Decimal]]:
    if inputs.income_basis == IncomeBasis.UNKNOWN:
        return [
            (
                "소득구간 하단 가정",
                LOW_INCOME_TAX_CREDIT_RATE_PERCENT,
                LOW_INCOME_DISPLAY_RATE_PERCENT,
            ),
            (
                "소득구간 상단 가정",
                HIGH_INCOME_TAX_CREDIT_RATE_PERCENT,
                HIGH_INCOME_DISPLAY_RATE_PERCENT,
            ),
        ]

    assert inputs.income_amount_krw is not None
    threshold = (
        GROSS_SALARY_THRESHOLD_KRW
        if inputs.income_basis == IncomeBasis.GROSS_SALARY
        else COMPREHENSIVE_INCOME_THRESHOLD_KRW
    )
    if inputs.income_amount_krw <= threshold:
        return [
            (
                "확인된 소득구간",
                LOW_INCOME_TAX_CREDIT_RATE_PERCENT,
                LOW_INCOME_DISPLAY_RATE_PERCENT,
            )
        ]
    return [
        (
            "확인된 소득구간",
            HIGH_INCOME_TAX_CREDIT_RATE_PERCENT,
            HIGH_INCOME_DISPLAY_RATE_PERCENT,
        )
    ]


def calculate_pension_tax_credit(
    inputs: PensionTaxCreditInput,
) -> PensionTaxCreditEvaluation:
    pension_eligible = min(
        inputs.pension_savings_contribution_krw,
        PENSION_SAVINGS_CREDIT_LIMIT_KRW,
    )
    remaining = COMBINED_CREDIT_LIMIT_KRW - pension_eligible
    irp_eligible = min(inputs.irp_contribution_krw, remaining)
    total_eligible = pension_eligible + irp_eligible
    scenarios = [
        TaxCreditRateScenario(
            label=label,
            income_tax_rate_percent=income_rate,
            local_inclusive_display_rate_percent=display_rate,
            estimated_tax_credit_krw=_money(
                total_eligible * display_rate / Decimal("100")
            ),
        )
        for label, income_rate, display_rate in _rate_scenarios(inputs)
    ]
    return PensionTaxCreditEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        rule_version=RULE_VERSION,
        tax_year=inputs.tax_year,
        pension_savings_contribution_krw=_money(
            inputs.pension_savings_contribution_krw
        ),
        irp_contribution_krw=_money(inputs.irp_contribution_krw),
        pension_savings_eligible_contribution_krw=_money(pension_eligible),
        irp_eligible_contribution_krw=_money(irp_eligible),
        total_eligible_contribution_krw=_money(total_eligible),
        unused_combined_limit_krw=_money(
            COMBINED_CREDIT_LIMIT_KRW - total_eligible
        ),
        rate_determined=inputs.income_basis != IncomeBasis.UNKNOWN,
        rate_scenarios=scenarios,
        assumption_notice=(
            "예상 세액공제액이며 실제 환급액은 결정세액과 개인별 과세상황에 "
            "따라 줄어들 수 있다. 같은 해 중도해지 추정과는 별도 가정이다."
        ),
        evidence=[DOCUMENT_SOURCE, TAX_CREDIT_SOURCE],
    )


def _withdrawal_breakdown(
    *,
    account_type: AccountType,
    account: PensionAccountTaxInput,
    deferred_retirement_income_krw: Decimal = Decimal("0"),
) -> tuple[WithdrawalAccountBreakdown, list[str]]:
    remaining = account.balance_krw
    current_year_excluded = min(remaining, account.current_year_contribution_krw)
    remaining -= current_year_excluded

    prior_requested = account.prior_year_non_deducted_principal_krw or Decimal("0")
    prior_excluded = min(remaining, prior_requested)
    remaining -= prior_excluded

    deferred_excluded = min(remaining, deferred_retirement_income_krw)
    remaining -= deferred_excluded

    limitations: list[str] = []
    if account.current_year_contribution_krw > account.balance_krw:
        limitations.append(
            f"{account_type.value} 당해연도 납입액이 잔액보다 커서 잔액까지만 "
            "과세제외금액으로 반영했습니다."
        )
    if prior_requested > account.balance_krw - current_year_excluded:
        limitations.append(
            f"{account_type.value} 미공제 원금은 남은 잔액까지만 반영했습니다."
        )
    if deferred_retirement_income_krw > (
        account.balance_krw - current_year_excluded - prior_excluded
    ):
        limitations.append("IRP 이연퇴직소득은 남은 잔액까지만 반영했습니다.")

    return (
        WithdrawalAccountBreakdown(
            account_type=account_type,
            balance_krw=_money(account.balance_krw),
            current_year_contribution_excluded_krw=_money(current_year_excluded),
            prior_year_non_deducted_principal_excluded_krw=_money(prior_excluded),
            deferred_retirement_income_excluded_krw=_money(deferred_excluded),
            assumed_other_income_tax_base_krw=_money(remaining),
        ),
        limitations,
    )


def estimate_non_pension_withdrawal_tax(
    inputs: NonPensionWithdrawalInput,
) -> NonPensionWithdrawalEvaluation:
    accounts = [
        account
        for account in (inputs.pension_savings, inputs.irp)
        if account is not None
    ]
    total_balance = (
        sum((account.balance_krw for account in accounts), start=Decimal("0"))
        if accounts
        else None
    )
    evidence = [DOCUMENT_SOURCE, WITHDRAWAL_ORDER_SOURCE, WITHDRAWAL_TAX_SOURCE]
    if inputs.withdrawal_reason != WithdrawalReason.GENERAL:
        reason = (
            "부득이한 인출 사유는 연금소득 과세 가능성을 별도 확인해야 합니다."
            if inputs.withdrawal_reason == WithdrawalReason.UNAVOIDABLE
            else "일반 연금외수령인지 부득이한 인출인지 먼저 확인해야 합니다."
        )
        return NonPensionWithdrawalEvaluation(
            engine_name=ENGINE_NAME,
            engine_version=ENGINE_VERSION,
            rule_version=RULE_VERSION,
            tax_year=inputs.tax_year,
            status=WithdrawalCalculationStatus.REQUIRES_REVIEW,
            calculation_mode=None,
            total_balance_krw=(
                _money(total_balance) if total_balance is not None else None
            ),
            total_current_year_contribution_excluded_krw=Decimal("0"),
            total_prior_year_non_deducted_principal_excluded_krw=Decimal("0"),
            total_deferred_retirement_income_excluded_krw=Decimal("0"),
            assumed_other_income_tax_base_krw=None,
            other_income_rate_percent=None,
            estimated_max_other_income_withholding_krw=None,
            account_breakdowns=[],
            assumptions=[],
            limitations=[
                reason,
                "금융기관 자료를 확인하고 세무전문가와 상의해 주세요.",
            ],
            evidence=evidence,
        )

    assert inputs.pension_savings is not None
    assert inputs.irp is not None
    assert total_balance is not None
    deferred = (
        inputs.irp_deferred_retirement_income_krw or Decimal("0")
        if inputs.irp_deferred_income_status == IrpDeferredIncomeStatus.KNOWN
        else Decimal("0")
    )
    pension_breakdown, pension_limits = _withdrawal_breakdown(
        account_type=AccountType.PENSION_SAVINGS,
        account=inputs.pension_savings,
    )
    irp_breakdown, irp_limits = _withdrawal_breakdown(
        account_type=AccountType.IRP,
        account=inputs.irp,
        deferred_retirement_income_krw=deferred,
    )
    breakdowns = [pension_breakdown, irp_breakdown]
    tax_base = sum(
        (item.assumed_other_income_tax_base_krw for item in breakdowns),
        start=Decimal("0"),
    )
    known_sources = (
        inputs.pension_savings.prior_year_non_deducted_principal_krw is not None
        and inputs.irp.prior_year_non_deducted_principal_krw is not None
        and inputs.irp_deferred_income_status != IrpDeferredIncomeStatus.UNKNOWN
    )
    mode = (
        WithdrawalCalculationMode.SOURCE_AWARE
        if known_sources
        else WithdrawalCalculationMode.SIMPLIFIED_MAX
    )
    assumptions: list[str] = []
    limitations = [*pension_limits, *irp_limits]
    if inputs.pension_savings.prior_year_non_deducted_principal_krw is None:
        assumptions.append("연금저축의 과거 미공제 원금을 0원으로 가정했습니다.")
    if inputs.irp.prior_year_non_deducted_principal_krw is None:
        assumptions.append("IRP의 과거 미공제 원금을 0원으로 가정했습니다.")
    if inputs.irp_deferred_income_status == IrpDeferredIncomeStatus.UNKNOWN:
        assumptions.append("IRP의 이연퇴직소득을 0원으로 가정했습니다.")
        limitations.append(
            "IRP에 퇴직금 이전분이 있으면 해당 금액은 16.5% 계산 대상이 "
            "아니므로 실제 결과가 달라집니다."
        )
    limitations.extend(
        [
            "기타소득 원천징수 간이 추정이며 확정 세액이 아닙니다.",
            "금융기관의 재원별 잔액을 확인하고 세무전문가와 상의해 주세요.",
        ]
    )

    return NonPensionWithdrawalEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        rule_version=RULE_VERSION,
        tax_year=inputs.tax_year,
        status=WithdrawalCalculationStatus.ESTIMATED,
        calculation_mode=mode,
        total_balance_krw=_money(total_balance),
        total_current_year_contribution_excluded_krw=_money(
            sum(
                (item.current_year_contribution_excluded_krw for item in breakdowns),
                start=Decimal("0"),
            )
        ),
        total_prior_year_non_deducted_principal_excluded_krw=_money(
            sum(
                (
                    item.prior_year_non_deducted_principal_excluded_krw
                    for item in breakdowns
                ),
                start=Decimal("0"),
            )
        ),
        total_deferred_retirement_income_excluded_krw=_money(
            irp_breakdown.deferred_retirement_income_excluded_krw
        ),
        assumed_other_income_tax_base_krw=_money(tax_base),
        other_income_rate_percent=NON_PENSION_OTHER_INCOME_RATE_PERCENT,
        estimated_max_other_income_withholding_krw=_money(
            tax_base * NON_PENSION_OTHER_INCOME_RATE_PERCENT / Decimal("100")
        ),
        account_breakdowns=breakdowns,
        assumptions=assumptions,
        limitations=limitations,
        evidence=evidence,
    )
