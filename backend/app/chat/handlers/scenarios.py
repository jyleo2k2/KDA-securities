"""Mock customer scenario selection and diagnosis handlers."""

from ...engine import AccountType, evaluate_mock_scenario
from ..models import (
    AnswerSection,
    ChatIntent,
    ChatResponse,
    DataBoundary,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from ..scenarios import ScenarioRepository
from ._shared import (
    _ACCOUNT_TYPE_LABELS,
    _ASSET_CLASS_LABELS,
    SCENARIO_KEYWORDS,
    _decimal_text,
    _scenario_holdings_summary,
    _scenario_rebalancing_summary,
)


def scenario_response(
    scenario_code: str,
    *,
    scenarios: ScenarioRepository,
) -> ChatResponse:
    scenario = scenarios.get(scenario_code)
    if scenario is None:
        return scenario_selection_response(
            limitation="선택한 예시 계좌를 찾지 못했어요.",
            scenarios=scenarios,
        )
    evaluation = evaluate_mock_scenario(scenario)
    sources = [
        SourceEvidence(
            evidence_id="mock:scenario",
            label=evaluation.source.label,
            locator=evaluation.source.reference,
            as_of=evaluation.source.as_of,
            data_boundary=DataBoundary.MOCK,
        ),
        SourceEvidence(
            evidence_id="engine:scenario",
            label="목계좌 통합 집계 엔진",
            locator=f"engine://{evaluation.engine_name}/{evaluation.engine_version}",
            as_of=evaluation.source.as_of,
            data_boundary=DataBoundary.ENGINE,
        ),
    ]
    account_lines: list[str] = []
    has_limit_breach = False
    risk_term_explained = False
    numeric = [
        NumericEvidence(
            label="목시나리오 총자산",
            value=evaluation.total_amount_krw,
            unit="KRW",
            evidence_id="engine:scenario",
            basis="목계좌 합산",
        )
    ]
    for result in evaluation.account_evaluations:
        account_code = result.evaluated_input.account_type.value
        account_name = _ACCOUNT_TYPE_LABELS[account_code]
        account_subject = {
            AccountType.DC.value: "DC형은",
            AccountType.IRP.value: "IRP는",
            AccountType.PENSION_SAVINGS.value: "연금저축펀드는",
        }[account_code]
        if result.limit_percent is None:
            account_lines.append(
                f"{account_subject} 비율 제한이 없어서 상품별로 담을 수 "
                "있는지만 확인하면 돼요"
            )
        else:
            ratio = _decimal_text(result.general_risky_ratio_percent)
            limit = _decimal_text(result.limit_percent)
            limit_status = (
                f"한도({limit}%) 안이에요"
                if result.within_limit
                else f"한도({limit}%)를 넘었어요"
            )
            risk_term = (
                "위험자산(주식처럼 가격이 오르내릴 수 있는 자산)"
                if not risk_term_explained
                else "위험자산"
            )
            account_lines.append(
                f"{account_subject} {risk_term}이 {ratio}%로 "
                f"{limit_status}"
            )
            risk_term_explained = True
            has_limit_breach = has_limit_breach or not result.within_limit
        numeric.append(
            NumericEvidence(
                label=f"{account_name} 일반 위험자산 비중",
                value=result.general_risky_ratio_percent,
                unit="%",
                evidence_id="engine:scenario",
                basis="규칙 엔진 계산",
            )
        )
        if result.limit_percent is not None:
            numeric.append(
                NumericEvidence(
                    label=f"{account_name} 일반 위험자산 한도",
                    value=result.limit_percent,
                    unit="%",
                    evidence_id="engine:scenario",
                    basis="규칙 엔진에 적용된 계좌 한도",
                )
            )
    for item in evaluation.asset_allocations:
        asset_name = _ASSET_CLASS_LABELS[item.asset_class_code]
        numeric.append(
            NumericEvidence(
                label=f"{asset_name} 통합 자산 비중",
                value=item.allocation_percent,
                unit="%",
                evidence_id="engine:scenario",
                basis="목계좌 통합 집계 엔진 계산",
            )
        )
    duplicate_text = (
        ", ".join(
            _ASSET_CLASS_LABELS[asset]
            for asset in evaluation.duplicated_asset_classes
        )
        if evaluation.duplicated_asset_classes
        else None
    )
    if duplicate_text and "현금성 자산" in duplicate_text:
        duplicate_text = duplicate_text.replace(
            "현금성 자산",
            "현금성 자산(예금·CMA처럼 바로 찾을 수 있는 돈)",
        )
    account_summary = ". ".join(account_lines)
    duplicate_summary = (
        f"여러 계좌에 {duplicate_text}이 겹쳐 있어요."
        if duplicate_text
        else "계좌 사이에 겹친 자산군은 없어요."
    )
    holdings_summary, holding_evidence = _scenario_holdings_summary(scenario)
    numeric.extend(holding_evidence)
    rebalancing_summary = _scenario_rebalancing_summary(
        evaluation.duplicated_asset_classes
    )
    conclusion = (
        "한도를 넘은 계좌가 있어요. "
        if has_limit_breach
        else "점검 결과 큰 문제는 없어요. "
    )
    answer = conclusion + f"{account_summary}. {duplicate_summary}"
    return ChatResponse(
        intent=ChatIntent.MOCK_PORTFOLIO,
        answer=answer,
        data_mode="mock_scenario",
        sections=[
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="계좌별 확인",
                content=account_summary,
                evidence_ids=["engine:scenario"],
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="자산 구성 그래프 안내",
                content=duplicate_summary,
                evidence_ids=["mock:scenario", "engine:scenario"],
            ),
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="보유 항목과 비중",
                content=holdings_summary,
                evidence_ids=["mock:scenario"],
            ),
            AnswerSection(
                kind=SectionKind.LIMITATION,
                title="리밸런싱 점검",
                content=rebalancing_summary,
                evidence_ids=["mock:scenario", "engine:scenario"],
            ),
        ],
        sources=sources,
        numeric_evidence=numeric,
        engine_results=evaluation.account_evaluations,
        scenario_evaluation=evaluation,
        limitations=["모든 계좌와 보유자산은 발표용 목데이터입니다."],
    )


def scenario_selection_response(
    limitation: str | None = None,
    *,
    scenarios: ScenarioRepository,
) -> ChatResponse:
    names = ", ".join(item.name for item in scenarios.list())
    limitations = [limitation] if limitation else []
    limitations.append("홈 또는 왼쪽 메뉴에서 진단할 가상 고객을 선택해 주세요.")
    return ChatResponse(
        intent=ChatIntent.MOCK_PORTFOLIO,
        answer=(
            "먼저 진단할 가상 고객을 선택해 주세요. "
            f"현재 선택할 수 있는 고객 유형은 {names}예요."
        ),
        data_mode="mock_scenario_selection",
        limitations=limitations,
    )


def scenario_code(message: str) -> str | None:
    return next(
        (code for keyword, code in SCENARIO_KEYWORDS.items() if keyword in message),
        None,
    )
