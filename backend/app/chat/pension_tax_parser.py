"""Deterministic slot extraction for pension-tax chatbot questions.

This module only converts a narrow set of user-provided facts into validated
Tool inputs.  It never calculates tax and never infers an absent monetary
amount.  The rule engine remains the only component allowed to calculate.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from ..engine import (
    IncomeBasis,
    IrpDeferredIncomeStatus,
    NonPensionWithdrawalInput,
    PensionAccountTaxInput,
    PensionTaxCreditInput,
    PensionTaxScenarioInput,
    WithdrawalReason,
)

_PENSION = r"연금\s*저축(?:\s*계좌)?"
_IRP = r"(?:IRP|개인형\s*퇴직\s*연금(?:\s*계좌)?)"


def _amount_pattern(prefix: str) -> str:
    return (
        rf"(?P<{prefix}_number>\d[\d,]*(?:\.\d+)?)\s*"
        rf"(?P<{prefix}_unit>억|천만|만|천)?\s*원"
    )


def _amount(match: re.Match[str], prefix: str) -> Decimal:
    number = Decimal(match.group(f"{prefix}_number").replace(",", ""))
    multiplier = {
        None: Decimal("1"),
        "천": Decimal("1000"),
        "만": Decimal("10000"),
        "천만": Decimal("10000000"),
        "억": Decimal("100000000"),
    }[match.group(f"{prefix}_unit")]
    return number * multiplier


def _account_balance(message: str, account: str, prefix: str) -> Decimal | None:
    match = re.search(
        rf"{account}\s*잔액(?:이|은|는)?\s*{_amount_pattern(prefix)}",
        message,
        re.I,
    )
    return _amount(match, prefix) if match is not None else None


def _account_contribution(
    message: str, account: str, prefix: str
) -> Decimal | None:
    before = re.search(
        rf"{account}.{{0,16}}?(?:올해|당해\s*연도)?\s*납입(?:액|금액)?"
        rf"(?:이|은|는|으로)?\s*{_amount_pattern(prefix)}",
        message,
        re.I,
    )
    if before is not None:
        return _amount(before, prefix)
    after = re.search(
        rf"{account}\s*(?:에|에는)?\s*{_amount_pattern(prefix)}"
        rf".{{0,18}}?납입",
        message,
        re.I,
    )
    return _amount(after, prefix) if after is not None else None


def _paired_contributions(message: str) -> tuple[Decimal | None, Decimal | None]:
    match = re.search(
        rf"{_PENSION}\s*(?:에|에는)?\s*{_amount_pattern('ps_pair')}"
        rf".{{0,30}}?{_IRP}\s*(?:에|에는)?\s*{_amount_pattern('irp_pair')}"
        rf".{{0,24}}?납입",
        message,
        re.I,
    )
    if match is None:
        return None, None
    return _amount(match, "ps_pair"), _amount(match, "irp_pair")


def _income(message: str) -> tuple[IncomeBasis, Decimal | None]:
    gross = re.search(
        rf"총\s*급여(?:액)?(?:이|은|는|가)?\s*{_amount_pattern('gross')}",
        message,
        re.I,
    )
    if gross is not None:
        return IncomeBasis.GROSS_SALARY, _amount(gross, "gross")
    comprehensive = re.search(
        rf"종합\s*소득(?:\s*금액)?(?:이|은|는|가)?\s*"
        rf"{_amount_pattern('comprehensive')}",
        message,
        re.I,
    )
    if comprehensive is not None:
        return (
            IncomeBasis.COMPREHENSIVE_INCOME,
            _amount(comprehensive, "comprehensive"),
        )
    return IncomeBasis.UNKNOWN, None


def _withdrawal_reason(message: str) -> WithdrawalReason:
    if re.search(
        r"의료비|질병|요양|천재지변|사망|해외\s*이주|파산|개인\s*회생|"
        r"부득이한?\s*(?:사유|인출)",
        message,
    ):
        return WithdrawalReason.UNAVOIDABLE
    if re.search(r"인출\s*사유.{0,12}(?:몰라|모르|불명)", message):
        return WithdrawalReason.UNKNOWN
    return WithdrawalReason.GENERAL


def _deferred_income(
    message: str,
) -> tuple[IrpDeferredIncomeStatus, Decimal | None]:
    if re.search(
        r"(?:퇴직금\s*이전분|이연\s*퇴직\s*소득).{0,15}(?:몰라|모르|불명)",
        message,
    ):
        return IrpDeferredIncomeStatus.UNKNOWN, None
    if re.search(
        r"(?:퇴직금\s*이전분|이연\s*퇴직\s*소득).{0,15}(?:없어|없음|없다)",
        message,
    ):
        return IrpDeferredIncomeStatus.NONE, None
    known = re.search(
        rf"(?:퇴직금\s*이전분|이연\s*퇴직\s*소득)(?:이|은|는)?\s*"
        rf"{_amount_pattern('deferred')}",
        message,
    )
    if known is not None:
        return IrpDeferredIncomeStatus.KNOWN, _amount(known, "deferred")
    return IrpDeferredIncomeStatus.UNKNOWN, None


@dataclass(frozen=True)
class ParsedPensionTaxInputs:
    tax_credit: PensionTaxCreditInput | None
    withdrawal: NonPensionWithdrawalInput | None
    missing_tax_credit: tuple[str, ...] = ()
    missing_withdrawal: tuple[str, ...] = ()


def parse_pension_tax_inputs(message: str) -> ParsedPensionTaxInputs:
    """Extract only explicit facts needed by each pension-tax Tool."""

    pension_contribution, irp_contribution = _paired_contributions(message)
    if pension_contribution is None:
        pension_contribution = _account_contribution(
            message, _PENSION, "ps_contribution"
        )
    if irp_contribution is None:
        irp_contribution = _account_contribution(
            message, _IRP, "irp_contribution"
        )
    income_basis, income_amount = _income(message)
    missing_credit: list[str] = []
    if pension_contribution is None:
        missing_credit.append("연금저축 당해연도 납입액")
    if irp_contribution is None:
        missing_credit.append("IRP 당해연도 납입액")
    tax_credit = (
        PensionTaxCreditInput(
            income_basis=income_basis,
            income_amount_krw=income_amount,
            pension_savings_contribution_krw=pension_contribution,
            irp_contribution_krw=irp_contribution,
        )
        if not missing_credit
        else None
    )

    reason = _withdrawal_reason(message)
    deferred_status, deferred_amount = _deferred_income(message)
    if reason != WithdrawalReason.GENERAL:
        withdrawal = NonPensionWithdrawalInput(
            withdrawal_reason=reason,
            irp_deferred_income_status=deferred_status,
            irp_deferred_retirement_income_krw=deferred_amount,
        )
        return ParsedPensionTaxInputs(
            tax_credit=tax_credit,
            withdrawal=withdrawal,
            missing_tax_credit=tuple(missing_credit),
        )

    pension_balance = _account_balance(message, _PENSION, "ps_balance")
    irp_balance = _account_balance(message, _IRP, "irp_balance")
    no_current_contribution = re.search(
        r"(?:올해|당해\s*연도)\s*납입액(?:이|은|는)?\s*(?:없|0\s*원)",
        message,
    ) is not None
    pension_withdrawal_contribution = (
        Decimal("0")
        if no_current_contribution
        else _account_contribution(message, _PENSION, "ps_withdrawal_contribution")
    )
    irp_withdrawal_contribution = (
        Decimal("0")
        if no_current_contribution
        else _account_contribution(message, _IRP, "irp_withdrawal_contribution")
    )
    missing_withdrawal: list[str] = []
    if pension_balance is None:
        missing_withdrawal.append("연금저축 잔액")
    if irp_balance is None:
        missing_withdrawal.append("IRP 잔액")
    if pension_withdrawal_contribution is None:
        missing_withdrawal.append("연금저축 당해연도 납입액")
    if irp_withdrawal_contribution is None:
        missing_withdrawal.append("IRP 당해연도 납입액")
    withdrawal = (
        NonPensionWithdrawalInput(
            pension_savings=PensionAccountTaxInput(
                balance_krw=pension_balance,
                current_year_contribution_krw=pension_withdrawal_contribution,
            ),
            irp=PensionAccountTaxInput(
                balance_krw=irp_balance,
                current_year_contribution_krw=irp_withdrawal_contribution,
            ),
            withdrawal_reason=reason,
            irp_deferred_income_status=deferred_status,
            irp_deferred_retirement_income_krw=deferred_amount,
        )
        if not missing_withdrawal
        else None
    )
    return ParsedPensionTaxInputs(
        tax_credit=tax_credit,
        withdrawal=withdrawal,
        missing_tax_credit=tuple(missing_credit),
        missing_withdrawal=tuple(missing_withdrawal),
    )


def resolve_pension_tax_inputs(
    message: str,
    structured: PensionTaxScenarioInput | None,
    *,
    prefer_structured: bool = False,
) -> ParsedPensionTaxInputs:
    """Prefer explicit form/API input, otherwise parse narrow natural slots."""

    parsed = parse_pension_tax_inputs(message)
    if structured is None:
        return parsed
    if prefer_structured:
        return ParsedPensionTaxInputs(
            tax_credit=structured.to_tax_credit_input(),
            withdrawal=structured.to_withdrawal_input(),
        )
    return ParsedPensionTaxInputs(
        # A complete value explicitly written in the latest question wins over
        # potentially stale sidebar values.  The form fills only missing Tools.
        tax_credit=parsed.tax_credit or structured.to_tax_credit_input(),
        withdrawal=parsed.withdrawal or structured.to_withdrawal_input(),
        missing_tax_credit=(
            () if parsed.tax_credit is not None else parsed.missing_tax_credit
        ),
        missing_withdrawal=(
            () if parsed.withdrawal is not None else parsed.missing_withdrawal
        ),
    )
