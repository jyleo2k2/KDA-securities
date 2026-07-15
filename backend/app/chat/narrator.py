import json
import re
from decimal import Decimal, InvalidOperation

import anthropic
from anthropic.types import Message as AnthropicMessage

from .models import ChatIntent, ChatResponse

NARRATABLE_INTENTS = {
    ChatIntent.ACCOUNT_RULE,
    ChatIntent.MOCK_PORTFOLIO,
    ChatIntent.PROVIDER_DISCLOSURE,
    ChatIntent.NEWS,
}

# 재서술 본문과 검토 노트를 분리해 받는 구조화 출력 계약.
NARRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "narration": {
            "type": "string",
            "description": "검증 답변을 쉬운 한국어 한 문단으로 다시 쓴 본문",
        },
        "review_note": {
            "type": "string",
            "description": (
                "검증 답변을 어떻게 검토·재서술했는지 1~2문장 설명 "
                "(원문에 없는 숫자 금지)"
            ),
        },
    },
    "required": ["narration", "review_note"],
    "additionalProperties": False,
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
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        self._model = model.strip()
        self._client = client or anthropic.Anthropic(api_key=api_key.strip())

    def narrate(self, response: ChatResponse) -> ChatResponse:
        if response.intent not in NARRATABLE_INTENTS or not response.sources:
            return response
        try:
            message = self._client.messages.create(
                model=self._model,
                # thinking과 검토 노트가 출력 토큰을 함께 소모하므로 여유를 둔다.
                max_tokens=1500,
                # 모델이 실제로 생각한 경우 그 요약을 검토 과정으로 우선 노출한다.
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={
                    "format": {"type": "json_schema", "schema": NARRATION_SCHEMA}
                },
                system=(
                    "당신은 연금 코파일럿의 설명 전용 내레이터다. 계산하거나 새로운 "
                    "수치·상품·전망·매매의견을 만들지 않는다. 제공된 검증 답변의 "
                    "사실만 쉬운 한국어로 한 문단에 다시 쓴다. 사실·외부 의견·서비스 "
                    "해석의 경계를 유지하고 숫자와 단위는 원문 그대로 둔다. "
                    "review_note에는 무엇을 검토해 어떻게 풀어썼는지 1~2문장으로 "
                    "적는다."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "검증 답변:\n"
                            f"{response.answer}\n\n"
                            "제한사항:\n" + "\n".join(response.limitations)
                        ),
                    }
                ],
            )
            candidate, review_note = self._extract_output(message)
        except (anthropic.APIError, ValueError):
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
                "narration_reasoning": self._safe_reasoning(
                    message, review_note, allowed_numbers
                ),
            }
        )
        return ChatResponse.model_validate(data)

    @staticmethod
    def _extract_output(message: AnthropicMessage) -> tuple[str, str]:
        """Parse the structured narration payload from the first text block."""
        text = next(
            (
                block.text
                for block in message.content
                if block.type == "text" and block.text
            ),
            None,
        )
        if not text:
            raise ValueError("Claude returned no narration text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("Claude narration is not valid JSON") from error
        narration = str(payload.get("narration", "")).strip()
        review_note = str(payload.get("review_note", "")).strip()
        if not narration or len(narration) > 2000:
            raise ValueError("Claude returned an invalid narration")
        return narration, review_note

    @staticmethod
    def _safe_reasoning(
        message: AnthropicMessage,
        review_note: str,
        allowed_numbers: set[Decimal],
    ) -> str | None:
        """Pick the reasoning to expose: real thinking summary first, else note.

        본문과 달리 보조 설명이므로 새 숫자가 감지되면 이 필드만 조용히
        생략하고 답변 자체는 유지한다.
        """
        thinking = next(
            (
                block.thinking.strip()
                for block in message.content
                if block.type == "thinking" and block.thinking.strip()
            ),
            None,
        )
        reasoning = thinking or review_note
        if not reasoning or len(reasoning) > 2000:
            return None
        if not _number_tokens(reasoning).issubset(allowed_numbers):
            return None
        return reasoning

    @staticmethod
    def _fallback(response: ChatResponse, limitation: str) -> ChatResponse:
        data = response.model_dump()
        data["limitations"] = [*response.limitations, limitation]
        return ChatResponse.model_validate(data)
