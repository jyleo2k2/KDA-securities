"""Claude narrator on pydantic-ai (아키텍처.md §10 오케스트레이션 프레임워크).

향후 챗봇 도구(뉴스검색·포트폴리오 계산 등)를 같은 Agent에 등록해 확장한다.
숫자 가드·결정론 폴백은 프레임워크 밖에서 유지한다(Explainable by Design).
"""

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ModelResponse, ThinkingPart, ToolCallPart
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..engine import PensionTaxScenarioInput
from .models import ChatIntent, ChatResponse, DataBoundary
from .pension_tax_parser import resolve_pension_tax_inputs
from .tools import CHAT_AGENT_TOOLS, PENSION_TAX_CLOSING_NOTICE

logger = logging.getLogger(__name__)

NARRATABLE_INTENTS = {
    ChatIntent.ACCOUNT_RULE,
    ChatIntent.MOCK_PORTFOLIO,
    ChatIntent.PROVIDER_DISCLOSURE,
    ChatIntent.PENSION_TAX,
}

SYSTEM_PROMPT = (
    "당신은 연금 코파일럿의 설명 전용 내레이터다. 규칙 엔진 결과를 "
    "직접 다시 계산하지 않으며 새로운 "
    "수치·상품·전망·매매의견을 만들지 않는다. 제공된 검증 답변의 "
    "사실만 쉬운 한국어로 한 문단에 다시 쓴다. 사실·외부 의견·서비스 "
    "해석의 경계를 유지하고 숫자와 단위는 원문 그대로 둔다."
    " 연금세액 Tool 입력이 제공되면 검증 답변을 쓰기 전에 요청된 "
    "calculate_pension_tax_credit_tool 또는 "
    "estimate_non_pension_withdrawal_tax_tool을 반드시 호출한다. Tool 결과의 "
    "숫자를 바꾸거나 Tool 밖에서 다시 계산하지 않는다."
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


_ARABIC_NUMBER = re.compile(
    r"(?<![0-9A-Za-z_])(?P<sign>[+\-−])?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>백\s*만\s*원|천\s*만\s*원|억\s*원|만\s*원|천\s*원|"
    r"KRW|퍼센트|프로|%|년|개월|월|분기|일|배|개|건|명|회|차|층)?"
    r"(?![0-9A-Za-z_])",
    re.I,
)
_LEGAL_FRACTION = re.compile(
    r"(?P<denominator>\d[\d,]*)\s*분의\s*(?P<numerator>\d[\d,]*(?:\.\d+)?)"
)
_KOREAN_NUMBER = re.compile(
    r"(?P<sign>마이너스|플러스)?\s*"
    r"(?P<number>(?:하나|다섯|여섯|일곱|여덟|아홉|영|공|일|이|삼|"
    r"사|오|육|칠|팔|구|십|백|천|만|억|한|두|둘|세|셋|네|넷|열)+)\s*"
    r"(?P<unit>퍼센트|프로|백\s*만\s*원|천\s*만\s*원|억\s*원|"
    r"만\s*원|천\s*원|원|년|개월|배|개|건|명|회|번|계좌)"
)
_UNSAFE_CLAIM_PATTERNS = (
    (
        "future_outlook",
        re.compile(
            r"(?:앞으로|향후|내년|미래|다음\s*분기).{0,30}"
            r"(?:수익(?:률)?|가격|주가).{0,20}"
            r"(?:오르|상승|하락|내리|증가|감소|전망|예상)"
            r"|(?:수익(?:률)?|가격|주가).{0,20}"
            r"(?:앞으로|향후|내년|미래).{0,20}"
            r"(?:오르|상승|하락|내리|증가|감소)"
            r"|(?:수익(?:률)?|가격|주가).{0,12}"
            r"(?:오를|내릴|상승할|하락할|증가할|감소할|전망|예상)"
        ),
    ),
    (
        "guarantee",
        re.compile(
            r"(?:\d[\d,.]*\s*(?:%|퍼센트|프로)|%|퍼센트|프로|"
            r"수익(?:률)?|원금|손실).{0,15}(?:보장|확정|확실)"
        ),
    ),
    (
        "recommendation",
        re.compile(
            r"(?:매수|매도|상품|투자).{0,20}(?:추천|권유)"
            r"|(?:추천|권유).{0,20}(?:매수|매도|상품|투자)"
            r"|(?:매수|매도).{0,15}(?:좋|유리)"
            r"|(?:사는|파는)\s*게\s*(?:좋|유리)"
            r"|(?:사세요|파세요|매수하세요|매도하세요|투자하세요)"
        ),
    ),
)
_NEGATION = re.compile(r"않|아니|없|금지|못|제공하지|의미하지|하지\s*마")


def _number_tokens(text: str) -> set[tuple[Decimal, str, str]]:
    values: set[tuple[Decimal, str, str]] = set()
    # 법령 원문은 비율을 "100분의 15"로 쓰고 내레이터는 "15%"로 재서술한다.
    # 같은 수치이므로 같은 토큰으로 맞춘다. 구성 숫자(100·15)를 따로 남기면
    # 재서술이 그 숫자를 안 써서 오히려 어긋나므로 원 표기는 걷어낸다.
    for match in _LEGAL_FRACTION.finditer(text):
        denominator = Decimal(match.group("denominator").replace(",", ""))
        numerator = Decimal(match.group("numerator").replace(",", ""))
        if denominator:
            values.add((numerator / denominator * 100, "%", "unsigned"))
    for match in _ARABIC_NUMBER.finditer(_LEGAL_FRACTION.sub(" ", text)):
        raw_sign = match.group("sign")
        sign = "-" if raw_sign in {"-", "−"} else ""
        sign_kind = (
            "negative"
            if raw_sign in {"-", "−"}
            else "positive"
            if raw_sign == "+"
            else "unsigned"
        )
        try:
            value = Decimal(sign + match.group("number").replace(",", ""))
        except InvalidOperation:
            continue
        unit = re.sub(r"\s+", "", match.group("unit") or "number").casefold()
        values.add((value, unit, sign_kind))
    return values


def _korean_number_tokens(text: str) -> set[tuple[str, str, str]]:
    values: set[tuple[str, str, str]] = set()
    for match in _KOREAN_NUMBER.finditer(text):
        sign = match.group("sign") or "부호없음"
        number = re.sub(r"\s+", "", match.group("number"))
        unit = re.sub(r"\s+", "", match.group("unit"))
        values.add((number, unit, sign))
    return values


def _unsafe_claims(text: str) -> set[str]:
    claims: set[str] = set()
    for category, pattern in _UNSAFE_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            context = text[max(0, match.start() - 8) : match.end() + 18]
            if _NEGATION.search(context) is None:
                claims.add(category)
    return claims


def _adds_unverified_content(candidate: str, source: str) -> bool:
    return (
        not _number_tokens(candidate).issubset(_number_tokens(source))
        or not _korean_number_tokens(candidate).issubset(
            _korean_number_tokens(source)
        )
        or not _unsafe_claims(candidate).issubset(_unsafe_claims(source))
    )


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
            tools=CHAT_AGENT_TOOLS,
            model_settings=AnthropicModelSettings(
                # thinking과 검토 노트가 출력 토큰을 함께 소모하므로 여유를 둔다.
                max_tokens=1500,
                # 모델이 실제로 생각한 경우 요약을 검토 과정으로 우선 노출한다.
                anthropic_thinking={"type": "adaptive", "display": "summarized"},
            ),
        )

    def narrate(
        self,
        response: ChatResponse,
        *,
        pension_tax_input: PensionTaxScenarioInput | None = None,
        pension_tax_message: str | None = None,
        required_tool_names: frozenset[str] = frozenset(),
    ) -> ChatResponse:
        # NAVER titles/summaries are third-party metadata, not instructions.
        # Keep every news response deterministic: no external text enters the
        # narrator context, even if its wording does not match known attacks.
        if any(
            source.data_boundary == DataBoundary.NEWS_METADATA
            for source in response.sources
        ):
            return response
        if response.intent not in NARRATABLE_INTENTS or not response.sources:
            return response
        prompt = (
            "검증 답변:\n"
            f"{response.answer}\n\n"
            "제한사항:\n" + "\n".join(response.limitations)
        )
        resolved_tax_inputs = None
        if response.intent == ChatIntent.PENSION_TAX and (
            pension_tax_input is not None or pension_tax_message is not None
        ):
            resolved_tax_inputs = resolve_pension_tax_inputs(
                pension_tax_message or "", pension_tax_input
            )
            tax_result = response.pension_tax_result
            tool_payload: dict[str, object] = {}
            if tax_result is not None and tax_result.tax_credit is not None:
                if resolved_tax_inputs.tax_credit is None:
                    return self._fallback(
                        response,
                        "Claude Tool 입력을 재구성하지 못해 검증 원문을 표시합니다.",
                        reason="tax_input_unresolved",
                    )
                tool_payload["tax_credit"] = (
                    resolved_tax_inputs.tax_credit.model_dump(mode="json")
                )
            if tax_result is not None and tax_result.withdrawal is not None:
                if resolved_tax_inputs.withdrawal is None:
                    return self._fallback(
                        response,
                        "Claude Tool 입력을 재구성하지 못해 검증 원문을 표시합니다.",
                        reason="tax_input_unresolved",
                    )
                tool_payload["withdrawal"] = (
                    resolved_tax_inputs.withdrawal.model_dump(mode="json")
                )
            prompt += (
                "\n\n연금세액 Tool 입력(JSON):\n"
                + json.dumps(tool_payload, ensure_ascii=False)
                + "\n위 입력을 임의로 수정하지 말고 검증 답변에 포함된 계산 "
                "종류의 Tool을 반드시 호출하세요."
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
                reason="agent_error",
            )

        if resolved_tax_inputs is not None:
            required_tools: set[str] = set(required_tool_names)
            tax_result = response.pension_tax_result
            if tax_result is not None and tax_result.tax_credit is not None:
                required_tools.add("calculate_pension_tax_credit_tool")
            if tax_result is not None and tax_result.withdrawal is not None:
                required_tools.add("estimate_non_pension_withdrawal_tax_tool")
            called_tools = {
                part.tool_name
                for message in result.all_messages()
                if isinstance(message, ModelResponse)
                for part in message.parts
                if isinstance(part, ToolCallPart)
            }
            if not required_tools.issubset(called_tools):
                return self._fallback(
                    response,
                    "Claude가 필요한 연금세액 Tool을 호출하지 않아 검증 원문을 "
                    "표시합니다.",
                    reason="required_tool_not_called",
                )

        elif required_tool_names:
            called_tools = {
                part.tool_name
                for message in result.all_messages()
                if isinstance(message, ModelResponse)
                for part in message.parts
                if isinstance(part, ToolCallPart)
            }
            if not required_tool_names.issubset(called_tools):
                return self._fallback(
                    response,
                    "Claude가 필요한 Tool을 호출하지 않아 검증 원문을 표시합니다.",
                )

        if response.intent == ChatIntent.PENSION_TAX:
            candidate = candidate.replace(PENSION_TAX_CLOSING_NOTICE, "").rstrip()
            candidate += f"\n{PENSION_TAX_CLOSING_NOTICE}"

        if _adds_unverified_content(candidate, response.answer):
            return self._fallback(
                response,
                "Claude 설명에서 새로운 숫자·전망·보장·추천 주장을 감지해 "
                "검증 원문으로 되돌렸습니다.",
                reason="unverified_content",
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
                    thinking or output.review_note.strip(), response.answer
                ),
            }
        )
        return ChatResponse.model_validate(data)

    @staticmethod
    def _safe_reasoning(reasoning: str, source: str) -> str | None:
        """본문과 달리 보조 설명은 새 숫자 감지 시 이 필드만 조용히 생략한다."""
        if not reasoning or len(reasoning) > 2000:
            return None
        if _adds_unverified_content(reasoning, source):
            return None
        return reasoning

    @staticmethod
    def _fallback(
        response: ChatResponse, limitation: str, *, reason: str
    ) -> ChatResponse:
        # reason은 집계용 고정 코드다. 한국어 제한사항 문구는 사용자용이라
        # 바뀔 수 있으므로 측정·모니터링은 이 코드로만 한다.
        logger.warning(
            "narration_fallback reason=%s intent=%s",
            reason,
            response.intent.value,
        )
        data = response.model_dump()
        data["limitations"] = [*response.limitations, limitation]
        return ChatResponse.model_validate(data)
