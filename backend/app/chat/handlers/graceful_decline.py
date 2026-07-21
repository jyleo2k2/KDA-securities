"""Deterministic alternatives for supported-but-declined chat requests."""

from dataclasses import dataclass
from enum import StrEnum

from ..models import ChatIntent, ChatResponse, SuggestedFollowUp


class GracefulDeclineKind(StrEnum):
    STOCK_NEWS = "stock_news"
    FOREIGN_MARKET_OR_INDIVIDUAL_STOCK = "foreign_market_or_individual_stock"
    PREDICTION_OR_ORDER = "prediction_or_order"


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
                    label="교육용 포트폴리오 예시",
                    message="연금저축 교육용 포트폴리오 예시를 보여줘",
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
