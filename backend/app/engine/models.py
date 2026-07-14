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
