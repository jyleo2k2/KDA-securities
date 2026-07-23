"""Pension tax calculation and deterministic response handlers."""

from datetime import date
from decimal import Decimal

from ...engine import (
    IsaTransferEligibilityStatus,
    NonPensionWithdrawalEvaluation,
    PensionTaxCreditEvaluation,
    PensionTaxToolResult,
    WithdrawalCalculationStatus,
)
from ..models import (
    AnswerSection,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    DataBoundary,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from ..pension_tax_parser import resolve_pension_tax_inputs
from ..query_planner import QueryPlan, is_missed_tax_credit_question
from ..tools import (
    PENSION_TAX_CLOSING_NOTICE,
    calculate_pension_tax_credit_tool,
    estimate_non_pension_withdrawal_tax_tool,
)
from ._shared import _decimal_text

PENSION_TAX_REFUND_NOTICE = (
    "실제 환급액은 소득세 결정세액 등에 따라 달라질 수 있으므로 자세한 "
    "내용은 금융기관에 확인하거나 세무전문가와 상담해야 해요."
)
PENSION_TAX_LOCAL_INCOME_TAX_NOTICE = (
    "세액공제율과 세액공제액은 지방소득세를 고려해서 계산했어요."
)
MISSED_TAX_CREDIT_DATA_MODE = "missed_pension_tax_credit_engine"


def pension_tax_response(
    request: ChatRequest,
    plan: QueryPlan,
    *,
    prefer_structured: bool = False,
) -> ChatResponse:
    resolved_inputs = resolve_pension_tax_inputs(
        request.message,
        request.pension_tax,
        prefer_structured=prefer_structured,
    )
    missing: list[str] = []
    if plan.requests_tax_credit and resolved_inputs.tax_credit is None:
        missing.extend(resolved_inputs.missing_tax_credit)
    if plan.requests_withdrawal_tax and resolved_inputs.withdrawal is None:
        missing.extend(resolved_inputs.missing_withdrawal)
    if missing:
        missing_text = "·".join(dict.fromkeys(missing))
        return ChatResponse(
            intent=ChatIntent.PENSION_TAX,
            answer=(
                f"계산에 필요한 {missing_text}이(가) 빠져 있어요. "
                "해당 값만 질문에 적거나 연금세액 입력 화면에 "
                f"입력해 주세요.\n{PENSION_TAX_CLOSING_NOTICE}"
            ),
            data_mode="input_required",
            limitations=[
                "계좌번호·주민등록번호·인증정보는 입력하지 마세요.",
        "입력 금액은 세무자문이 아닌 간이 계산에만 사용합니다.",
            ],
        )

    tax_credit: PensionTaxCreditEvaluation | None = None
    withdrawal: NonPensionWithdrawalEvaluation | None = None
    if plan.requests_tax_credit:
        assert resolved_inputs.tax_credit is not None
        tax_credit = calculate_pension_tax_credit_tool(resolved_inputs.tax_credit)
    if plan.requests_withdrawal_tax:
        assert resolved_inputs.withdrawal is not None
        withdrawal = estimate_non_pension_withdrawal_tax_tool(
            resolved_inputs.withdrawal
        )
    result = PensionTaxToolResult(
        tax_credit=tax_credit,
        withdrawal=withdrawal,
    )
    sources = pension_tax_sources(result)
    numeric: list[NumericEvidence] = []
    sections: list[AnswerSection] = []
    answer_parts: list[str] = []
    limitations: list[str] = []

    if tax_credit is not None:
        if (
            is_missed_tax_credit_question(request.message)
            and tax_credit.rate_determined
            and resolved_inputs.tax_credit is not None
            and tax_credit.additional_tax_credit_krw is not None
        ):
            maximum_input = resolved_inputs.tax_credit.model_copy(
                update={
                    "pension_savings_contribution_krw": Decimal("6000000"),
                    "irp_contribution_krw": Decimal("3000000"),
                    "dc_employee_additional_contribution_krw": Decimal("0"),
                    "isa_maturity_transfer_krw": Decimal("0"),
                    "isa_transfer_eligibility_status": (
                        IsaTransferEligibilityStatus.NONE
                    ),
                    "isa_additional_limit_used_prior_tax_year_krw": Decimal("0"),
                }
            )
            maximum_credit = calculate_pension_tax_credit_tool(maximum_input)
            maximum_effect = maximum_credit.rate_scenarios[
                0
            ].estimated_total_tax_reduction_effect_krw
            remaining = tax_credit.remaining_eligible_contribution_krw
            missed_effect = tax_credit.additional_tax_credit_krw
            return ChatResponse(
                intent=ChatIntent.PENSION_TAX,
                answer=(
                    "고객님은 올해 "
                    f"{missed_effect:,.0f}원 만큼의 세금을 덜 돌려받고 있어요.\n\n"
                    "연금저축계좌나 IRP 또는 DC형 계좌에 "
                    f"{remaining:,.0f}원 만큼을 추가로 납입하세요.\n\n"
                    "그러면 고객님의 "
                    f"최대 세액공제혜택 {maximum_effect:,.0f}원을 온전히 "
                    "받을 수 있어요."
                ),
                data_mode=MISSED_TAX_CREDIT_DATA_MODE,
                sources=pension_tax_sources(
                    PensionTaxToolResult(tax_credit=tax_credit)
                ),
                numeric_evidence=[
                    NumericEvidence(
                        label="추가 납입 가능액",
                        value=remaining,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="일반 합산 세액공제 대상 한도 900만원의 남은 금액",
                    ),
                    NumericEvidence(
                        label="놓친 예상 세액공제혜택",
                        value=missed_effect,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="남은 합산 한도와 지방소득세 포함 세액공제율",
                    ),
                    NumericEvidence(
                        label="최대 세액공제혜택",
                        value=maximum_effect,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="합산 한도 900만원을 채운 규칙 엔진 시나리오",
                    ),
                ],
                pension_tax_result=PensionTaxToolResult(tax_credit=tax_credit),
                limitations=[
                    PENSION_TAX_REFUND_NOTICE,
                    PENSION_TAX_LOCAL_INCOME_TAX_NOTICE,
                    (
                        "연금저축은 연 600만원 한도 안에서, 나머지는 IRP 또는 "
                        "DC형 본인 추가납입 한도 안에서 채워야 해요."
                    ),
                ],
            )
        credit_text = tax_credit_text(tax_credit)
        answer_parts.append(credit_text)
        tax_input = resolved_inputs.tax_credit
        tax_numeric = tax_credit_numeric(tax_credit)
        if (
            tax_input is not None
            and tax_input.income_amount_krw is not None
            and tax_credit.rate_determined
        ):
            rate = tax_credit.rate_scenarios[0]
            primary_labels = {
                "연금저축 당해연도 납입액",
                "IRP 당해연도 납입액",
                "합산 세액공제 대상 납입액",
                f"{rate.label} 표시율",
                f"{rate.label} 지방세 포함 예상 절세효과",
            }
            numeric.extend(
                [
                    NumericEvidence(
                        label=(
                            "총급여액"
                            if tax_input.income_basis.value == "gross_salary"
                            else "종합소득금액"
                        ),
                        value=tax_input.income_amount_krw,
                        unit="KRW",
                        evidence_id="user:pension_tax",
                        basis="세액공제율 적용을 위한 사용자 소득정보",
                    ),
                    NumericEvidence(
                        label="세액공제율",
                        value=rate.local_inclusive_display_rate_percent,
                        unit="%",
                        evidence_id="rule:pension_tax:credit",
                        basis="소득세율과 개인지방소득세 효과 포함",
                    ),
                    NumericEvidence(
                        label="올해 연금저축 납입액",
                        value=tax_credit.pension_savings_contribution_krw,
                        unit="KRW",
                        evidence_id="user:pension_tax",
                        basis="사용자 입력",
                    ),
                    NumericEvidence(
                        label="올해 IRP 납입액",
                        value=tax_credit.irp_contribution_krw,
                        unit="KRW",
                        evidence_id="user:pension_tax",
                        basis="사용자 입력",
                    ),
                    NumericEvidence(
                        label="세액공제대상 납입액",
                        value=tax_credit.total_eligible_contribution_krw,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="2026년 일반 합산 900만원 및 적격 ISA 추가 한도",
                    ),
                    NumericEvidence(
                        label="세액공제액",
                        value=rate.estimated_total_tax_reduction_effect_krw,
                        unit="KRW",
                        evidence_id="engine:pension_tax",
                        basis="법정 세액공제액과 개인지방소득세 효과 합산",
                    ),
                ]
            )
            numeric.extend(
                item for item in tax_numeric if item.label not in primary_labels
            )
        else:
            numeric.extend(tax_numeric)
        limitations.append(PENSION_TAX_REFUND_NOTICE)
        limitations.append(PENSION_TAX_LOCAL_INCOME_TAX_NOTICE)
        limitations.append("세액공제 계산과 같은 해 중도해지 추정은 별도 가정이에요.")
        if "ISA 만기자금" in tax_credit.assumption_notice:
            limitations.append(
                "ISA 만기자금 전환의 법정 요건이 확인되지 않아 해당 금액은 "
                "계산에서 제외했어요."
            )

    if withdrawal is not None:
        withdrawal_answer = withdrawal_text(withdrawal)
        answer_parts.append(withdrawal_answer)
        sections.append(
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="연금외수령 기타소득 간이 추정",
                content=withdrawal_answer,
                evidence_ids=[
                    "user:pension_tax",
                    "engine:pension_tax",
                    "rule:pension_tax:withdrawal_order",
                    "rule:pension_tax:withdrawal",
                ],
            )
        )
        numeric.extend(withdrawal_numeric(withdrawal))
        limitations.extend(withdrawal.assumptions)
        limitations.extend(withdrawal.limitations)

    return ChatResponse(
        intent=ChatIntent.PENSION_TAX,
        answer=" ".join(answer_parts) + f"\n{PENSION_TAX_CLOSING_NOTICE}",
        data_mode="user_input_engine",
        sections=sections,
        sources=sources,
        numeric_evidence=numeric,
        pension_tax_result=result,
        limitations=list(dict.fromkeys(limitations)),
    )


def pension_tax_sources(
    result: PensionTaxToolResult,
) -> list[SourceEvidence]:
    evidence = [
        *(result.tax_credit.evidence if result.tax_credit is not None else []),
        *(result.withdrawal.evidence if result.withdrawal is not None else []),
    ]
    credit_source = next(
        (item for item in evidence if "59조의3" in item.label),
        None,
    )
    withdrawal_source = next(
        (item for item in evidence if "원천징수세율" in item.label),
        None,
    )
    withdrawal_order_source = next(
        (item for item in evidence if "인출순서" in item.label),
        None,
    )
    sources = [
        SourceEvidence(
            evidence_id="user:pension_tax",
            label="사용자가 입력한 계좌 잔액·당해연도 납입액",
            locator="request://pension-tax",
            publisher="사용자 입력",
            data_boundary=DataBoundary.USER_INPUT,
        ),
        SourceEvidence(
            evidence_id="engine:pension_tax",
            label="연금계좌 세액공제·연금외수령 규칙 엔진",
            locator="engine://pension_tax_guidance/2026-07-20.1",
            publisher="연금 코파일럿 규칙 엔진",
            as_of=date(2026, 7, 15),
            data_boundary=DataBoundary.ENGINE,
        ),
    ]
    if result.tax_credit is not None and credit_source is not None:
        sources.append(
            SourceEvidence(
                evidence_id="rule:pension_tax:credit",
                label=credit_source.label,
                locator=credit_source.reference,
                publisher="국가법령정보센터",
                as_of=credit_source.as_of,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            )
        )
    if result.withdrawal is not None and withdrawal_source is not None:
        if withdrawal_order_source is not None:
            sources.append(
                SourceEvidence(
                    evidence_id="rule:pension_tax:withdrawal_order",
                    label=withdrawal_order_source.label,
                    locator=withdrawal_order_source.reference,
                    publisher="국가법령정보센터",
                    as_of=withdrawal_order_source.as_of,
                    data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
                )
            )
        sources.append(
            SourceEvidence(
                evidence_id="rule:pension_tax:withdrawal",
                label=withdrawal_source.label,
                locator=withdrawal_source.reference,
                publisher="국세청",
                as_of=withdrawal_source.as_of,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            )
        )
    return sources


def krw(value: Decimal) -> str:
    if value >= 10_000:
        in_man = value / Decimal("10000")
        text = f"{in_man:,.4f}".rstrip("0").rstrip(".")
        return f"{text}만 원"
    return f"{value:,.0f}원"


def tax_credit_text(result: PensionTaxCreditEvaluation) -> str:
    base = (
        "세액공제 대상은 총 "
        f"{krw(result.total_eligible_contribution_krw)}이에요. "
        "입력한 납입액은 연금저축 "
        f"{krw(result.pension_savings_contribution_krw)}, IRP "
        f"{krw(result.irp_contribution_krw)}, DC 근로자 추가납입 "
        f"{krw(result.dc_employee_additional_contribution_krw)}입니다."
    )
    if result.isa_maturity_transfer_krw > 0:
        base += (
            " ISA 만기자금 전환액은 "
            f"{krw(result.isa_maturity_transfer_krw)}, 추가 한도는 "
            f"{krw(result.isa_additional_credit_limit_krw)}입니다."
        )
    if result.total_excluded_contribution_krw > 0:
        base += (
            " 회사 DC 부담금·퇴직급여 이전액·연금계좌 간 이전액 중 "
            f"{krw(result.total_excluded_contribution_krw)}은 "
            "세액공제 계산에서 제외했습니다."
        )
    if result.rate_determined:
        scenario = result.rate_scenarios[0]
        return (
            f"{base} 소득세법상 세액공제율 "
            f"{_decimal_text(scenario.income_tax_rate_percent)}% 기준 법정 "
            f"세액공제액은 {krw(scenario.income_tax_credit_krw)}, "
            "개인지방소득세 효과를 포함한 예상 절세효과는 "
            f"{krw(scenario.estimated_total_tax_reduction_effect_krw)}입니다. "
            "실제 환급액은 결정세액 등에 따라 달라질 수 있습니다."
        )
    ordered = sorted(
        result.rate_scenarios,
        key=lambda item: item.income_tax_credit_krw,
    )
    return (
        f"{base} 소득정보가 없어 법정 세액공제액은 "
        f"{krw(ordered[0].income_tax_credit_krw)}부터 "
        f"{krw(ordered[-1].income_tax_credit_krw)}까지, "
        "개인지방소득세 효과를 포함한 예상 절세효과는 "
        f"{krw(ordered[0].estimated_total_tax_reduction_effect_krw)}부터 "
        f"{krw(ordered[-1].estimated_total_tax_reduction_effect_krw)}"
        "까지입니다. "
        "실제 환급액은 결정세액 등에 따라 달라질 수 있습니다."
    )


def tax_credit_numeric(
    result: PensionTaxCreditEvaluation,
) -> list[NumericEvidence]:
    numeric = [
        NumericEvidence(
            label="연금저축 당해연도 납입액",
            value=result.pension_savings_contribution_krw,
            unit="KRW",
            evidence_id="user:pension_tax",
            basis="사용자 입력",
        ),
        NumericEvidence(
            label="IRP 당해연도 납입액",
            value=result.irp_contribution_krw,
            unit="KRW",
            evidence_id="user:pension_tax",
            basis="사용자 입력",
        ),
        NumericEvidence(
            label="DC 근로자 본인 추가납입액",
            value=result.dc_employee_additional_contribution_krw,
            unit="KRW",
            evidence_id="user:pension_tax",
            basis="사용자 입력",
        ),
        NumericEvidence(
            label="세액공제 제외 납입·이전액",
            value=result.total_excluded_contribution_krw,
            unit="KRW",
            evidence_id="engine:pension_tax",
            basis="회사 DC 부담금·퇴직급여 이전액·연금계좌 간 이전액 제외",
        ),
        NumericEvidence(
            label="합산 세액공제 대상 납입액",
            value=result.total_eligible_contribution_krw,
            unit="KRW",
            evidence_id="engine:pension_tax",
            basis="2026년 일반 합산 900만원 및 적격 ISA 추가 한도",
        ),
        NumericEvidence(
            label="ISA 전환 추가 세액공제 한도",
            value=result.isa_additional_credit_limit_krw,
            unit="KRW",
            evidence_id="engine:pension_tax",
            basis="적격 ISA 만기자금 전환액의 10%, 누적 최대 300만원",
        ),
    ]
    for scenario in result.rate_scenarios:
        numeric.extend(
            [
                NumericEvidence(
                    label=(
                        "지방세 제외 세액공제율"
                        if result.rate_determined
                        else f"{scenario.label} 지방세 제외 세액공제율"
                    ),
                    value=scenario.income_tax_rate_percent,
                    unit="%",
                    evidence_id="rule:pension_tax:credit",
                    basis="소득세법상 세액공제율",
                ),
                NumericEvidence(
                    label=f"{scenario.label} 표시율",
                    value=scenario.local_inclusive_display_rate_percent,
                    unit="%",
                    evidence_id="rule:pension_tax:credit",
                    basis="소득세율과 개인지방소득세 효과 포함",
                ),
                NumericEvidence(
                    label=f"{scenario.label} 법정 세액공제액",
                    value=scenario.income_tax_credit_krw,
                    unit="KRW",
                    evidence_id="engine:pension_tax",
                    basis="소득세법상 세액공제율 적용",
                ),
                NumericEvidence(
                    label=f"{scenario.label} 지방세 포함 예상 절세효과",
                    value=scenario.estimated_total_tax_reduction_effect_krw,
                    unit="KRW",
                    evidence_id="engine:pension_tax",
                    basis="법정 세액공제액과 개인지방소득세 효과 합산",
                ),
            ]
        )
    return numeric


def withdrawal_text(
    result: NonPensionWithdrawalEvaluation,
) -> str:
    if result.status == WithdrawalCalculationStatus.REQUIRES_REVIEW:
        if result.total_balance_krw is None:
            return (
                "의료비 등 부득이한 인출 사유는 일반 연금외수령과 "
                "세금 부과 방식이 다를 수 있어 예상세액을 계산하지 않았어요. "
                "먼저 법정 요건과 적용 방식을 확인해야 해요."
            )
        return (
            f"두 계좌 잔액 합계는 {krw(result.total_balance_krw)}이에요. "
            "인출 사유를 먼저 확인해야 해서 기타소득 예상액은 계산하지 않았어요."
        )
    assert result.assumed_other_income_tax_base_krw is not None
    assert result.other_income_rate_percent is not None
    assert result.estimated_max_other_income_withholding_krw is not None
    return (
        f"두 계좌 잔액 합계 {krw(result.total_balance_krw)}에서 "
        "당해연도 납입 과세제외액 "
        f"{krw(result.total_current_year_contribution_excluded_krw)} 등을 "
        "반영한 16.5% 간이 과세대상액은 "
        f"{krw(result.assumed_other_income_tax_base_krw)}이에요. "
        "지방소득세를 포함한 기타소득 원천징수 최대 간이 추정액은 "
        f"{krw(result.estimated_max_other_income_withholding_krw)}이에요."
    )


def withdrawal_numeric(
    result: NonPensionWithdrawalEvaluation,
) -> list[NumericEvidence]:
    numeric = []
    if result.total_balance_krw is not None:
        numeric.append(
            NumericEvidence(
                label="연금저축·IRP 잔액 합계",
                value=result.total_balance_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="사용자 입력 잔액 합산",
            )
        )
    if result.status == WithdrawalCalculationStatus.REQUIRES_REVIEW:
        return numeric
    assert result.assumed_other_income_tax_base_krw is not None
    assert result.other_income_rate_percent is not None
    assert result.estimated_max_other_income_withholding_krw is not None
    numeric.extend(
        [
            NumericEvidence(
                label="당해연도 납입 과세제외액",
                value=result.total_current_year_contribution_excluded_krw,
                unit="KRW",
                evidence_id="rule:pension_tax:withdrawal_order",
                basis="소득세법 시행령 인출순서",
            ),
            NumericEvidence(
                label="기타소득 간이 과세대상액",
                value=result.assumed_other_income_tax_base_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="과세제외 재원을 차감한 규칙 엔진 계산",
            ),
            NumericEvidence(
                label="연금외수령 기타소득 표시세율",
                value=result.other_income_rate_percent,
                unit="%",
                evidence_id="rule:pension_tax:withdrawal",
                basis="소득세 15%와 개인지방소득세 1.5% 포함",
            ),
            NumericEvidence(
                label="최대 기타소득 원천징수 간이 추정액",
                value=result.estimated_max_other_income_withholding_krw,
                unit="KRW",
                evidence_id="engine:pension_tax",
                basis="규칙 엔진 계산",
            ),
        ]
    )
    return numeric
