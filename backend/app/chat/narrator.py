"""Claude narrator on pydantic-ai (아키텍처.md §10 오케스트레이션 프레임워크).

향후 챗봇 도구(뉴스검색·포트폴리오 계산 등)를 같은 Agent에 등록해 확장한다.
숫자 가드·결정론 폴백은 프레임워크 밖에서 유지한다(Explainable by Design).
"""

import json
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from time import monotonic

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

# 엔진 답변이 결정론이므로 같은 프롬프트는 같은 검증 내레이션을 재사용한다.
NARRATION_CACHE_MAX_ENTRIES = 256
NARRATION_CACHE_VERSION = 1
NARRATION_CACHE_PERSIST_DEBOUNCE_SECONDS = 5.0
_NARRATION_CACHE_FILE_LOCK = threading.Lock()

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
    "사실만 쉬운 한국어 해요체 한 문단으로 다시 쓴다. 결론을 첫 문장에 "
    "말한다. 어려운 금융 용어가 나오면 새로운 사실·수치를 만들지 않는 "
    "범위에서 짧게 풀어서 쓴다. 금융을 잘 아는 따뜻한 친구처럼, "
    "질문에서 느껴지는 걱정이나 혼란을 짧게 공감한 뒤 "
    "차근차근 설명하고 필요하면 '같이 살펴봐요'처럼 다음 행동을 안내한다. "
    "과도하게 친근하거나 가벼운 말투, 근거 없는 안심·격려는 쓰지 않는다. "
    "본문은 서너 문장, 최대 다섯 문장으로 짧게 쓰되 모든 문장은 중간에 "
    "끊지 말고 완결한다. "
    "사실·외부 의견·서비스 해석의 경계를 유지하고 숫자와 단위는 원문 "
    "그대로 둔다."
    " 연금세액 Tool 입력이 제공되면 검증 답변을 쓰기 전에 요청된 "
    "calculate_pension_tax_credit_tool 또는 "
    "estimate_non_pension_withdrawal_tax_tool을 반드시 호출한다. Tool 결과의 "
    "숫자를 바꾸거나 Tool 밖에서 다시 계산하지 않는다."
)


class NarrationOutput(BaseModel):
    """구조화 출력 계약: 재서술 본문만 받는다.

    검토 과정은 thinking 요약(anthropic_thinking)이 담당한다. 별도 검토 노트를
    함께 생성하면 출력 토큰만 늘고 thinking이 있을 때 버려지므로 두지 않는다.
    """

    narration: str = Field(
        description="검증 답변을 쉬운 한국어 한 문단으로 다시 쓴 본문"
    )


from .narration_guard import (
    _ARABIC_NUMBER,
    _LEGAL_FRACTION,
    _PERCENT_RANGE,
    _ISO_DATE,
    _KOREAN_DATE,
    _DOTTED_DATE,
    _CURRENCY_MULTIPLIERS,
    _KOREAN_NUMBER,
    _AMBIGUOUS_SINGLE_KOREAN_NUMERALS,
    _APPROXIMATE_COUNT_NUMERALS,
    _NON_NUMERIC_KOREAN_COMPOUNDS,
    _IDIOMATIC_HUNDRED_TIMES_SUFFIX,
    _UNSAFE_CLAIM_PATTERNS,
    _NEGATION,
    _number_tokens,
    _korean_number_tokens,
    _unsafe_claim_instances,
    _unsafe_claims,
    _adds_unverified_content,
    _is_non_numeric_korean_match,
    contains_unsafe_financial_claim,
)
class ClaudeNarrator:
    """Rephrase verified output; reject any response that invents a new number."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        cache_path: Path | None = None,
        cache_persist_debounce_seconds: float = (
            NARRATION_CACHE_PERSIST_DEBOUNCE_SECONDS
        ),
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        if cache_persist_debounce_seconds < 0:
            raise ValueError("cache_persist_debounce_seconds must be non-negative")
        self._model = model.strip()
        self._api_key = api_key.strip()
        self._cache_path = cache_path
        self._cache_persist_debounce_seconds = cache_persist_debounce_seconds
        # 검증 통과 내레이션만 저장하는 LRU 캐시(폴백은 저장하지 않는다).
        self._narration_cache: OrderedDict[str, tuple[str, str | None]] = (
            OrderedDict()
        )
        self._narration_cache_lock = threading.Lock()
        self._cache_dirty = False
        self._cache_generation = 0
        self._last_cache_persisted_at: float | None = None
        self._load_persistent_cache()
        self.agent: Agent[None, NarrationOutput] = self._build_agent()

    def _build_agent(self) -> Agent[None, NarrationOutput]:
        settings = AnthropicModelSettings(
            # 출력 길이는 시스템프롬프트의 문장 수 제한으로 관리한다.
            # max_tokens는 안전 상한일 뿐이며, 초과 절단 시 구조화 출력이
            # 깨져 결정론 폴백으로 빠지므로 끊긴 문장이 노출되지 않는다.
            max_tokens=2500,
            # 고정부(시스템프롬프트·툴 정의) 서버측 프롬프트 캐싱.
            anthropic_cache_instructions=True,
            anthropic_cache_tool_definitions=True,
        )
        if not self._model.startswith("claude-haiku"):
            # Haiku 계열은 adaptive thinking 미지원(400)이고, enabled(고정
            # 예산)는 매번 thinking을 강제 생성해 오히려 느리다(실측:
            # enabled 7.2초 vs OFF 3.6초, 2026-07-18). Haiku에서는 thinking을
            # 끄고 숫자 가드가 품질을 보장한다. 그 외 모델은 검토 과정을
            # 이 thinking 요약만 사용한다(NarrationOutput 참고).
            settings["anthropic_thinking"] = {
                "type": "adaptive",
                "display": "summarized",
            }
        return Agent(
            AnthropicModel(
                self._model,
                provider=AnthropicProvider(api_key=self._api_key),
            ),
            output_type=NativeOutput(NarrationOutput),
            instructions=SYSTEM_PROMPT,
            tools=CHAT_AGENT_TOOLS,
            model_settings=settings,
        )

    def prewarm(self) -> None:
        """부팅 시 1회 호출해 첫 요청의 프로세스 초기화 지연을 흡수한다.

        실측: 콜드 첫 호출 ~14초 vs 워밍 후 ~4초(2026-07-18). 반드시 버리는
        Agent로 호출한다 — self.agent를 부팅 스레드의 이벤트루프에서 쓰면
        HTTP 클라이언트가 그 루프에 묶여 이후 요청 스레드의 호출이 멈춘다
        (TestClient 재현으로 확인). 실패해도 본 요청은 결정론 폴백으로
        동작하므로 경고만 남긴다.
        """
        try:
            self._build_agent().run_sync(
                "검증 답변:\n연금 코파일럿 내레이터 워밍업 호출이다.\n\n"
                "제한사항:\n한 문장으로만 답한다."
            )
        except Exception:  # noqa: BLE001 — 워밍업 실패는 서비스에 영향 없음
            logger.warning("narrator_prewarm_failed")

    def _cache_key(self, intent: ChatIntent, prompt: str) -> str:
        return sha256(
            f"{self._model}\x00{intent.value}\x00{prompt}".encode()
        ).hexdigest()

    def _read_persistent_cache(
        self,
    ) -> OrderedDict[str, tuple[str, str | None]]:
        if self._cache_path is None:
            return OrderedDict()
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return OrderedDict()
        if not isinstance(payload, dict) or payload.get("version") != 1:
            return OrderedDict()
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            return OrderedDict()
        loaded: OrderedDict[str, tuple[str, str | None]] = OrderedDict()
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            narration = entry.get("narration")
            reasoning = entry.get("reasoning")
            if not isinstance(key, str) or not isinstance(narration, str):
                continue
            if reasoning is not None and not isinstance(reasoning, str):
                continue
            loaded[key] = (narration, reasoning)
        while len(loaded) > NARRATION_CACHE_MAX_ENTRIES:
            loaded.popitem(last=False)
        return loaded

    def _merge_cache(
        self,
        entries: OrderedDict[str, tuple[str, str | None]],
        *,
        mark_dirty: bool = False,
    ) -> None:
        with self._narration_cache_lock:
            for key, value in entries.items():
                self._narration_cache[key] = value
                self._narration_cache.move_to_end(key)
            while len(self._narration_cache) > NARRATION_CACHE_MAX_ENTRIES:
                self._narration_cache.popitem(last=False)
            if mark_dirty and entries:
                self._cache_dirty = True
                self._cache_generation += 1

    def _load_persistent_cache(self) -> None:
        self._merge_cache(self._read_persistent_cache())

    def _persist_cache(self) -> None:
        if self._cache_path is None:
            return
        try:
            with _NARRATION_CACHE_FILE_LOCK:
                merged = self._read_persistent_cache()
                with self._narration_cache_lock:
                    cache_entries = OrderedDict(self._narration_cache)
                    cache_generation = self._cache_generation
                for key, value in cache_entries.items():
                    merged[key] = value
                    merged.move_to_end(key)
                while len(merged) > NARRATION_CACHE_MAX_ENTRIES:
                    merged.popitem(last=False)
                payload = {
                    "version": NARRATION_CACHE_VERSION,
                    "entries": [
                        {
                            "key": key,
                            "narration": narration,
                            "reasoning": reasoning,
                        }
                        for key, (narration, reasoning) in merged.items()
                    ],
                }
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._cache_path.with_suffix(
                    self._cache_path.suffix + ".tmp"
                )
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                temporary.replace(self._cache_path)
                with self._narration_cache_lock:
                    self._last_cache_persisted_at = monotonic()
                    if self._cache_generation == cache_generation:
                        self._cache_dirty = False
        except OSError:
            logger.warning("narration_cache_persist_failed")

    def flush_cache(self, *, force: bool = True) -> None:
        """Persist dirty verified narrations without delaying every request."""
        if self._cache_path is None:
            return
        with self._narration_cache_lock:
            if not self._cache_dirty:
                return
            if (
                not force
                and self._last_cache_persisted_at is not None
                and monotonic() - self._last_cache_persisted_at
                < self._cache_persist_debounce_seconds
            ):
                return
        self._persist_cache()

    def _cache_lookup(self, key: str) -> tuple[str, str | None] | None:
        with self._narration_cache_lock:
            cached = self._narration_cache.get(key)
            if cached is not None:
                self._narration_cache.move_to_end(key)
            return cached

    def _cache_store(
        self, key: str, narration: str, reasoning: str | None
    ) -> None:
        with self._narration_cache_lock:
            self._narration_cache[key] = (narration, reasoning)
            self._narration_cache.move_to_end(key)
            while len(self._narration_cache) > NARRATION_CACHE_MAX_ENTRIES:
                self._narration_cache.popitem(last=False)
            if self._cache_path is not None:
                self._cache_dirty = True
                self._cache_generation += 1
        self.flush_cache(force=False)

    def precompute(self, responses: Iterable[ChatResponse]) -> None:
        """Populate cache through a disposable narrator, never the request agent."""

        try:
            warmer = ClaudeNarrator(
                api_key=self._api_key,
                model=self._model,
                cache_path=self._cache_path,
                cache_persist_debounce_seconds=self._cache_persist_debounce_seconds,
            )
            for response in responses:
                warmer.narrate(response)
            with warmer._narration_cache_lock:
                warmed = OrderedDict(warmer._narration_cache)
            self._merge_cache(warmed, mark_dirty=True)
            self.flush_cache(force=False)
        except Exception:  # noqa: BLE001 — 프리컴퓨트 실패는 요청 경로와 격리
            logger.warning("narration_precompute_failed")

    def narrate(
        self,
        response: ChatResponse,
        *,
        pension_tax_input: PensionTaxScenarioInput | None = None,
        pension_tax_message: str | None = None,
    ) -> ChatResponse:
        if response.data_mode in {
            "verified_pension_account_overview",
            "verified_pension_account_deferred_topic",
        }:
            return response
        # NAVER titles/summaries are third-party metadata, not instructions.
        # Keep every news response deterministic: no external text enters the
        # narrator context, even if its wording does not match known attacks.
        if any(
            source.data_boundary
            in {DataBoundary.NEWS_METADATA, DataBoundary.NEWS_SUMMARY}
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
        # answer와 limitations는 모두 서버가 만든 검증 입력이며 Claude가 실제로
        # 함께 본다. 가드 원문도 같은 범위로 맞춰 limitations 반향 오탐을 막는다.
        # 아래 Tool JSON은 사용자 입력이므로 이 신뢰 범위에 포함하지 않는다.
        guard_source = "\n".join((response.answer, *response.limitations))
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
        # 엔진 답변이 결정론이라 같은 프롬프트의 검증 통과 내레이션은 그대로
        # 재사용한다(정확 일치라 오적중 없음). 폴백은 캐시되지 않는다.
        cache_key = self._cache_key(response.intent, prompt)
        cached = self._cache_lookup(cache_key)
        if cached is not None:
            cached_answer, cached_reasoning = cached
            data = response.model_dump()
            data.update(
                {
                    "answer": cached_answer,
                    "narration_mode": "claude_verified",
                    "model_name": self._model,
                    "narration_reasoning": cached_reasoning,
                }
            )
            return ChatResponse.model_validate(data)
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
            required_tools: set[str] = set()
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

        if response.intent == ChatIntent.PENSION_TAX:
            candidate = candidate.replace(PENSION_TAX_CLOSING_NOTICE, "").rstrip()
            candidate += f"\n{PENSION_TAX_CLOSING_NOTICE}"
            # 이 문구는 모델 출력이 아니라 서버가 강제로 붙이는 검증된 고정문이다.
            guard_source += f"\n{PENSION_TAX_CLOSING_NOTICE}"

        if _adds_unverified_content(candidate, guard_source):
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
        reasoning = self._safe_reasoning(thinking, guard_source)
        self._cache_store(cache_key, candidate, reasoning)
        data = response.model_dump()
        data.update(
            {
                "answer": candidate,
                "narration_mode": "claude_verified",
                "model_name": self._model,
                "narration_reasoning": reasoning,
            }
        )
        return ChatResponse.model_validate(data)

    @staticmethod
    def _safe_reasoning(reasoning: str | None, source: str) -> str | None:
        """본문과 달리 보조 설명은 새 숫자 감지 시 이 필드만 조용히 생략한다.

        모델이 thinking을 내지 않으면 reasoning이 None이고, 그때는 검토 과정
        없이 본문만 남긴다(본문 자체는 숫자 가드를 이미 통과한 상태다).
        """
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
