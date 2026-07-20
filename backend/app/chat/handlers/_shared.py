"""Shared deterministic chat-response helpers."""

from ..models import ChatIntent, ChatResponse
from ..query_planner import BlockedReason

def blocked_response(reason: BlockedReason) -> ChatResponse:
    if reason == BlockedReason.SENSITIVE_INFORMATION:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "개인 식별정보나 인증정보가 포함된 질문은 처리하지 않아요. "
                "해당 값을 지운 뒤 제도나 운용 원리만 질문해 주세요."
            ),
            data_mode="blocked",
            limitations=[
                "입력 원문은 검색이나 AI 설명 단계로 전달하지 않았습니다."
            ],
        )
    if reason == BlockedReason.FUTURE_PREDICTION:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "미래 수익률 예측은 제공하지 않아요. 목표가나 수익 보장도 "
                "안내하지 않아요. 포트폴리오 입력이 있으면 규칙 엔진이 계산한 "
                "장기 계획가정과 과거 위험지표를 설명해 드려요."
            ),
            data_mode="blocked",
            limitations=[
                "LLM의 미래 수익 예측은 지원하지 않습니다.",
                "계획가정은 예측이나 보장 수익률이 아닙니다.",
            ],
        )
    if reason == BlockedReason.ORDER_REQUEST:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "상품 선택과 주문은 이용자가 직접 해야 해요. 금융회사 공식 "
                "채널을 이용해 주세요. 챗봇은 판단 기준과 근거만 설명해 드려요."
            ),
            data_mode="blocked",
            limitations=["주문·자동운용은 지원하지 않습니다."],
        )
    if reason == BlockedReason.PRODUCT_LEVEL_UNAVAILABLE:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "현재 데이터는 연금저축 회사와 퇴직연금 사업자 단위로 모여 "
                "있어요. 개별 상품 데이터가 아니어서 상품별 비교·추천은 "
                "제공하지 않아요."
            ),
            data_mode="unavailable",
            limitations=["검증된 개별 상품 식별자와 적격성 데이터가 필요합니다."],
        )
    if reason == BlockedReason.ACCOUNT_SELECTION_REQUIRED:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "공시 수치는 계좌 제도별 항목이 달라 한 번에 섞어 비교하지 "
                "않아요. DC형, IRP, 연금저축 중 하나를 지정해 주세요."
            ),
            data_mode="blocked",
            limitations=["계좌별 공시 계약을 분리해 조회합니다."],
        )
    return ChatResponse(
        intent=ChatIntent.OUT_OF_SCOPE,
        answer=(
            "연금계좌 규칙, 가상계좌 진단, 과거 공시와 뉴스 근거를 안내할 수 "
            "있어요. 질문에 계좌 유형이나 진단할 가상 시나리오를 적어 주세요."
        ),
        data_mode="safe_fallback",
        limitations=["범용 투자·세무·법률 상담은 지원하지 않습니다."],
    )
