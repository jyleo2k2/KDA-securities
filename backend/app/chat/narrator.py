"""Claude narrator on pydantic-ai (아키텍처.md §10 오케스트레이션 프레임워크).

향후 챗봇 도구(뉴스검색·포트폴리오 계산 등)를 같은 Agent에 등록해 확장한다.
숫자 가드·결정론 폴백은 프레임워크 밖에서 유지한다(Explainable by Design).
"""

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ModelResponse, ThinkingPart
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

from .models import ChatIntent, ChatResponse

NARRATABLE_INTENTS = {
    ChatIntent.ACCOUNT_RULE,
    ChatIntent.MOCK_PORTFOLIO,
    ChatIntent.PROVIDER_DISCLOSURE,
    ChatIntent.NEWS,
}

SYSTEM_PROMPT = (
    "당신은 연금 코파일럿의 설명 전용 내레이터다. 계산하거나 새로운 "
    "수치·상품·전망·매매의견을 만들지 않는다. 제공된 검증 답변의 "
    "사실만 쉬운 한국어로 한 문단에 다시 쓴다. 사실·외부 의견·서비스 "
    "해석의 경계를 유지하고 숫자와 단위는 원문 그대로 둔다."
)


class NarrationOutput(BaseModel):
    """구조화 출력 계약: 재서술 본문과 검토 노트를 분리해 받는다."""

    narration: str = Field(
        description="검증 답변을 쉬운 한국어 한 문단으로 다시 쓴 본문"
    )
    review_note: str = Field(
        description=(
            "검증 답변을 어떻게 검토·재서술했는지 1~2문장 설명 "
            "(원문에 없는 숫자 금지)"
        )
    )


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

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        self._model = model.strip()
        self.agent: Agent[None, NarrationOutput] = Agent(
            AnthropicModel(
                self._model,
                provider=AnthropicProvider(api_key=api_key.strip()),
            ),
            output_type=NativeOutput(NarrationOutput),
            instructions=SYSTEM_PROMPT,
            model_settings=AnthropicModelSettings(
                # thinking과 검토 노트가 출력 토큰을 함께 소모하므로 여유를 둔다.
                max_tokens=1500,
                # 모델이 실제로 생각한 경우 요약을 검토 과정으로 우선 노출한다.
                anthropic_thinking={"type": "adaptive", "display": "summarized"},
            ),
        )

    def narrate(self, response: ChatResponse) -> ChatResponse:
        if response.intent not in NARRATABLE_INTENTS or not response.sources:
            return response
        prompt = (
            "검증 답변:\n"
            f"{response.answer}\n\n"
            "제한사항:\n" + "\n".join(response.limitations)
        )
        try:
            result = self.agent.run_sync(prompt)
            output = result.output
            candidate = output.narration.strip()
            if not candidate or len(candidate) > 2000:
                raise ValueError("Claude returned an invalid narration")
        except (AgentRunError, ValueError):
            return self._fallback(
                response,
                "Claude 설명 호출 실패로 검증 원문을 표시합니다.",
            )

        allowed_numbers = _number_tokens(response.answer)
        if not _number_tokens(candidate).issubset(allowed_numbers):
            return self._fallback(
                response,
                "Claude 설명에서 새로운 숫자를 감지해 검증 원문으로 되돌렸습니다.",
            )
        thinking = next(
            (
                part.content.strip()
                for message in result.all_messages()
                if isinstance(message, ModelResponse)
                for part in message.parts
                if isinstance(part, ThinkingPart) and part.content.strip()
            ),
            None,
        )
        data = response.model_dump()
        data.update(
            {
                "answer": candidate,
                "narration_mode": "claude_verified",
                "model_name": self._model,
                "narration_reasoning": self._safe_reasoning(
                    thinking or output.review_note.strip(), allowed_numbers
                ),
            }
        )
        return ChatResponse.model_validate(data)

    @staticmethod
    def _safe_reasoning(
        reasoning: str, allowed_numbers: set[Decimal]
    ) -> str | None:
        """본문과 달리 보조 설명은 새 숫자 감지 시 이 필드만 조용히 생략한다."""
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
