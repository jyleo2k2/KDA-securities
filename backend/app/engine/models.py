from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccountType(StrEnum):
    DC = "dc"
    IRP = "irp"
    PENSION_SAVINGS = "pension_savings"


class RiskTreatment(StrEnum):
    CAPITAL_PRESERVATION = "capital_preservation"
    GENERAL_RISKY = "general_risky"
    STATUTORY_EXCEPTION = "statutory_exception"


class StatutoryException(StrEnum):
    ELIGIBLE_TDF = "eligible_tdf"
    DEFAULT_OPTION = "default_option"


class RuleStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class HoldingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holding_id: str = Field(min_length=1)
    amount_krw: Decimal = Field(
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    risk_treatment: RiskTreatment
    statutory_exception: StatutoryException | None = None

    @model_validator(mode="after")
    def require_explicit_exception(self) -> "HoldingInput":
        is_exception = self.risk_treatment == RiskTreatment.STATUTORY_EXCEPTION
        if is_exception != (self.statutory_exception is not None):
            raise ValueError(
                "statutory_exception is required only when risk_treatment is "
                "statutory_exception"
            )
        return self


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType
    holdings: list[HoldingInput] = Field(min_length=1)

    @model_validator(mode="after")
    def keep_account_rules_separate(self) -> "PortfolioInput":
        if self.account_type == AccountType.PENSION_SAVINGS and any(
            holding.risk_treatment == RiskTreatment.STATUTORY_EXCEPTION
            for holding in self.holdings
        ):
            raise ValueError(
                "DC/IRP statutory risk-cap exceptions do not apply to pension_savings"
            )
        if sum((holding.amount_krw for holding in self.holdings), Decimal("0")) <= 0:
            raise ValueError("portfolio total amount must be greater than zero")
        return self


class SourceChip(BaseModel):
    label: str
    reference: str
    as_of: date


class RiskCapEvidence(BaseModel):
    rule_code: str
    rule_version: str
    source: SourceChip
    numerator_general_risky_krw: Decimal
    denominator_total_krw: Decimal
    statutory_exception_krw: Decimal
    limit_percent: Decimal | None


class RiskCapEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    evaluated_input: PortfolioInput
    total_amount_krw: Decimal
    capital_preservation_amount_krw: Decimal
    general_risky_amount_krw: Decimal
    statutory_exception_amount_krw: Decimal
    general_risky_ratio_percent: Decimal
    limit_percent: Decimal | None
    excess_general_risky_amount_krw: Decimal | None
    within_limit: bool | None
    status: RuleStatus
    evidence: list[RiskCapEvidence]


class ReturnSubperiod(BaseModel):
    """A valuation interval with no external cash flow inside the interval."""

    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date
    beginning_value_krw: Decimal = Field(
        gt=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )
    ending_value_before_flow_krw: Decimal = Field(
        ge=0,
        max_digits=20,
        decimal_places=2,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def require_positive_interval(self) -> "ReturnSubperiod":
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


class HistoricalReturnEvaluation(BaseModel):
    engine_name: str
    engine_version: str
    method: str
    subperiod_returns_percent: list[Decimal]
    cumulative_return_percent: Decimal
    annualized_volatility_percent: Decimal
    maximum_drawdown_percent: Decimal
    periods_per_year: int
    policy_reference: str


class RiskBudgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType
    current_value_krw: Decimal = Field(gt=0, allow_inf_nan=False)
    minimum_target_at_55_krw: Decimal = Field(gt=0, allow_inf_nan=False)
    years_to_55: int = Field(ge=0, le=55)
    safe_rate_assumption_percent: Decimal = Field(gt=-100, allow_inf_nan=False)
    risk_multiplier: Decimal = Field(ge=0, allow_inf_nan=False)
    suitability_limit_percent: Decimal = Field(ge=0, le=100, allow_inf_nan=False)


class RiskBudgetEvaluation(BaseModel):
    preservation_floor_krw: Decimal
    cushion_krw: Decimal
    account_limit_percent: Decimal
    suitability_limit_percent: Decimal
    cushion_limit_percent: Decimal
    allowed_risky_percent: Decimal
    assumption_notice: str
    policy_reference: str


class ProfitLockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=18, le=100)
    total_value_krw: Decimal = Field(gt=0, allow_inf_nan=False)
    tactical_value_krw: Decimal = Field(ge=0, allow_inf_nan=False)
    tactical_checkpoint_krw: Decimal = Field(gt=0, allow_inf_nan=False)
    tactical_target_percent: Decimal = Field(ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def keep_tactical_value_within_total(self) -> "ProfitLockInput":
        if self.tactical_value_krw > self.total_value_krw:
            raise ValueError("tactical_value_krw cannot exceed total_value_krw")
        return self


class ProfitLockEvaluation(BaseModel):
    tactical_weight_percent: Decimal
    checkpoint_return_percent: Decimal
    overweight_triggered: bool
    checkpoint_triggered: bool
    recommended_transfer_krw: Decimal
    transfer_destination: str
    policy_reference: str
