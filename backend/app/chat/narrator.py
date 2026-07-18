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


_ARABIC_NUMBER = re.compile(
    r"(?<![0-9A-Za-z_])(?P<sign>[+\-−])?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    # 긴 통화 단위를 먼저 둬 '3조원'이 '3조'로 잘리지 않게 한다. 세·주·위·
    # 조·평·원은 값이 같아도 의미가 달라 단위 스왑을 보수적으로 거부한다.
    r"(?P<unit>조\s*원|백\s*만\s*원|천\s*만\s*원|억\s*원|만\s*원|"
    r"천\s*원|원|KRW|퍼센트|프로|%|년|개월|월|분기|일|세|주|위|"
    r"조|평|배|개|건|명|회|차|층)?"
    r"(?![0-9A-Za-z_])",
    re.I,
)
_LEGAL_FRACTION = re.compile(
    r"(?P<denominator>\d[\d,]*)\s*분의\s*(?P<numerator>\d[\d,]*(?:\.\d+)?)"
)
_PERCENT_RANGE = re.compile(
    r"(?<!\d)(?P<left>\d[\d,]*(?:\.\d+)?)\s*%?\s*"
    r"(?:~|〜|–|—)\s*(?P<right>\d[\d,]*(?:\.\d+)?)\s*%(?!\d)"
)
_ISO_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?!\d)"
)
_KOREAN_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})\s*년\s*(?P<month>\d{1,2})\s*월\s*"
    r"(?P<day>\d{1,2})\s*일(?!\d)"
)
_CURRENCY_MULTIPLIERS = {
    "원": Decimal("1"),
    "천원": Decimal("1000"),
    "만원": Decimal("10000"),
    "백만원": Decimal("1000000"),
    "천만원": Decimal("10000000"),
    "억원": Decimal("100000000"),
    "조원": Decimal("1000000000000"),
    "krw": Decimal("1"),
}
_KOREAN_NUMBER = re.compile(
    # '3천만 원'의 '천만 원'을 별도 한글 숫자로 중복 추출하지 않는다.
    r"(?<![0-9A-Za-z_,하나다섯여섯일곱여덟아홉영공일이삼사오육칠팔구십백천만억한두둘세셋네넷열])"
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
# 위험 주장 앞의 '손실 없이', '예금이 아니라'는 뒤 주장을 부정하지 않는다.
# 따라서 매치 주변 창이 아니라 주장 키워드 직후의 문법적 꼬리만 부정으로
# 인정한다. 애매한 원거리 부정은 안전 우선으로 거부(결정론 폴백)한다.
_NEGATION = re.compile(
    r"^\s*(?:은|는|이|가|을|를|도)?\s*"
    r"(?:하(?:지\s*(?:않|못)|지\s*마)|되\s*지\s*(?:않|못)|"
    r"할\s*수\s*없|(?:해서는|하면|해도)\s*안\s*(?:돼|되)|"
    r"안\s*(?:돼|되)|허용되지|금지|아니|없|못|제공하지|의미하지)"
)


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

    # '10~20%'와 '10%~20%'는 양 끝이 모두 퍼센트인 같은 범위다. 명시적인
    # % 종결 범위만 정규화하며 단위 없는 일반 범위는 추론하지 않는다.
    for match in _PERCENT_RANGE.finditer(text):
        left = Decimal(match.group("left").replace(",", ""))
        right = Decimal(match.group("right").replace(",", ""))
        values.update({(left, "%", "unsigned"), (right, "%", "unsigned")})

    # ISO와 한국어 날짜 표기만 연·월·일 토큰으로 맞춘다. 달력값을 다른
    # 단위로 바꾸지 않아 날짜가 아닌 숫자를 동치로 오인하지 않는다.
    for date_pattern in (_ISO_DATE, _KOREAN_DATE):
        for match in date_pattern.finditer(text):
            values.update(
                {
                    (Decimal(match.group("year")), "date_year", "unsigned"),
                    (Decimal(match.group("month")), "date_month", "unsigned"),
                    (Decimal(match.group("day")), "date_day", "unsigned"),
                }
            )

    remaining = _LEGAL_FRACTION.sub(" ", text)
    remaining = _PERCENT_RANGE.sub(" ", remaining)
    remaining = _ISO_DATE.sub(" ", remaining)
    remaining = _KOREAN_DATE.sub(" ", remaining)
    for match in _ARABIC_NUMBER.finditer(remaining):
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
        multiplier = _CURRENCY_MULTIPLIERS.get(unit)
        if multiplier is not None:
            value *= multiplier
            unit = "krw"
        values.add((value, unit, sign_kind))
    return values


# 한 글자 숫자어(이·한·일·구·사·오·공·영)는 흔한 낱말의 첫 글자와 겹쳐
# (이번·이건·한번·구원·사실·오늘) regex가 형태소 경계 없이 숫자로 오인한다.
# 이런 단독 한 글자 모호 숫자어는 숫자 토큰에서 제외한다. 두 글자 이상 조합
# (칠십·구백만)은 일상어와 겹치지 않아 그대로 검증하고, 실제 조작 수치는
# 아라비아 숫자 가드(_ARABIC_NUMBER)가 엄격히 잡는다.
_AMBIGUOUS_SINGLE_KOREAN_NUMERALS = frozenset("이한일구사오공영")
_APPROXIMATE_COUNT_NUMERALS = frozenset({"한두", "두세"})
_NON_NUMERIC_KOREAN_COMPOUNDS = frozenset({"이사회", "육회"})
_IDIOMATIC_HUNDRED_TIMES_SUFFIX = re.compile(r"^\s*(?:맞|옳)(?:는|은)?\s*말")


def _is_non_numeric_korean_match(
    text: str,
    match: re.Match[str],
    *,
    number: str,
    unit: str,
) -> bool:
    """Exclude only narrow, explainable Korean homographs from number tokens."""

    raw = match.group()
    if raw in _NON_NUMERIC_KOREAN_COMPOUNDS:
        return True
    if unit == "번" and number in _APPROXIMATE_COUNT_NUMERALS:
        # 한두/두세 번은 정확값이 아닌 일상 어림수라 검증 수치로 연결하지 않는다.
        return True
    compact = re.sub(r"\s+", "", raw)
    # '백번 맞는 말'에서 백번은 횟수 주장이 아니라 강조 관용구다.
    return compact == "백번" and bool(
        _IDIOMATIC_HUNDRED_TIMES_SUFFIX.search(text[match.end() :])
    )


def _korean_number_tokens(text: str) -> set[tuple[str, str, str]]:
    values: set[tuple[str, str, str]] = set()
    for match in _KOREAN_NUMBER.finditer(text):
        number = re.sub(r"\s+", "", match.group("number"))
        if number in _AMBIGUOUS_SINGLE_KOREAN_NUMERALS:
            continue
        sign = match.group("sign") or "부호없음"
        unit = re.sub(r"\s+", "", match.group("unit"))
        if _is_non_numeric_korean_match(
            text,
            match,
            number=number,
            unit=unit,
        ):
            continue
        values.add((number, unit, sign))
    return values


def _unsafe_claim_instances(text: str) -> set[tuple[str, str]]:
    """Return each non-negated claim as category plus normalized matched text.

    카테고리만 비교하면 원문의 '원금 보장' 하나로 새 '수익 보장'까지 통과한다.
    공백·문장부호만 제거한 실제 매치 문구를 함께 비교해 그 우회를 막는다.
    """

    claims: set[tuple[str, str]] = set()
    for category, pattern in _UNSAFE_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            suffix = text[match.end() : match.end() + 24]
            if _NEGATION.search(suffix) is None:
                normalized_match = re.sub(
                    r"[^0-9A-Za-z가-힣%]+", "", match.group()
                ).casefold()
                claims.add((category, normalized_match))
    return claims


def _unsafe_claims(text: str) -> set[str]:
    return {category for category, _ in _unsafe_claim_instances(text)}


def contains_unsafe_financial_claim(text: str) -> bool:
    """Expose the narrator's positive-claim guard to verified RAG consumers."""

    return bool(_unsafe_claim_instances(text))


def _adds_unverified_content(candidate: str, source: str) -> bool:
    return (
        not _number_tokens(candidate).issubset(_number_tokens(source))
        or not _korean_number_tokens(candidate).issubset(
            _korean_number_tokens(source)
        )
        or not _unsafe_claim_instances(candidate).issubset(
            _unsafe_claim_instances(source)
        )
    )


class ClaudeNarrator:
    """Rephrase verified output; reject any response that invents a new number."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        cache_path: Path | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        self._model = model.strip()
        self._api_key = api_key.strip()
        self._cache_path = cache_path
        # 검증 통과 내레이션만 저장하는 LRU 캐시(폴백은 저장하지 않는다).
        self._narration_cache: OrderedDict[str, tuple[str, str | None]] = (
            OrderedDict()
        )
        self._narration_cache_lock = threading.Lock()
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
    ) -> None:
        with self._narration_cache_lock:
            for key, value in entries.items():
                self._narration_cache[key] = value
                self._narration_cache.move_to_end(key)
            while len(self._narration_cache) > NARRATION_CACHE_MAX_ENTRIES:
                self._narration_cache.popitem(last=False)

    def _load_persistent_cache(self) -> None:
        self._merge_cache(self._read_persistent_cache())

    def _persist_cache(self) -> None:
        if self._cache_path is None:
            return
        try:
            with _NARRATION_CACHE_FILE_LOCK:
                merged = self._read_persistent_cache()
                with self._narration_cache_lock:
                    for key, value in self._narration_cache.items():
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
        except OSError:
            logger.warning("narration_cache_persist_failed")

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
        self._persist_cache()

    def precompute(self, responses: Iterable[ChatResponse]) -> None:
        """Populate cache through a disposable narrator, never the request agent."""

        try:
            warmer = ClaudeNarrator(
                api_key=self._api_key,
                model=self._model,
                cache_path=self._cache_path,
            )
            for response in responses:
                warmer.narrate(response)
            with warmer._narration_cache_lock:
                warmed = OrderedDict(warmer._narration_cache)
            self._merge_cache(warmed)
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
