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
from hashlib import sha256
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ModelResponse, ThinkingPart, ToolCallPart

from ..engine import PensionTaxScenarioInput
from ..llm_models import GOOGLE, build_model, build_model_settings, resolve_vendor
from .models import ChatIntent, ChatResponse, DataBoundary
from .narration_guard import (
    _adds_unverified_content as _adds_unverified_content,
)
from .narration_guard import (
    _is_non_numeric_korean_match as _is_non_numeric_korean_match,
)
from .narration_guard import (
    _korean_number_tokens as _korean_number_tokens,
)
from .narration_guard import (
    _number_tokens as _number_tokens,
)
from .narration_guard import (
    _unsafe_claim_instances as _unsafe_claim_instances,
)
from .narration_guard import (
    _unsafe_claims as _unsafe_claims,
)
from .narration_guard import (
    contains_unsafe_financial_claim as contains_unsafe_financial_claim,
)
from .pension_tax_parser import resolve_pension_tax_inputs
from .tools import CHAT_AGENT_TOOLS, PENSION_TAX_CLOSING_NOTICE

logger = logging.getLogger(__name__)

# 엔진 답변이 결정론이므로 같은 프롬프트는 같은 검증 내레이션을 재사용한다.
NARRATION_CACHE_MAX_ENTRIES = 256
NARRATION_CACHE_VERSION = 4
NARRATION_CACHE_PERSIST_DEBOUNCE_SECONDS = 5.0
_NARRATION_CACHE_FILE_LOCK = threading.Lock()

# 워밍업은 응답을 버리므로 서비스 모델과 무관하게 벤더별 최저가 모델로
# 호출한다. 다만 API 키는 벤더마다 다르므로 서비스 모델과 같은 벤더를 쓴다.
PREWARM_MODEL = "claude-haiku-4-5"
PREWARM_MODEL_BY_VENDOR = {
    GOOGLE: "gemini-3.5-flash-lite",
}

# thinking을 켜면 오히려 느려지는 저지연 모델 계열.
_LOW_LATENCY_MODEL_PREFIXES = ("claude-haiku", "gemini-3.5-flash-lite")


def _is_low_latency_model(model: str) -> bool:
    name = model.strip().lower()
    _, _, bare = name.rpartition(":")
    return (bare or name).startswith(_LOW_LATENCY_MODEL_PREFIXES)


def prewarm_model_for(model: str) -> str:
    """서비스 모델과 같은 벤더의 워밍업용 모델 이름."""

    return PREWARM_MODEL_BY_VENDOR.get(resolve_vendor(model), PREWARM_MODEL)

NARRATABLE_INTENTS = {
    ChatIntent.ACCOUNT_RULE,
    ChatIntent.MOCK_PORTFOLIO,
    ChatIntent.PROVIDER_DISCLOSURE,
    ChatIntent.PENSION_TAX,
}

# 인텐트별 상위 모델 라우팅(2026-07-26 실측). 상위 모델은 같은 길이의 답변을
# 내면서도 기본 모델보다 2배 이상 느리므로(계좌 규칙 8.3초 vs 3.6초) 설명
# 품질이 실제로 값을 하는 인텐트에만 쓴다.
#
# PENSION_TAX는 초기 후보였지만 제외했다. 세액 답변은 Tool 왕복이 한 번 더
# 붙어 상위 모델에서 평균 10.0초까지 늘고(기본 모델 6.1초), 숫자 가드 통과율도
# 8회 중 3회로 기본 모델(8회 중 5회)보다 낮았다. 느려진 만큼 폴백 확률이 커져
# 사용자는 오래 기다린 뒤 검증 원문을 보게 된다.
UPGRADED_INTENTS = frozenset({ChatIntent.ACCOUNT_RULE})
# 계좌 규칙은 근거 문서가 여러 건 결합될 때만 비교·해설 성격이 강해진다.
# 단일 근거의 한 줄 규칙 답변은 기본 모델로 충분하다.
UPGRADED_ACCOUNT_RULE_MIN_SOURCES = 2

# 검증 답변은 '-한다'체로 작성된 경우가 많아, 문체 지시가 문장 중간에 묻히면
# 모델이 원문 문체를 따라가 하십시오체로 이탈한다(실측: 6개 문항 6회 위반).
# 최우선 지시로 올리고 금지 어미를 열거하면 위반이 사라진다(같은 문항 0회).
REGISTER_RULE = (
    "가장 중요한 규칙: 모든 문장을 반드시 해요체로 끝낸다. "
    "'-해요', '-예요', '-이에요', '-돼요', '-어요'로만 문장을 맺는다. "
    "'-습니다', '-합니다', '-입니다', '-하십시오', '-바랍니다', '-이다', "
    "'-한다'로 끝나는 문장은 절대 쓰지 않는다. 검증 답변 원문이 '-한다'나 "
    "'-습니다'로 쓰여 있어도 해요체로 바꿔 쓴다. 친절하고 차분한 상담원의 "
    "말투를 지키되 과장된 감탄이나 근거 없는 안심은 넣지 않는다.\n\n"
)

# 내레이션 상한은 프롬프트·구조화 출력 스키마·후검증 세 곳이 같은 값을 쓴다.
# 한 곳만 바꾸면 정상 내레이션이 길이 검증에 걸려 통째로 폴백된다.
#
# 상한 자체는 안전장치이고, 실제 분량은 프롬프트의 문장 수 지시가 정한다.
# 세액공제와 중도해지를 함께 묻는 결정론 원문이 342자까지 나오므로 상한을
# 그보다 낮추면 정상 답변이 폴백된다(실측: 280자로 낮췄을 때 재현).
NARRATION_MAX_CHARS = 350

# 구조화 출력 검증용 상한. 표시 상한(NARRATION_MAX_CHARS)을 조금 넘긴 출력은
# 여기서 통과시켜 문장 경계 트림으로 다듬는다. 두 값을 같게 두면 트림이
# 무력화된다(실측: 355자 입력이 재시도 1회 후 폴백).
NARRATION_SCHEMA_MAX_CHARS = NARRATION_MAX_CHARS * 2

# 상한을 넘겼을 때 문장을 통째로 버리면 사용자는 해요체 설명 대신 '-한다'체
# 근거 원문을 보게 되어 한 대화 안에서 말투가 튄다. 넘친 만큼만 문장 경계에서
# 덜어내면 남은 문장은 그대로 완결이라 중간이 끊기지 않는다.
#
# 뒤에 공백이나 문자열 끝이 오는 종결 부호만 경계로 본다. 원문 숫자의 쉼표는
# 애초에 대상이 아니고 '1.5%'처럼 소수점 뒤에 숫자가 붙는 경우도 걸리지 않는다.
# handlers/account_rules._SENTENCE_END와 같은 판정이며, 그쪽은 행 단위로
# 이쪽은 문자 상한에 맞춰 쓴다.
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def _trim_to_sentence_boundary(text: str, limit: int) -> str:
    """상한 안에서 마지막으로 완결된 문장까지만 남긴다.

    첫 문장부터 상한을 넘으면 자를 지점이 없다. 그때는 빈 문자열을 돌려
    호출부가 기존 폴백을 그대로 타게 한다(문장 중간을 잘라 내보내지 않는다).
    """

    if len(text) <= limit:
        return text
    end = 0
    for match in _SENTENCE_END.finditer(text):
        if match.end() > limit:
            break
        end = match.end()
    return text[:end].rstrip()

SYSTEM_PROMPT = (
    REGISTER_RULE
    +
    "당신은 연금 코파일럿의 설명 전용 내레이터다. 규칙 엔진 결과를 "
    "직접 다시 계산하지 않으며 새로운 "
    "수치·상품·전망·매매의견을 만들지 않는다. 제공된 검증 답변의 "
    "사실만 투자 입문 성인을 위한 명확하고 자연스러운 해요체 한 문단으로 "
    "다시 쓴다. 질문의 핵심 결론을 "
    "첫 문장에 직접 말하고, 검증 답변의 배경이나 같은 내용을 반복하지 않는다. "
    "금융 용어를 처음 언급할 때는 새로운 사실·수치를 만들지 않는 범위에서 "
    "괄호 또는 짧은 정의로 뜻을 설명한다. 유아적인 비유나 과도한 단순화는 피하고, "
    "필요한 위험·제약·판단 기준은 생략하지 않는다. 공감이나 다음 행동은 꼭 필요할 "
    "때만 한 문장 안에서 "
    "짧게 안내한다. "
    "과도하게 친근하거나 가벼운 말투, 근거 없는 안심·격려는 쓰지 않는다. "
    f"본문은 두 문장 이내, {NARRATION_MAX_CHARS}자 이내로 쓰고 모든 문장은 "
    "중간에 끊지 말고 완결한다. 결론과 그 근거가 되는 숫자만 남기고, 검증 "
    "답변의 나머지 세부는 사용자가 후속 질문으로 골라 보므로 여기서 함께 "
    "옮기지 않는다. 다만 검증 답변이 서로 다른 계산 결과를 여러 건 담고 "
    "있으면 어느 것도 빠뜨리지 않는다. "
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
        # 스키마 상한은 표시 상한보다 넉넉하게 둔다. 두 값을 같게 두면 351자
        # 출력이 구조화 검증에서 먼저 거부돼(재시도 1회 낭비 후 폴백) 문장
        # 경계 트림에 도달하지 못한다. 표시 분량은 프롬프트 지시와 트림이 맡고
        # 이 값은 폭주 출력만 막는다.
        max_length=NARRATION_SCHEMA_MAX_CHARS,
        description=(
            "검증 답변을 투자 입문 성인에게 맞는 한국어로 "
            f"{NARRATION_MAX_CHARS}자 이내에 요약한 한 문단"
        )
    )


class ClaudeNarrator:
    """Rephrase verified output; reject any response that invents a new number."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        upgraded_model: str | None = None,
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
        # 상위 모델 미설정이면 기본 모델만 쓰고 라우팅은 사실상 비활성이다.
        self._upgraded_model = (upgraded_model or "").strip() or self._model
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
        # 상위 모델 에이전트는 실제로 필요한 첫 요청에서 만든다.
        self._upgraded_agent: Agent[None, NarrationOutput] | None = None
        self._upgraded_agent_lock = threading.Lock()

    def _build_agent(self) -> Agent[None, NarrationOutput]:
        return self._build_agent_for(self._model)

    def _model_for(self, response: ChatResponse) -> str:
        """인텐트와 근거 수로 이 응답에 쓸 모델을 고른다."""

        if self._upgraded_model == self._model:
            return self._model
        if response.intent not in UPGRADED_INTENTS:
            return self._model
        if (
            response.intent == ChatIntent.ACCOUNT_RULE
            and len(response.sources) < UPGRADED_ACCOUNT_RULE_MIN_SOURCES
        ):
            return self._model
        return self._upgraded_model

    def _agent_for_model(self, model: str) -> Agent[None, NarrationOutput]:
        if model == self._model:
            return self.agent
        with self._upgraded_agent_lock:
            if self._upgraded_agent is None:
                self._upgraded_agent = self._build_agent_for(model)
            return self._upgraded_agent

    def _build_agent_for(self, model: str) -> Agent[None, NarrationOutput]:
        # 저지연 모델(Haiku 계열·Flash Lite 계열)에서는 thinking을 끈다.
        # Haiku 계열은 adaptive thinking 미지원(400)이고, 고정 예산 thinking은
        # 매번 추론을 강제 생성해 오히려 느리다(실측: enabled 7.2초 vs OFF
        # 3.6초, 2026-07-18). Flash Lite도 같은 이유로 끈다. thinking을 끈
        # 모델에서는 숫자 가드가 품질을 보장한다. 그 외 모델은 검토 과정을
        # thinking 요약으로만 사용한다(NarrationOutput 참고).
        settings = build_model_settings(
            model,
            # 출력 길이는 시스템프롬프트의 문장 수 제한으로 관리한다.
            # max_tokens는 안전 상한일 뿐이며, 초과 절단 시 구조화 출력이
            # 깨져 결정론 폴백으로 빠지므로 끊긴 문장이 노출되지 않는다.
            max_tokens=2500,
            # 고정부(시스템프롬프트·툴 정의) 서버측 프롬프트 캐싱.
            cache_static_prompt=True,
            thinking=not _is_low_latency_model(model),
        )
        return Agent(
            build_model(model, api_key=self._api_key),
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

        워밍업은 프로세스·연결 초기화가 목적이라 답변 품질을 쓰지 않고
        버린다. 그래서 서비스 모델과 같은 벤더의 최저가 모델로 호출한다.
        """
        try:
            self._build_agent_for(prewarm_model_for(self._model)).run_sync(
                "검증 답변:\n연금 코파일럿 내레이터 워밍업 호출이다.\n\n"
                "제한사항:\n한 문장으로만 답한다."
            )
        except Exception:  # noqa: BLE001 — 워밍업 실패는 서비스에 영향 없음
            logger.warning("narrator_prewarm_failed")

    def _cache_key(self, intent: ChatIntent, prompt: str, model: str) -> str:
        return sha256(
            f"{model}\x00{intent.value}\x00{prompt}".encode()
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
        if (
            not isinstance(payload, dict)
            or payload.get("version") != NARRATION_CACHE_VERSION
        ):
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
                upgraded_model=self._upgraded_model,
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
        model = self._model_for(response)
        cache_key = self._cache_key(response.intent, prompt, model)
        cached = self._cache_lookup(cache_key)
        if cached is not None:
            cached_answer, cached_reasoning = cached
            data = response.model_dump()
            data.update(
                {
                    "answer": cached_answer,
                    "narration_mode": "claude_verified",
                    "model_name": model,
                    "narration_reasoning": cached_reasoning,
                }
            )
            return ChatResponse.model_validate(data)
        try:
            result = self._agent_for_model(model).run_sync(prompt)
            output = result.output
            candidate = output.narration.strip()
            if not candidate:
                raise ValueError("Claude returned an empty narration")
            if len(candidate) > NARRATION_MAX_CHARS:
                # 넘친 문장을 버리면 말투가 근거 원문체로 튄다. 완결 문장까지만
                # 남기고, 첫 문장부터 넘쳐 남길 것이 없을 때만 폴백한다.
                candidate = _trim_to_sentence_boundary(
                    candidate, NARRATION_MAX_CHARS
                )
                if not candidate:
                    return self._fallback(
                        response,
                        "Claude 설명이 길어 검증 원문을 표시합니다.",
                        reason="narration_too_long",
                    )
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
                "model_name": model,
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
