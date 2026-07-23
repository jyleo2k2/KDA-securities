"""Deterministic ETF distribution-event chat responses."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

import psycopg

from ...engine.distribution_reinvestment import (
    DistributionEventInput,
    DistributionHoldingInput,
    DistributionReinvestmentInput,
    DistributionStatus,
    calculate_distribution_reinvestment,
)
from ...etf_distribution_event_repository import (
    EtfDistributionEventUnavailable,
    PostgresEtfDistributionEventRepository,
)
from ..models import (
    AnswerBlock,
    AnswerBlockKind,
    AnswerSection,
    ChatIntent,
    ChatResponse,
    DataBoundary,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from ..query_planner import DistributionReinvestmentRequest


def distribution_event_response(
    isu_code: str | None,
    *,
    events: PostgresEtfDistributionEventRepository | None,
) -> ChatResponse:
    if isu_code is None:
        return ChatResponse(
            intent=ChatIntent.ETF_DISTRIBUTION,
            answer="확인할 ETF 종목코드 6자리를 함께 알려주세요.",
            data_mode="distribution_code_required",
            limitations=[
                "예: ‘069500 분배금·지급일 알려줘’처럼 종목코드를 입력하면 "
                "공식 이벤트 기준으로 확인합니다.",
                "자동 재투자나 주문은 실행하지 않습니다.",
            ],
        )
    if events is None:
        return _unavailable_response()
    try:
        dataset = events.latest_for_etf(isu_code)
    except (EtfDistributionEventUnavailable, psycopg.Error):
        return _unavailable_response()
    if not dataset.events:
        return ChatResponse(
            intent=ChatIntent.ETF_DISTRIBUTION,
            answer=f"{isu_code} ETF의 최신 공식 분배 이벤트가 확인되지 않았어요.",
            data_mode="official_distribution_event_empty",
            sources=[_master_source(dataset.as_of.isoformat())],
            limitations=[
                "이 답변은 최신 적재 기준일의 공식 이벤트 마스터만 조회합니다.",
                "예정 일정은 확정 현금분배 또는 재투자 계산에 포함하지 않습니다.",
            ],
        )

    sources: list[SourceEvidence] = []
    numeric_evidence: list[NumericEvidence] = []
    lines: list[str] = []
    evidence_ids: list[str] = []
    for index, event in enumerate(dataset.events[:3], start=1):
        evidence_id = f"distribution-event:{isu_code}:{index}"
        source = _event_source(event, evidence_id, dataset.as_of.isoformat())
        sources.append(source)
        evidence_ids.append(evidence_id)
        amount = event.get("cash_per_share_krw")
        amount_text = "금액 미공시"
        if amount is not None:
            value = Decimal(str(amount))
            amount_text = f"주당 {_decimal_text(value)}원"
            numeric_evidence.append(
                NumericEvidence(
                    label=f"{isu_code} 주당 현금분배",
                    value=value,
                    unit="KRW",
                    evidence_id=evidence_id,
                    basis="공식 이벤트 마스터의 주당 현금분배 금액",
                )
            )
        payment_date = event.get("payment_date") or "지급일 미공시"
        lines.append(
            " · ".join(
                (
                    _event_status(str(event.get("status", ""))),
                    f"기준일 {event['effective_date']}",
                    f"지급일 {payment_date}",
                    amount_text,
                )
            )
        )

    return ChatResponse(
        intent=ChatIntent.ETF_DISTRIBUTION,
        answer=f"{isu_code} ETF의 최신 공식 분배 이벤트를 확인했어요.",
        data_mode="official_distribution_event",
        sections=[
            AnswerSection(
                kind=SectionKind.FACT,
                title="분배금·지급일",
                content="공식 이벤트 마스터의 최근 기록입니다.",
                evidence_ids=evidence_ids,
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.BULLETS,
                        items=lines,
                    )
                ],
            )
        ],
        sources=sources,
        numeric_evidence=numeric_evidence,
        limitations=[
            "예정 일정은 참고용이며 확정 현금분배 또는 재투자 계산에 "
            "포함하지 않습니다.",
            "자동 재투자나 주문은 실행하지 않습니다.",
        ],
    )


def distribution_reinvestment_response(
    request: DistributionReinvestmentRequest | None,
    *,
    events: PostgresEtfDistributionEventRepository | None,
) -> ChatResponse:
    if request is None:
        return ChatResponse(
            intent=ChatIntent.ETF_DISTRIBUTION,
            answer="분배금 재투자 교육용 계산에 필요한 입력을 확인해 주세요.",
            data_mode="distribution_reinvestment_input_required",
            sections=[
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="입력 형식",
                    content=(
                        "`069500 재투자 수량=10 기준가=30000 "
                        "기준일=2026-07-01 리밸런싱일=2026-07-31`처럼 입력해 주세요."
                    ),
                )
            ],
            limitations=[
                "보유수량과 기준가는 사용자가 직접 입력한 교육용 값입니다.",
                "자동 재투자나 주문은 실행하지 않습니다.",
            ],
        )
    if events is None:
        return _unavailable_response()
    try:
        dataset = events.latest_for_etf(request.isu_code)
    except (EtfDistributionEventUnavailable, psycopg.Error):
        return _unavailable_response()

    inputs: list[DistributionEventInput] = []
    sources: list[SourceEvidence] = []
    for index, event in enumerate(dataset.events, start=1):
        status = _reinvestment_status(event)
        payment_date = event.get("payment_date")
        amount = event.get("cash_per_share_krw")
        if status is None or payment_date is None or amount is None:
            continue
        try:
            inputs.append(
                DistributionEventInput(
                    event_id=f"{request.isu_code}:{index}",
                    isu_code=request.isu_code,
                    payment_date=date.fromisoformat(str(payment_date)),
                    cash_per_share_krw=Decimal(str(amount)),
                    status=status,
                )
            )
        except (ValueError, ArithmeticError):
            continue
        sources.append(
            _event_source(
                event,
                f"distribution-event:{request.isu_code}:{index}",
                dataset.as_of.isoformat(),
            )
        )
    if not inputs:
        return ChatResponse(
            intent=ChatIntent.ETF_DISTRIBUTION,
            answer=(
                "공식 이벤트 마스터에서 재투자 계산에 쓸 분배금 지급 기록을 "
                "찾지 못했어요."
            ),
            data_mode="official_distribution_event_empty",
            sources=[_master_source(dataset.as_of.isoformat())],
            limitations=[
                "확정 현금분배 또는 참고용 예정 일정에 지급일과 주당 금액이 "
                "함께 있어야 계산합니다.",
                "자동 재투자나 주문은 실행하지 않습니다.",
            ],
        )

    evaluation = calculate_distribution_reinvestment(
        DistributionReinvestmentInput(
            as_of=request.as_of,
            rebalance_on=request.rebalance_on,
            holdings=[
                DistributionHoldingInput(
                    isu_code=request.isu_code,
                    quantity=request.quantity,
                    reinvestment_price_krw=request.reinvestment_price_krw,
                )
            ],
            events=inputs,
        )
    )
    evidence_id = sources[0].evidence_id if sources else "distribution-event-master"
    lines = [
        (
            f"{line.payment_date}: 현금 { _decimal_text(line.gross_cash_krw) }원 · "
            f"재투자 { _decimal_text(line.reinvested_quantity) }주 · "
            f"잔여 현금 { _decimal_text(line.remaining_cash_krw) }원"
        )
        for line in evaluation.lines
    ]
    return ChatResponse(
        intent=ChatIntent.ETF_DISTRIBUTION,
        answer=(
            "공식 분배금 이벤트와 입력한 보유수량으로 재투자·리밸런싱 "
            "현금흐름을 계산했어요."
        ),
        data_mode="distribution_reinvestment_guide",
        sections=[
            AnswerSection(
                kind=SectionKind.FACT,
                title="재투자·리밸런싱 현금흐름",
                content=(
                    f"{request.as_of}부터 {request.rebalance_on}까지 "
                    "지급되는 확정 현금분배만 리밸런싱 가능 현금으로 반영합니다."
                ),
                evidence_ids=[source.evidence_id for source in sources],
                blocks=[AnswerBlock(kind=AnswerBlockKind.BULLETS, items=lines)],
            )
        ],
        sources=sources,
        numeric_evidence=[
            NumericEvidence(
                label="리밸런싱 가능 현금",
                value=evaluation.available_for_rebalance_krw,
                unit="KRW",
                evidence_id=evidence_id,
                basis="확정 현금분배 중 입력한 리밸런싱 기간에 지급되는 금액",
            ),
            NumericEvidence(
                label="교육용 재투자 수량",
                value=evaluation.reinvested_quantity,
                unit="shares",
                evidence_id=evidence_id,
                basis="입력 기준가로 계산한 정수 단위 재투자 수량",
            ),
            NumericEvidence(
                label="재투자 후 잔여 현금",
                value=evaluation.remaining_cash_krw,
                unit="KRW",
                evidence_id=evidence_id,
                basis="정수 단위 재투자 뒤 남는 현금",
            ),
        ],
        limitations=evaluation.limitations,
    )


def _reinvestment_status(event: Mapping[str, object]) -> DistributionStatus | None:
    if event.get("event_type") == "cash_distribution" and event.get(
        "status"
    ) == "confirmed_cash_flow":
        return DistributionStatus.CONFIRMED_CASH_FLOW
    if event.get("event_type") == "scheduled_cash_distribution":
        return DistributionStatus.REFERENCE_ONLY
    return None


def _unavailable_response() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.ETF_DISTRIBUTION,
        answer="ETF 분배금 이벤트 데이터가 아직 준비되지 않았어요.",
        data_mode="official_distribution_event_unavailable",
        limitations=[
            "공식 이벤트 마스터가 적재된 뒤에만 종목별 분배금·지급일을 안내합니다.",
            "자동 재투자나 주문은 실행하지 않습니다.",
        ],
    )


def _event_source(
    event: Mapping[str, object], evidence_id: str, as_of: str
) -> SourceEvidence:
    evidence = event.get("source_evidence")
    item = evidence[0] if isinstance(evidence, list) and evidence else {}
    item = item if isinstance(item, Mapping) else {}
    source_type = str(item.get("source_type", "official_event_master"))
    locator = next(
        (
            str(item[key])
            for key in ("source_url", "endpoint", "receipt_number")
            if item.get(key)
        ),
        "ETF distribution event master",
    )
    return SourceEvidence(
        evidence_id=evidence_id,
        label=_source_label(source_type),
        locator=locator,
        data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
        publisher=_source_publisher(source_type),
        as_of=as_of,
    )


def _master_source(as_of: str) -> SourceEvidence:
    return SourceEvidence(
        evidence_id="distribution-event-master",
        label="ETF 공식 분배 이벤트 마스터",
        locator="ETF distribution event master",
        data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
        as_of=as_of,
    )


def _event_status(status: str) -> str:
    return {
        "confirmed_cash_flow": "확정 현금분배",
        "excluded_from_historical_total_return": "예정 일정(참고용)",
    }.get(status, "공식 이벤트")


def _source_label(source_type: str) -> str:
    if "kind" in source_type.lower():
        return "KIND ETF 현금분배 공시"
    if "kis" in source_type.lower() or "ksd" in source_type.lower():
        return "한국투자증권 KSD 배당 일정"
    return "ETF 공식 분배 이벤트"


def _source_publisher(source_type: str) -> str | None:
    if "kind" in source_type.lower():
        return "한국거래소 KIND"
    if "kis" in source_type.lower() or "ksd" in source_type.lower():
        return "한국투자증권"
    return None


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")
