"""Evidence-bounded ETF product feature sentences for theme cards."""

import logging
import re
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import AgentRunError

from ..llm_models import build_model, build_model_settings
from ..llm_usage import LlmCallKind, LlmUsageRecorder, record_llm_usage
from .narration_guard import contains_unsafe_financial_claim

logger = logging.getLogger(__name__)

DEFAULT_ETF_PRODUCT_RESEARCH_PATH = Path(
    "docs/20_리서치/ETF_상품/ETF_상품_설명_통합원문.md"
)
ETF_FEATURE_PROMPT_VERSION = "etf-product-feature-v1"
ETF_FEATURE_CACHE_MAX_ENTRIES = 256
ETF_FEATURE_MAX_LENGTH = 180

_NUMERIC_UNIT = re.compile(
    r"(?<![A-Za-z0-9])\d(?:[\d,.]*\d)?\s*(?:%|원|만원|억원)"
)

_FORBIDDEN_FEATURE_TERMS = (
    "수익률",
    "보장",
    "추천",
    "매수",
    "매도",
    "전망",
    "거래대금",
    "운용보수",
    "총보수",
)


class EtfProductFeatureFacts(BaseModel):
    """Verified inputs available for one selected ETF."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    isu_code: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    theme_name: str = Field(min_length=1)
    approved_description: str | None = None
    benchmark_name: str | None = None
    classification: dict[str, Any] = Field(default_factory=dict)
    top_holding_names: tuple[str, ...] = ()


class EtfProductFeatureResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isu_code: str
    feature: str
    support_quote: str = Field(
        description="입력 근거에서 그대로 복사한 핵심 근거 문장"
    )


class EtfProductFeatureBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    products: tuple[EtfProductFeatureResult, ...]


class EtfProductFeatureGenerator(Protocol):
    def generate(
        self, facts: tuple[EtfProductFeatureFacts, ...]
    ) -> dict[str, str]: ...


SYSTEM_PROMPT = (
    "당신은 ETF 테마 카드의 '상품 특징' 한 줄만 작성한다. 입력에 제공된 "
    "공개 대화 통합 원문, 운용사 공식 설명, 검증된 기초·비교지수, KIS "
    "구성종목 사실만 사용한다. 상품마다 한두 문장의 쉬운 한국어 해요체로 "
    "투자 대상과 다른 상품과 구별되는 구성 특징을 설명한다. 수수료, "
    "거래대금, 순자산, 과거 수익률, 미래 전망, 추천·매매 의견은 쓰지 않는다. "
    "입력에 없는 숫자와 사실을 만들지 않는다. support_quote에는 문장의 핵심을 "
    "직접 뒷받침하는 입력 근거 일부를 글자 그대로 복사한다."
)


def deterministic_etf_product_feature(facts: EtfProductFeatureFacts) -> str:
    """Always return a grounded sentence when Claude or source prose is unavailable."""

    if facts.approved_description:
        return " ".join(facts.approved_description.split())
    holdings = tuple(name for name in facts.top_holding_names if name)[:3]
    benchmark_name = (
        facts.benchmark_name
        if facts.benchmark_name
        and _NUMERIC_UNIT.search(facts.benchmark_name) is None
        else None
    )
    if benchmark_name and holdings:
        names = "·".join(holdings)
        return (
            f"{benchmark_name}를 기준으로 {names} 등을 담아 "
            f"{facts.theme_name} 분야에 투자합니다."
        )
    if benchmark_name:
        return (
            f"{benchmark_name}를 기준으로 {facts.theme_name} 관련 "
            "기업·자산에 투자합니다."
        )
    if holdings:
        names = "·".join(holdings)
        return (
            f"{names} 등을 주요 구성종목으로 담아 {facts.theme_name} 분야에 "
            "투자합니다."
        )
    return f"{facts.theme_name} 관련 기업·자산에 분산 투자하는 ETF입니다."


class ClaudeEtfProductFeatureGenerator:
    """Generate a batch of validated feature sentences with deterministic fallback."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        research_path: Path = DEFAULT_ETF_PRODUCT_RESEARCH_PATH,
        usage_recorder: LlmUsageRecorder | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        self._model = model.strip()
        self._usage_recorder = usage_recorder
        self._research_path = research_path
        try:
            self._research_text = research_path.read_text(encoding="utf-8")
        except OSError:
            self._research_text = ""
        self._cache: OrderedDict[str, dict[str, str]] = OrderedDict()
        self.agent: Agent[None, EtfProductFeatureBatch] = Agent(
            build_model(self._model, api_key=api_key.strip()),
            output_type=NativeOutput(EtfProductFeatureBatch),
            instructions=SYSTEM_PROMPT,
            model_settings=build_model_settings(self._model, max_tokens=1200),
        )

    def _research_excerpt(self, facts: EtfProductFeatureFacts) -> str:
        if not self._research_text:
            return ""
        marker = f"## [ETF:{facts.isu_code}] {facts.product_name}"
        start = self._research_text.find(marker)
        if start >= 0:
            end = self._research_text.find("\n## [ETF:", start + len(marker))
            return self._research_text[start : end if end >= 0 else None].strip()
        match = re.search(
            rf"(?m)^\d+\.\s+{re.escape(facts.product_name)}\s*$",
            self._research_text,
        )
        if match is None:
            return ""
        excerpt = self._research_text[match.start() : match.start() + 1800]
        next_product = re.search(r"(?m)^\d+\.\s+\S", excerpt[1:])
        if next_product is not None:
            excerpt = excerpt[: next_product.start() + 1]
        return excerpt.strip()

    def _prompt(self, facts: tuple[EtfProductFeatureFacts, ...]) -> str:
        chunks = []
        for item in facts:
            holdings = ", ".join(item.top_holding_names) or "없음"
            classification = ", ".join(
                f"{key}={value}"
                for key, value in sorted(item.classification.items())
                if value not in {None, "", "unknown"}
            )
            chunks.append(
                "\n".join(
                    (
                        f"[상품 {item.isu_code}]",
                        f"상품명: {item.product_name}",
                        f"테마: {item.theme_name}",
                        f"승인 설명: {item.approved_description or '없음'}",
                        f"기초·비교지수: {item.benchmark_name or '없음'}",
                        f"검증 분류: {classification or '없음'}",
                        f"KIS 구성종목: {holdings}",
                        "통합 원문 발췌:",
                        self._research_excerpt(item) or "없음",
                    )
                )
            )
        return (
            f"프롬프트 버전: {ETF_FEATURE_PROMPT_VERSION}\n"
            "아래 상품 코드를 빠짐없이 한 번씩 반환하세요.\n\n"
            + "\n\n".join(chunks)
        )

    @staticmethod
    def _evidence_text(facts: EtfProductFeatureFacts, excerpt: str) -> str:
        return "\n".join(
            filter(
                None,
                (
                    facts.approved_description,
                    facts.benchmark_name,
                    " ".join(facts.top_holding_names),
                    excerpt,
                ),
            )
        )

    def _validate(
        self,
        output: EtfProductFeatureBatch,
        facts: tuple[EtfProductFeatureFacts, ...],
    ) -> dict[str, str]:
        requested = {item.isu_code: item for item in facts}
        if len(output.products) != len(requested):
            return {}
        generated: dict[str, str] = {}
        for result in output.products:
            source = requested.get(result.isu_code)
            if source is None or result.isu_code in generated:
                return {}
            feature = " ".join(result.feature.split())
            support_quote = result.support_quote.strip()
            evidence = self._evidence_text(source, self._research_excerpt(source))
            if (
                len(feature) < 10
                or len(feature) > ETF_FEATURE_MAX_LENGTH
                or not support_quote
                or support_quote not in evidence
                or any(term in feature for term in _FORBIDDEN_FEATURE_TERMS)
                or contains_unsafe_financial_claim(feature)
            ):
                return {}
            generated[result.isu_code] = feature
        return generated if generated.keys() == requested.keys() else {}

    def generate(
        self, facts: tuple[EtfProductFeatureFacts, ...]
    ) -> dict[str, str]:
        if not facts:
            return {}
        prompt = self._prompt(facts)
        key = sha256(
            f"{self._model}\x00{ETF_FEATURE_PROMPT_VERSION}\x00{prompt}".encode()
        ).hexdigest()
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            record_llm_usage(
                self._usage_recorder,
                call_kind=LlmCallKind.ETF_PRODUCT_FEATURE,
                model_name=self._model,
                outcome="cache_hit",
                outcome_detail="etf_product_feature_cache",
                provider_called=False,
                application_cache_hit=True,
            )
            return dict(cached)
        started_at = monotonic()
        result = None
        try:
            result = self.agent.run_sync(prompt)
            generated = self._validate(result.output, facts)
        except (AgentRunError, OSError):
            record_llm_usage(
                self._usage_recorder,
                call_kind=LlmCallKind.ETF_PRODUCT_FEATURE,
                model_name=self._model,
                outcome="provider_error",
                outcome_detail="agent_error",
                result=result,
                started_at=started_at,
            )
            logger.warning("etf_product_feature_generation_failed")
            return {}
        except ValueError:
            record_llm_usage(
                self._usage_recorder,
                call_kind=LlmCallKind.ETF_PRODUCT_FEATURE,
                model_name=self._model,
                outcome="validation_rejected",
                outcome_detail="invalid_output",
                result=result,
                started_at=started_at,
            )
            logger.warning("etf_product_feature_generation_failed")
            return {}
        if not generated:
            record_llm_usage(
                self._usage_recorder,
                call_kind=LlmCallKind.ETF_PRODUCT_FEATURE,
                model_name=self._model,
                outcome="validation_rejected",
                outcome_detail="evidence_validation_failed",
                result=result,
                started_at=started_at,
            )
            logger.warning("etf_product_feature_validation_failed")
            return {}
        record_llm_usage(
            self._usage_recorder,
            call_kind=LlmCallKind.ETF_PRODUCT_FEATURE,
            model_name=self._model,
            outcome="accepted",
            outcome_detail=None,
            result=result,
            started_at=started_at,
        )
        self._cache[key] = generated
        while len(self._cache) > ETF_FEATURE_CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)
        return dict(generated)
