"""Deterministic starting guide for users who do not know what to ask.

타깃은 "무엇을 모르는지도 모르는" 입문자다. "뭐부터 해야 할지 모르겠어"는
이들의 첫 질문이 될 가능성이 높은데, 어떤 기능으로도 분류되지 않아
차단됐다. 여기서는 계산기 튜토리얼과 추천 질문을 함께 제시하고 사용자가
직접 고르게 한다. 특정 상품이나 금액을 권유하지 않는다.
"""

from ..models import ChatIntent, ChatResponse, SuggestedFollowUp

GETTING_STARTED_DATA_MODE = "getting_started_guide"


def getting_started_response() -> ChatResponse:
    """Offer both the planner tutorial and starter questions without ranking them."""

    return ChatResponse(
        intent=ChatIntent.GETTING_STARTED,
        answer=(
            "처음이라 막막한 게 당연해요. 두 가지 중에 편한 쪽으로 "
            "시작해 봐요.\n\n"
            "첫째, 연금계산기로 지금 상황을 숫자로 먼저 볼 수 있어요. "
            "얼마를 넣으면 나중에 어떻게 되는지 직접 움직여 보는 방법이에요.\n\n"
            "둘째, 아래 질문 중에 궁금한 걸 눌러도 돼요. 계좌가 어떻게 "
            "다른지부터 보면 나머지가 훨씬 쉬워져요."
        ),
        data_mode=GETTING_STARTED_DATA_MODE,
        suggested_follow_ups=[
            SuggestedFollowUp(
                follow_up_id="open_pension_planner",
                label="연금계산기 열어보기",
                message="연금계산기를 열어줘",
            ),
            SuggestedFollowUp(
                follow_up_id="fallback_account_diff",
                label="계좌별 차이 보기",
                message="DC형, IRP, 연금저축은 뭐가 달라?",
            ),
            SuggestedFollowUp(
                follow_up_id="fallback_tax_credit",
                label="세액공제 알아보기",
                message="올해 받을 수 있는 연금세액공제가 궁금해.",
            ),
            SuggestedFollowUp(
                follow_up_id="fallback_educational_portfolio",
                label="내 상황에 맞는 전략 보기",
                message="내 상황에 맞는 연금저축전략을 알려줘.",
            ),
        ],
        limitations=[
            "시작을 돕는 안내이고, 특정 상품이나 납입 금액을 권유하지 않아요."
        ],
    )
