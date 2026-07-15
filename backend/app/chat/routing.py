from ..engine import AccountType
from .models import ChatRequest

CONTEXTUAL_FOLLOW_UP_TERMS = ("그럼", "그러면", "해당", "이 경우", "그 계좌")


class IntentRouter:
    """Add only an omitted account name; the safety planner stays authoritative."""

    @classmethod
    def contextual_message(cls, request: ChatRequest) -> str:
        if cls.account_type(request.message) is not None:
            return request.message
        context = request.conversation_context
        if (
            context is None
            or context.account_type is None
            or not cls._is_contextual_follow_up(request.message)
        ):
            return request.message
        return f"{context.account_type.value.upper()} {request.message}"

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
    def _is_contextual_follow_up(message: str) -> bool:
        return any(term in message for term in CONTEXTUAL_FOLLOW_UP_TERMS)
