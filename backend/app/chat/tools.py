"""Narrow, read-only tools exposed to the chatbot agent.

The functions are deliberately thin wrappers over pure engine functions.  They
cannot query SQL, mutate accounts, browse the web, or execute an order.
"""

from ..engine import (
    NonPensionWithdrawalEvaluation,
    NonPensionWithdrawalInput,
    PensionTaxCreditEvaluation,
    PensionTaxCreditInput,
    calculate_pension_tax_credit,
    estimate_non_pension_withdrawal_tax,
)

PENSION_TAX_CLOSING_NOTICE = (
    "자세한 내용은 금융기관을 통한 확인 및 세무전문가의 상담이 필요합니다."
)


def calculate_pension_tax_credit_tool(
    inputs: PensionTaxCreditInput,
) -> PensionTaxCreditEvaluation:
    """Calculate an educational 2026 pension tax-credit estimate.

    Use only for Korean pension-savings and IRP current-year contributions.
    This returns an estimated credit, not a guaranteed refund.  Never use it
    for filing, ordering a product, or years other than the validated schema.
    """

    return calculate_pension_tax_credit(inputs)


def estimate_non_pension_withdrawal_tax_tool(
    inputs: NonPensionWithdrawalInput,
) -> NonPensionWithdrawalEvaluation:
    """Estimate the 16.5% other-income withholding portion on withdrawal.

    The result is assumption-based and excludes known current-year
    contributions, non-deducted principal, and IRP deferred retirement income.
    It is not an exact tax assessment and always requires source limitations.
    """

    return estimate_non_pension_withdrawal_tax(inputs)


PENSION_TAX_AGENT_TOOLS = (
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)
