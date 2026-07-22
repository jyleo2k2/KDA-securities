"""Deterministic pension-calculator engine using approved education assumptions."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from .assumptions import (
    ALLOCATION_MATRIX,
    ASSUMPTION_SOURCE,
    ASSUMPTION_VERSION,
    PENSION_SAVINGS_EXTENSION,
    age_band,
    net_annual_return_percent,
)
from .educational_portfolio import PROFILE_POLICY
from .educational_portfolio import RiskProfile as EducationalRiskProfile
from .models import (
    AccountType,
    AllocationWeights,
    PensionCalculatorAssumption,
    PensionCalculatorEvaluation,
    PensionCalculatorHeadline,
    PensionCalculatorInput,
    PensionCalculatorStrategy,
    PensionCalculatorTax,
    PensionCalculatorYear,
    RiskProfile,
    SourceChip,
)
from .strategy_presentation import get_strategy_presentation

KRW_QUANTUM = Decimal("1")
ONE_HUNDRED = Decimal("100")
TWELVE = Decimal("12")
DC_IRP_GROWTH_LIMIT_PERCENT = Decimal("70")
ANNUAL_PENSION_THRESHOLD_KRW = Decimal("15000000")
SEPARATE_TAX_RATE_PERCENT = Decimal("16.5")
WITHDRAWAL_LIMIT_MULTIPLIER = Decimal("1.2")

ASSUMPTION_NOTICE = (
    "미래 수익 예측이 아니라 사용자가 선택한 교육용 가정 시나리오입니다."
)
BASE_WARNINGS = (
    "assumes_pension_account_held_for_at_least_five_years",
    "deferred_severance_income_excluded",
    "tax_rules_as_of_2026_and_actual_tax_depends_on_personal_circumstances",
)
PROFILE_ORDER = tuple(RiskProfile)
PROFILE_RANK = {profile: rank for rank, profile in enumerate(PROFILE_ORDER, start=1)}


def _krw(value: Decimal) -> Decimal:
    return value.quantize(KRW_QUANTUM, rounding=ROUND_HALF_UP)


def _strategy_id(profile: RiskProfile) -> str:
    educational_profile = EducationalRiskProfile(profile.value)
    return str(PROFILE_POLICY[educational_profile]["strategy"])


def _strategy_profile(strategy_id: str) -> RiskProfile:
    for profile in PROFILE_ORDER:
        if _strategy_id(profile) == strategy_id:
            return profile
    raise ValueError("strategy_id is not a known educational strategy")


def _allocation(
    *,
    account_type: AccountType,
    age: int,
    profile: RiskProfile,
) -> AllocationWeights:
    band = age_band(age)
    weights = ALLOCATION_MATRIX[band][profile]
    if account_type == AccountType.PENSION_SAVINGS:
        weights = PENSION_SAVINGS_EXTENSION.get((band, profile), weights)
    elif weights.growth_percent > DC_IRP_GROWTH_LIMIT_PERCENT:
        raise ValueError("DC/IRP growth allocation exceeds the 70 percent limit")
    return weights


def _monthly_rate(annual_return_percent: Decimal) -> Decimal:
    return (Decimal("1") + annual_return_percent / ONE_HUNDRED) ** (
        Decimal("1") / TWELVE
    ) - Decimal("1")


def _build_strategies(
    inputs: PensionCalculatorInput,
    *,
    selected_profile: RiskProfile | None = None,
    selected_annual_return_percent: Decimal | None = None,
) -> list[PensionCalculatorStrategy]:
    band = age_band(inputs.current_age)
    candidates: list[tuple[RiskProfile, str, AllocationWeights, Decimal]] = []
    for profile in PROFILE_ORDER:
        weights = ALLOCATION_MATRIX[band][profile]
        if (
            inputs.account_type in {AccountType.DC, AccountType.IRP}
            and weights.growth_percent > DC_IRP_GROWTH_LIMIT_PERCENT
        ):
            raise ValueError("DC/IRP growth allocation exceeds the 70 percent limit")
        annual_return = net_annual_return_percent(weights, inputs.scenario)
        if profile == selected_profile and selected_annual_return_percent is not None:
            annual_return = selected_annual_return_percent
        candidates.append(
            (
                profile,
                _strategy_id(profile),
                weights,
                annual_return,
            )
        )

    candidates.sort(key=lambda item: (-item[3], PROFILE_RANK[item[0]]))
    eligible_ids = [
        strategy_id
        for profile, strategy_id, _, _ in candidates
        if PROFILE_RANK[profile] <= PROFILE_RANK[inputs.risk_profile]
    ]
    default_ids = set(eligible_ids[:3])

    return [
        PensionCalculatorStrategy(
            strategy_id=strategy_id,
            presentation=get_strategy_presentation(strategy_id),
            risk_profile=profile,
            net_annual_return_percent=annual_return,
            growth_percent=weights.growth_percent,
            safe_percent=weights.safe_percent,
            cash_percent=weights.cash_percent,
            within_profile=(
                PROFILE_RANK[profile] <= PROFILE_RANK[inputs.risk_profile]
            ),
            default_visible=strategy_id in default_ids,
        )
        for profile, strategy_id, weights, annual_return in candidates
    ]


def _accumulate(
    inputs: PensionCalculatorInput,
    strategy_profile: RiskProfile,
    annual_return_override_percent: Decimal | None = None,
) -> tuple[Decimal, list[PensionCalculatorYear]]:
    balance = inputs.current_balance_krw
    yearly: list[PensionCalculatorYear] = []
    contribution_years = inputs.contribution_end_age - inputs.current_age
    monthly_rates = {}

    for month_index in range(contribution_years * 12):
        age = inputs.current_age + month_index // 12
        band = age_band(age)
        if band not in monthly_rates:
            weights = _allocation(
                account_type=inputs.account_type,
                age=age,
                profile=strategy_profile,
            )
            annual_return = (
                annual_return_override_percent
                if annual_return_override_percent is not None
                else net_annual_return_percent(weights, inputs.scenario)
            )
            monthly_rates[band] = _monthly_rate(annual_return)
        balance = balance * (Decimal("1") + monthly_rates[band])
        balance += inputs.monthly_contribution_krw

        if (month_index + 1) % 12 == 0:
            year_index = (month_index + 1) // 12
            rounded_balance = _krw(balance)
            principal = _krw(
                inputs.current_balance_krw
                + inputs.monthly_contribution_krw * Decimal(year_index * 12)
            )
            yearly.append(
                PensionCalculatorYear(
                    year_index=year_index,
                    age=inputs.current_age + year_index,
                    cumulative_principal_krw=principal,
                    cumulative_gain_krw=rounded_balance - principal,
                    balance_krw=rounded_balance,
                )
            )

    return balance, yearly


def _payout_rate(
    inputs: PensionCalculatorInput,
    strategy_profile: RiskProfile,
    annual_return_override_percent: Decimal | None = None,
) -> Decimal:
    if annual_return_override_percent is not None:
        return _monthly_rate(annual_return_override_percent)
    weights = _allocation(
        account_type=inputs.account_type,
        age=inputs.contribution_end_age,
        profile=strategy_profile,
    )
    return _monthly_rate(net_annual_return_percent(weights, inputs.scenario))


def _monthly_payout(
    balance: Decimal,
    monthly_rate: Decimal,
    payout_years: int,
) -> Decimal:
    month_count = Decimal(payout_years * 12)
    if monthly_rate == 0:
        return balance / month_count
    return balance * monthly_rate / (
        Decimal("1") - (Decimal("1") + monthly_rate) ** (-month_count)
    )


def _age_rate(age: int) -> Decimal:
    if age >= 80:
        return Decimal("3.3")
    if age >= 70:
        return Decimal("4.4")
    return Decimal("5.5")


def _tax_rates(
    *,
    annual_payout: Decimal,
    pension_start_age: int,
    payout_years: int,
) -> tuple[list[Decimal], bool]:
    exceeds_threshold = annual_payout > ANNUAL_PENSION_THRESHOLD_KRW
    if exceeds_threshold:
        return [SEPARATE_TAX_RATE_PERCENT] * payout_years, True
    return [
        _age_rate(pension_start_age + year_index)
        for year_index in range(payout_years)
    ], False


def _withdrawal_limit_excess_years(
    *,
    starting_balance: Decimal,
    monthly_rate: Decimal,
    monthly_payout: Decimal,
    payout_years: int,
) -> list[int]:
    balance = starting_balance
    excess_years: list[int] = []
    for year_index in range(1, min(payout_years, 10) + 1):
        limit = (
            balance
            / Decimal(11 - year_index)
            * WITHDRAWAL_LIMIT_MULTIPLIER
        )
        if monthly_payout * TWELVE > limit:
            excess_years.append(year_index)
        for _ in range(12):
            balance = balance * (Decimal("1") + monthly_rate) - monthly_payout
    return excess_years


def calculate_pension(
    inputs: PensionCalculatorInput,
    *,
    annual_return_override_percent: Decimal | None = None,
    assumption_source: SourceChip = ASSUMPTION_SOURCE,
    assumption_version: str = ASSUMPTION_VERSION,
    assumption_notice: str = ASSUMPTION_NOTICE,
    additional_warnings: tuple[str, ...] = (),
) -> PensionCalculatorEvaluation:
    """Evaluate accumulation, payout, strategies, and documented 2026 tax rules."""

    with localcontext() as context:
        context.prec = 50
        if (
            annual_return_override_percent is not None
            and annual_return_override_percent <= Decimal("-100")
        ):
            raise ValueError("annual return override must be greater than -100 percent")
        selected_profile = (
            inputs.risk_profile
            if inputs.strategy_id is None
            else _strategy_profile(inputs.strategy_id)
        )
        ending_balance, yearly = _accumulate(
            inputs,
            selected_profile,
            annual_return_override_percent,
        )
        monthly_rate = _payout_rate(
            inputs,
            selected_profile,
            annual_return_override_percent,
        )
        monthly_payout = _monthly_payout(
            ending_balance,
            monthly_rate,
            inputs.payout_years,
        )
        annual_payout = monthly_payout * TWELVE
        rates, exceeds_threshold = _tax_rates(
            annual_payout=annual_payout,
            pension_start_age=inputs.contribution_end_age,
            payout_years=inputs.payout_years,
        )
        effective_rate = sum(rates, Decimal("0")) / Decimal(len(rates))
        first_year_after_tax = monthly_payout * (
            Decimal("1") - rates[0] / ONE_HUNDRED
        )

        warnings = list(BASE_WARNINGS) + list(additional_warnings)
        if exceeds_threshold:
            warnings.append(
                "annual_payout_over_15m_assumes_16_5_percent_separate_taxation;"
                "comprehensive_taxation_may_be_more_favorable"
            )
        excess_years = _withdrawal_limit_excess_years(
            starting_balance=ending_balance,
            monthly_rate=monthly_rate,
            monthly_payout=monthly_payout,
            payout_years=inputs.payout_years,
        )
        if excess_years:
            warnings.append(
                "pension_withdrawal_limit_exceeded_years:"
                + ",".join(str(year) for year in excess_years)
            )

        total = _krw(ending_balance)
        principal = _krw(
            inputs.current_balance_krw
            + inputs.monthly_contribution_krw
            * Decimal((inputs.contribution_end_age - inputs.current_age) * 12)
        )
        return PensionCalculatorEvaluation(
            headline=PensionCalculatorHeadline(
                total_krw=total,
                total_principal_krw=principal,
                total_gain_krw=total - principal,
                monthly_payout_pretax_krw=_krw(monthly_payout),
                monthly_payout_after_tax_krw=_krw(first_year_after_tax),
                contribution_years=(
                    inputs.contribution_end_age - inputs.current_age
                ),
            ),
            yearly=yearly,
            strategies=_build_strategies(
                inputs,
                selected_profile=selected_profile,
                selected_annual_return_percent=annual_return_override_percent,
            ),
            tax=PensionCalculatorTax(
                withholding_rate_percent_by_year=rates,
                effective_rate_percent=effective_rate,
                annual_payout_krw=_krw(annual_payout),
                exceeds_annual_15m_threshold=exceeds_threshold,
                deferred_severance_excluded=True,
            ),
            assumption=PensionCalculatorAssumption(
                version=assumption_version,
                scenario=inputs.scenario,
                source=assumption_source,
                notice=assumption_notice,
            ),
            warnings=warnings,
        )
