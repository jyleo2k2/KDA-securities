"""Narrow, read-only tools exposed to the chatbot agent.

The functions are deliberately thin wrappers over pure engine functions.  They
cannot query SQL, mutate accounts, browse the web, or execute an order.
"""

from ..engine import (
    AccountDiagnosticsEvaluation,
    AccountInput,
    AggregationEvaluation,
    AggregationInput,
    AllocationExampleEvaluation,
    AllocationExampleInput,
    NonPensionWithdrawalEvaluation,
    NonPensionWithdrawalInput,
    PensionTaxCreditEvaluation,
    PensionTaxCreditInput,
    ProfileEvaluation,
    ProfileSurveyInput,
    SimulationEvaluation,
    SimulationInput,
    aggregate_accounts,
    build_allocation_example,
    calculate_pension_tax_credit,
    estimate_non_pension_withdrawal_tax,
    evaluate_account_diagnostics,
    evaluate_profile,
    simulate_accumulation,
)

PENSION_TAX_CLOSING_NOTICE = (
    "자세한 내용은 금융기관에 확인하거나 세무전문가와 상담해야 해요."
)


def account_diagnostics_tool(
    account: AccountInput,
) -> AccountDiagnosticsEvaluation:
    """Evaluate one explicitly supplied pension account with rule-engine checks."""

    return evaluate_account_diagnostics(account)


def account_aggregation_tool(inputs: AggregationInput) -> AggregationEvaluation:
    """Aggregate explicitly supplied pension accounts; no account data is fetched."""

    return aggregate_accounts(inputs)


def accumulation_simulation_tool(inputs: SimulationInput) -> SimulationEvaluation:
    """Run the approved educational accumulation assumptions for supplied inputs."""

    return simulate_accumulation(inputs)


def profile_assessment_tool(inputs: ProfileSurveyInput) -> ProfileEvaluation:
    """Evaluate an explicitly supplied investment-profile survey with fixed rules."""

    return evaluate_profile(inputs)


def allocation_example_tool(
    inputs: AllocationExampleInput,
) -> AllocationExampleEvaluation:
    """Build an approved educational allocation example, not a recommendation."""

    return build_allocation_example(inputs)


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


ENGINE_AGENT_TOOLS = (
    account_diagnostics_tool,
    accumulation_simulation_tool,
    profile_assessment_tool,
    allocation_example_tool,
    account_aggregation_tool,
)

PENSION_TAX_AGENT_TOOLS = (
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)

CHAT_AGENT_TOOLS = ENGINE_AGENT_TOOLS + PENSION_TAX_AGENT_TOOLS
