from dataclasses import dataclass
from enum import StrEnum

from ..engine import AccountType
from .models import ChatRequest

SCENARIO_KEYWORDS = {
    "방치": "dc_dormant",
    "세액공제": "tax_contribution_uninvested",
    "미운용": "tax_contribution_uninvested",
    "중복": "overlap_risk_concentration",
    "편중": "overlap_risk_concentration",
}
DISCLOSURE_TERMS = ("수익률", "수수료", "적립금", "사업자", "회사")
ACCOUNT_RULE_TERMS = ("dc", "irp", "연금저축", "연금", "위험자산", "tdf")
SCENARIO_TERMS = ("내 계좌", "목계좌", "포트폴리오 진단")
CONTEXTUAL_FOLLOW_UP_TERMS = ("그럼", "그것", "해당", "이 경우", "그 계좌")


class RouteKind(StrEnum):
    ACCOUNT_RULE = "account_rule"
    CUSTOM_PORTFOLIO = "custom_portfolio"
    PROVIDER_DISCLOSURE = "provider_disclosure"
    NEWS = "news"
    SCENARIO = "scenario"
    SCENARIO_SELECTION = "scenario_selection"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True, slots=True)
class ChatRoute:
    kind: RouteKind
    scenario_code: str | None = None
    account_type: AccountType | None = None


class IntentRouter:
    """Classify only the current user turn; context fills in omitted account names."""

    def route(self, request: ChatRequest) -> ChatRoute:
        message = request.message
        lower = message.lower()
        account_type = self.account_type(message)

        if request.portfolio is not None:
            return ChatRoute(RouteKind.CUSTOM_PORTFOLIO, account_type=account_type)
        if "뉴스" in message or "소식" in message:
            return ChatRoute(RouteKind.NEWS, account_type=account_type)
        if account_type is not None and any(
            term in message for term in DISCLOSURE_TERMS
        ):
            return ChatRoute(RouteKind.PROVIDER_DISCLOSURE, account_type=account_type)
        if account_type is None and self._is_contextual_follow_up(message):
            account_type = (
                request.conversation_context.account_type
                if request.conversation_context
                else None
            )
            if account_type is not None and any(
                term in message for term in DISCLOSURE_TERMS
            ):
                return ChatRoute(
                    RouteKind.PROVIDER_DISCLOSURE, account_type=account_type
                )
        if any(term in lower for term in ACCOUNT_RULE_TERMS):
            return ChatRoute(RouteKind.ACCOUNT_RULE, account_type=account_type)
        scenario_code = self.scenario_code(message)
        if scenario_code is not None:
            return ChatRoute(RouteKind.SCENARIO, scenario_code=scenario_code)
        if self._looks_like_scenario(message):
            if request.scenario_code:
                return ChatRoute(
                    RouteKind.SCENARIO, scenario_code=request.scenario_code
                )
            return ChatRoute(RouteKind.SCENARIO_SELECTION)
        return ChatRoute(RouteKind.OUT_OF_SCOPE, account_type=account_type)

    @staticmethod
    def scenario_code(message: str) -> str | None:
        return next(
            (code for keyword, code in SCENARIO_KEYWORDS.items() if keyword in message),
            None,
        )

    @staticmethod
    def account_type(message: str) -> AccountType | None:
        lower = message.lower()
        if "연금저축" in message:
            return AccountType.PENSION_SAVINGS
        if "irp" in lower:
            return AccountType.IRP
        if "dc" in lower:
            return AccountType.DC
        return None

    @staticmethod
    def _looks_like_scenario(message: str) -> bool:
        return any(term in message for term in SCENARIO_TERMS)

    @staticmethod
    def _is_contextual_follow_up(message: str) -> bool:
        return any(term in message for term in CONTEXTUAL_FOLLOW_UP_TERMS)
