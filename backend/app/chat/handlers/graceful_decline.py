"""Deterministic alternatives for supported-but-declined chat requests."""

from dataclasses import dataclass
from enum import StrEnum

from ..models import ChatIntent, ChatResponse, SuggestedFollowUp


class GracefulDeclineKind(StrEnum):
    STOCK_NEWS = "stock_news"
    FOREIGN_MARKET_OR_INDIVIDUAL_STOCK = "foreign_market_or_individual_stock"
    PREDICTION_OR_ORDER = "prediction_or_order"
    CONTRIBUTION_AMOUNT_ADVICE = "contribution_amount_advice"
    FEE_TARGET_REQUIRED = "fee_target_required"
    PROVIDER_CHOICE_ADVICE = "provider_choice_advice"
    PERSONAL_ALLOCATION_ADVICE = "personal_allocation_advice"
    PRINCIPAL_GUARANTEE_QUESTION = "principal_guarantee_question"


@dataclass(frozen=True)
class GracefulDecline:
    answer: str
    suggested_follow_ups: list[SuggestedFollowUp]
    limitations: list[str]


def graceful_decline(
    kind: GracefulDeclineKind,
    user_message: str,
) -> GracefulDecline:
    """Return fixed alternatives without invoking an LLM."""

    if kind is GracefulDeclineKind.STOCK_NEWS:
        return GracefulDecline(
            answer=(
                "개별 종목 뉴스는 안내하지 않아요. 대신 시장 뉴스나 이 종목과 "
                "관련된 ETF 테마 정보는 어떠세요?"
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="decline_market_news",
                    label="한국·미국 증시 뉴스 보기",
                    message="한국 증시 뉴스 보여줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="decline_stock_related_etf_theme",
                    label="관련 ETF 테마 보기",
                    message="반도체 테마 ETF를 보여줘",
                ),
            ],
            limitations=[
                "개별 종목 뉴스와 개별 ETF 프로필은 제공하지 않아요."
            ],
        )

    if kind is GracefulDeclineKind.FOREIGN_MARKET_OR_INDIVIDUAL_STOCK:
        return GracefulDecline(
            answer=(
                "연금계좌에서는 개별주식을 직접 담을 수 없고, 해외 개별 시장 "
                "데이터도 다루지 않아요. 대신 이런 걸 도와드릴 수 있어요:"
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="decline_market_etf_theme",
                    label="한국·미국 증시 ETF 테마 보기",
                    message="반도체 테마 ETF를 보여줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="decline_account_rules",
                    label="내 계좌 규칙 알아보기",
                    message="IRP 위험자산 한도를 알려줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="decline_profile_portfolio",
                    label="성향별 포트폴리오 비교",
                    message="투자성향별 연금 운용 가이드를 비교해줘",
                ),
            ],
            limitations=[
                "개별주식 직접 편입과 한국·미국 외 시장 데이터는 지원하지 않아요."
            ],
        )

    if kind is GracefulDeclineKind.PREDICTION_OR_ORDER:
        return GracefulDecline(
            answer=(
                "미래 수익 예측이나 매수·매도 추천은 규정상 해드릴 수 없어요. "
                "대신 이런 사실 정보는 어때요?"
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="decline_historical_disclosure",
                    label="과거 실적 공시 보기",
                    message="IRP 사업자 과거 수익률 공시를 알려줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="decline_educational_portfolio",
                    label="포트폴리오 예시",
                    message="연금저축 포트폴리오 예시를 보여줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="decline_etf_total_return",
                    label="ETF 과거 총수익률 보기",
                    message="반도체 테마 ETF의 과거 총수익률을 보여줘",
                ),
            ],
            limitations=[
                "미래 수익 예측, 상품 추천, 매수·매도 주문은 지원하지 않아요.",
                "과거 실적은 미래 수익을 보장하지 않아요.",
            ],
        )

    if kind is GracefulDeclineKind.CONTRIBUTION_AMOUNT_ADVICE:
        # 적정 납입액은 소득·지출에 따라 달라 정답을 정할 수 없다. 대신
        # 세액공제 한도라는 공식 기준점을 주고 계산기로 넘긴다.
        return GracefulDecline(
            answer=(
                "얼마가 알맞은지는 소득과 생활비에 따라 달라서 금액을 "
                "정해드리지는 않아요. 대신 기준점으로 삼을 만한 건 "
                "세액공제 납입 한도예요. 공식 근거의 한도 금액을 먼저 "
                "확인하고, 그 안에서 형편에 맞춰 정하는 분이 많아요."
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="advice_tax_credit_limit",
                    label="세액공제 한도 알아보기",
                    message="연금계좌 세액공제 납입 한도를 알려줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_pension_planner",
                    label="연금 계산기로 확인하기",
                    message="연금 계산기로 예상 수령액을 계산해줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_contribution_flexibility",
                    label="납입을 쉬어도 되는지 보기",
                    message="연금저축 납입을 한 달 쉬어도 되나요?",
                ),
            ],
            limitations=[
                "적정 납입액은 개인의 소득·지출에 따라 달라 특정 금액을 "
                "권유하지 않아요.",
            ],
        )

    if kind is GracefulDeclineKind.FEE_TARGET_REQUIRED:
        return GracefulDecline(
            answer=(
                "어떤 비용이 궁금하세요? 연금계좌의 금융회사 수수료인지, "
                "보유 상품의 총보수인지 알려주시면 확인해 드릴게요."
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="fee_total_expense_ratio",
                    label="ETF 총보수 알아보기",
                    message="총보수가 뭐야?",
                ),
                SuggestedFollowUp(
                    follow_up_id="fee_pension_account_comparison",
                    label="연금계좌 수수료 비교 기준",
                    message="연금계좌 수수료를 비교할 때 무엇을 봐야 해?",
                ),
                SuggestedFollowUp(
                    follow_up_id="fee_long_term_impact",
                    label="수수료의 장기 영향",
                    message="수수료가 왜 중요해?",
                ),
            ],
            limitations=[
                "구체적인 수수료와 총보수는 금융회사·상품별 공식 공시를 "
                "확인해야 해요."
            ],
        )

    if kind is GracefulDeclineKind.PROVIDER_CHOICE_ADVICE:
        # 특정 금융회사를 권유하지 않는다. 대신 비교 기준과 공시 데이터로 넘긴다.
        return GracefulDecline(
            answer=(
                "어느 회사가 더 낫다고 말씀드리지는 않아요. 대신 비교하는 "
                "기준은 알려드릴 수 있어요. 담을 수 있는 상품의 범위, "
                "수수료, 그리고 과거 운용 실적 공시를 함께 보는 것이 "
                "일반적이에요."
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="advice_provider_disclosure",
                    label="사업자 공시 비교 기준 보기",
                    message="IRP 사업자 과거 수익률 공시를 알려줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_account_investable",
                    label="계좌별 담을 수 있는 상품 보기",
                    message="연금계좌에 어떤 상품을 담을 수 있어?",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_account_overview",
                    label="세 계좌 차이 비교하기",
                    message="DC형, IRP, 연금저축은 뭐가 달라?",
                ),
            ],
            limitations=[
                "특정 금융회사를 권유하지 않아요. 공시는 과거 실적이며 "
                "미래 수익을 보장하지 않아요.",
            ],
        )

    if kind is GracefulDeclineKind.PERSONAL_ALLOCATION_ADVICE:
        # "나 어떻게 투자해야 해?"는 조건이 있어야 답할 수 있다. 상품을
        # 고르는 대신 어떤 정보가 더 필요한지 되물어 다음 단계로 잇는다.
        return GracefulDecline(
            answer=(
                "어떤 게 맞을지는 나이와 투자성향, 그리고 어떤 계좌를 "
                "쓰는지에 따라 달라져요. 무엇을 사라고 정해드리지는 "
                "않지만, 조건을 알려주시면 성향별로 어떻게 나눠 담는지 "
                "비교해서 보여드릴 수 있어요."
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="advice_profile_guide",
                    label="투자성향별로 비교하기",
                    message="투자성향별 연금 운용 가이드를 비교해줘",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_age_allocation",
                    label="나이대로 알아보기",
                    message="35살인데 어떻게 배분해?",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_why_diversify",
                    label="왜 나눠 담는지 보기",
                    message="분산투자를 왜 해야 해?",
                ),
            ],
            limitations=[
                "개인에게 맞는 특정 상품을 골라 드리지 않아요. 실제 상품 "
                "선택과 주문은 고객님이 하세요.",
            ],
        )

    if kind is GracefulDeclineKind.PRINCIPAL_GUARANTEE_QUESTION:
        # 원금 보장·손실 회피 질문. 안심시키는 대신 제도 사실로 답을 돌린다.
        return GracefulDecline(
            answer=(
                "손실이 나지 않는 방법을 알려드릴 수는 없어요. 다만 "
                "연금계좌의 원리금보장상품과 실적배당상품이 어떻게 다른지는 "
                "공식 기준으로 설명해 드릴 수 있어요. 예금자보호가 어디까지 "
                "적용되는지도 함께 확인하실 수 있어요."
            ),
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="advice_principal_guaranteed",
                    label="원리금보장상품이란",
                    message="원리금보장상품이 뭐야?",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_volatility",
                    label="변동성이란",
                    message="변동성이 뭐야?",
                ),
                SuggestedFollowUp(
                    follow_up_id="advice_risk_return",
                    label="위험과 수익의 관계 보기",
                    message="위험을 줄이면 수익도 줄어?",
                ),
            ],
            limitations=[
                "원금 보장이나 손실 회피를 약속하지 않아요.",
                "상품별 보호 여부는 가입 금융회사의 공식 안내를 확인해야 해요.",
            ],
        )

    raise ValueError(f"unsupported graceful decline kind: {kind}")


def graceful_decline_response(
    kind: GracefulDeclineKind,
    user_message: str,
) -> ChatResponse:
    """Build an out-of-scope response from a deterministic decline."""

    decline = graceful_decline(kind, user_message)
    return ChatResponse(
        intent=ChatIntent.OUT_OF_SCOPE,
        answer=decline.answer,
        data_mode="blocked",
        suggested_follow_ups=decline.suggested_follow_ups,
        limitations=decline.limitations,
    )
