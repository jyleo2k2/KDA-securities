from __future__ import annotations

import json
import threading
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

from pydantic_ai.usage import RunUsage

from backend.app.chat.etf_product_features import (
    ClaudeEtfProductFeatureGenerator,
    EtfProductFeatureBatch,
    EtfProductFeatureFacts,
    EtfProductFeatureResult,
)
from backend.app.chat.models import (
    ChatIntent,
    ChatResponse,
    DataBoundary,
    SourceEvidence,
)
from backend.app.chat.narrator import ClaudeNarrator, NarrationOutput
from backend.app.chat.topic_guard import (
    ClaudeTopicGuard,
    TopicGuardDecision,
    TopicGuardRoute,
)
from backend.app.llm_usage import (
    BufferedLlmUsageRecorder,
    LlmCallKind,
    LlmUsageObservation,
    ModelPricingCatalog,
    price_observation,
    record_llm_usage,
)


def _observation() -> LlmUsageObservation:
    return LlmUsageObservation(
        call_kind=LlmCallKind.NARRATION,
        model_name="gemini-3.5-flash-lite",
        outcome="accepted",
        outcome_detail=None,
        provider_called=True,
        application_cache_hit=False,
        usage_available=True,
        request_count=1,
        input_tokens=1_000,
        output_tokens=200,
        cache_read_tokens=0,
        cache_write_tokens=0,
        latency_ms=125,
    )


def test_pricing_catalog_preserves_version_and_exact_decimal_cost(
    tmp_path: Path,
) -> None:
    pricing_path = tmp_path / "model_pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "_verified_at": "2026-07-27",
                "google:gemini-3.5-flash-lite": {
                    "input_per_mtok_usd": 0.3,
                    "output_per_mtok_usd": 2.5,
                },
            }
        ),
        encoding="utf-8",
    )

    priced = price_observation(
        _observation(), ModelPricingCatalog.from_path(pricing_path)
    )

    assert priced.estimated_list_cost_usd == Decimal("0.000800000000")
    assert priced.pricing_version == "2026-07-27"
    assert priced.input_price_per_mtok_usd == Decimal("0.3")
    assert priced.output_price_per_mtok_usd == Decimal("2.5")


def test_unknown_model_is_stored_as_unpriced_instead_of_zero_cost(
    tmp_path: Path,
) -> None:
    pricing_path = tmp_path / "model_pricing.json"
    pricing_path.write_text('{"_verified_at":"2026-07-27"}', encoding="utf-8")
    unknown = replace(_observation(), model_name="gemini-unpriced-preview")

    priced = price_observation(unknown, ModelPricingCatalog.from_path(pricing_path))

    assert priced.estimated_list_cost_usd is None
    assert priced.input_price_per_mtok_usd is None
    assert priced.output_price_per_mtok_usd is None


def test_record_llm_usage_extracts_run_usage_without_content() -> None:
    captured: list[LlmUsageObservation] = []
    recorder = SimpleNamespace(record=captured.append)
    result = SimpleNamespace(
        usage=lambda: RunUsage(
            requests=2,
            input_tokens=321,
            output_tokens=45,
            cache_read_tokens=100,
            cache_write_tokens=20,
        )
    )

    record_llm_usage(
        recorder,
        call_kind=LlmCallKind.NARRATION,
        model_name="gemini-3.5-flash-lite",
        outcome="validation_rejected",
        outcome_detail="unverified_content",
        result=result,
        started_at=monotonic() - 0.01,
    )

    assert len(captured) == 1
    observation = captured[0]
    assert observation.request_count == 2
    assert observation.input_tokens == 321
    assert observation.output_tokens == 45
    assert observation.cache_read_tokens == 100
    assert observation.cache_write_tokens == 20
    assert observation.latency_ms >= 0
    assert not hasattr(observation, "prompt")
    assert not hasattr(observation, "response")


def test_buffered_recorder_writes_on_background_thread() -> None:
    written = threading.Event()
    writer_thread_ids: list[int] = []

    class Repository:
        def write_batch(self, events) -> None:
            writer_thread_ids.append(threading.get_ident())
            assert len(events) == 1
            written.set()

    recorder = BufferedLlmUsageRecorder(
        Repository(),
        ModelPricingCatalog.empty(),
        flush_interval_seconds=0.01,
    )
    caller_thread_id = threading.get_ident()
    try:
        assert recorder.record(_observation()) is True
        assert written.wait(timeout=1)
    finally:
        recorder.close()

    assert writer_thread_ids
    assert writer_thread_ids[0] != caller_thread_id


def test_buffered_recorder_flushes_shutdown_queue_as_one_batch() -> None:
    batch_sizes: list[int] = []

    class Repository:
        def write_batch(self, events) -> None:
            batch_sizes.append(len(events))

    recorder = BufferedLlmUsageRecorder(
        Repository(),
        ModelPricingCatalog.empty(),
        batch_size=10,
        flush_interval_seconds=60,
    )
    for _ in range(3):
        assert recorder.record(_observation()) is True

    recorder.close()

    assert batch_sizes == [3]


class _CaptureRecorder:
    def __init__(self) -> None:
        self.observations: list[LlmUsageObservation] = []

    def record(self, observation: LlmUsageObservation) -> bool:
        self.observations.append(observation)
        return True


def _result(output: object, *, input_tokens: int, output_tokens: int):
    return SimpleNamespace(
        output=output,
        usage=lambda: RunUsage(
            requests=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        all_messages=lambda: [],
    )


def test_narrator_records_provider_usage_and_application_cache_hit() -> None:
    recorder = _CaptureRecorder()
    narrator = ClaudeNarrator(
        api_key="test-key",
        model="gemini-3.5-flash-lite",
        usage_recorder=recorder,
    )
    response = ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer="IRP 계좌 규칙을 확인해요.",
        data_mode="verified",
        sources=[
            SourceEvidence(
                evidence_id="rule:irp",
                label="IRP 규칙",
                locator="docs/rule",
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            )
        ],
    )

    class Agent:
        def run_sync(self, prompt: str):
            return _result(
                NarrationOutput(narration="IRP 계좌 규칙을 확인해요."),
                input_tokens=120,
                output_tokens=18,
            )

    narrator.agent = Agent()

    narrator.narrate(response)
    narrator.narrate(response)

    assert [item.outcome for item in recorder.observations] == [
        "accepted",
        "cache_hit",
    ]
    assert recorder.observations[0].input_tokens == 120
    assert recorder.observations[1].provider_called is False


def test_topic_guard_records_provider_usage() -> None:
    recorder = _CaptureRecorder()
    guard = ClaudeTopicGuard(
        api_key="test-key",
        model="gemini-3.5-flash-lite",
        usage_recorder=recorder,
    )

    class Agent:
        def run_sync(self, prompt: str):
            return _result(
                TopicGuardDecision(
                    allowed=True,
                    route=TopicGuardRoute.ACCOUNT_RULE,
                ),
                input_tokens=80,
                output_tokens=8,
            )

    guard.agent = Agent()

    guard.classify("노후에 받는 돈은 언제부터 꺼내 써?")

    assert len(recorder.observations) == 1
    assert recorder.observations[0].call_kind is LlmCallKind.TOPIC_GUARD
    assert recorder.observations[0].input_tokens == 80


def test_etf_feature_generator_records_validated_provider_usage() -> None:
    recorder = _CaptureRecorder()
    generator = ClaudeEtfProductFeatureGenerator(
        api_key="test-key",
        model="gemini-3.5-flash-lite",
        usage_recorder=recorder,
    )
    facts = EtfProductFeatureFacts(
        isu_code="487240",
        product_name="KODEX AI전력핵심설비",
        theme_name="AI·소프트웨어",
        benchmark_name="iSelect AI 전력핵심설비 지수",
    )

    class Agent:
        def run_sync(self, prompt: str):
            return _result(
                EtfProductFeatureBatch(
                    products=(
                        EtfProductFeatureResult(
                            isu_code="487240",
                            feature=(
                                "iSelect AI 전력핵심설비 지수를 기준으로 "
                                "관련 기업에 투자해요."
                            ),
                            support_quote="iSelect AI 전력핵심설비 지수",
                        ),
                    )
                ),
                input_tokens=240,
                output_tokens=30,
            )

    generator.agent = Agent()

    assert generator.generate((facts,))
    assert len(recorder.observations) == 1
    assert recorder.observations[0].call_kind is LlmCallKind.ETF_PRODUCT_FEATURE
    assert recorder.observations[0].outcome == "accepted"
