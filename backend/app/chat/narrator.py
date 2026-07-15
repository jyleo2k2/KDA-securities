import re
from decimal import Decimal, InvalidOperation

import httpx

from .models import ChatIntent, ChatResponse

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
NARRATABLE_INTENTS = {
    ChatIntent.ACCOUNT_RULE,
    ChatIntent.MOCK_PORTFOLIO,
    ChatIntent.PROVIDER_DISCLOSURE,
    ChatIntent.NEWS,
}


def _number_tokens(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in re.findall(r"(?<![a-zA-Z])\d[\d,]*(?:\.\d+)?", text):
        try:
            values.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return values


class ClaudeNarrator:
    """Rephrase verified output; reject any response that invents a new number."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._client = client

    def narrate(self, response: ChatResponse) -> ChatResponse:
        if response.intent not in NARRATABLE_INTENTS or not response.sources:
            return response
        payload = {
            "model": self._model,
            "max_tokens": 500,
            "temperature": 0,
            "system": (
                "당신은 연금 코파일럿의 설명 전용 내레이터다. 계산하거나 새로운 "
                "수치·상품·전망·매매의견을 만들지 않는다. 제공된 검증 답변의 "
                "사실만 쉬운 한국어로 한 문단에 다시 쓴다. 사실·외부 의견·서비스 "
                "해석의 경계를 유지하고 숫자와 단위는 원문 그대로 둔다."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "검증 답변:\n"
                        f"{response.answer}\n\n"
                        "제한사항:\n" + "\n".join(response.limitations)
                    ),
                }
            ],
        }
        try:
            if self._client is not None:
                candidate = self._request(self._client, payload)
            else:
                with httpx.Client(timeout=20.0) as client:
                    candidate = self._request(client, payload)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return self._fallback(
                response,
                "Claude 설명 호출 실패로 검증 원문을 표시합니다.",
            )

        allowed_numbers = _number_tokens(response.answer)
        candidate_numbers = _number_tokens(candidate)
        if not candidate_numbers.issubset(allowed_numbers):
            return self._fallback(
                response,
                "Claude 설명에서 새로운 숫자를 감지해 검증 원문으로 되돌렸습니다.",
            )
        data = response.model_dump()
        data.update(
            {
                "answer": candidate,
                "narration_mode": "claude_verified",
                "model_name": self._model,
            }
        )
        return ChatResponse.model_validate(data)

    def _request(self, client: httpx.Client, payload: dict[str, object]) -> str:
        result = client.post(
            ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json=payload,
        )
        result.raise_for_status()
        body = result.json()
        text = next(
            item["text"]
            for item in body["content"]
            if item.get("type") == "text" and item.get("text")
        )
        candidate = str(text).strip()
        if not candidate or len(candidate) > 2000:
            raise ValueError("Claude returned an invalid narration")
        return candidate

    @staticmethod
    def _fallback(response: ChatResponse, limitation: str) -> ChatResponse:
        data = response.model_dump()
        data["limitations"] = [*response.limitations, limitation]
        return ChatResponse.model_validate(data)
