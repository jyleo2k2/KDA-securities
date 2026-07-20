"""Card follow-up response finalization."""

from ..cards import build_suggested_follow_ups
from ..models import ChatResponse


def with_suggested_follow_ups(response: ChatResponse) -> ChatResponse:
    return response.model_copy(
        update={"suggested_follow_ups": build_suggested_follow_ups(response)}
    )
