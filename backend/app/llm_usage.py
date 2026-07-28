"""Best-effort LLM usage and list-price estimation telemetry.

Only operational metadata is recorded. Prompts, responses, user ids and chat
session ids never enter this module. Request code performs a non-blocking queue
write; PostgreSQL inserts and price calculation run on one daemon thread.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from queue import Empty, Full, Queue
from time import monotonic
from typing import Literal, Protocol

from psycopg_pool import ConnectionPool

from .database import get_database_pool
from .llm_models import resolve_vendor, strip_vendor_prefix

logger = logging.getLogger(__name__)

DEFAULT_PRICING_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "data" / "model_pricing.json"
)
_COST_QUANTUM = Decimal("0.000000000001")
_TOKENS_PER_MILLION = Decimal(1_000_000)
_STOP_ITEM = object()


class LlmCallKind(StrEnum):
    NARRATION = "narration"
    NARRATION_PREWARM = "narration_prewarm"
    TOPIC_GUARD = "topic_guard"
    ETF_PRODUCT_FEATURE = "etf_product_feature"


LlmOutcome = Literal[
    "accepted",
    "cache_hit",
    "provider_error",
    "validation_rejected",
]


@dataclass(frozen=True, slots=True)
class LlmUsageObservation:
    call_kind: LlmCallKind
    model_name: str
    outcome: LlmOutcome
    outcome_detail: str | None
    provider_called: bool
    application_cache_hit: bool
    usage_available: bool
    request_count: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int | None
    intent: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        counts = (
            self.request_count,
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
        )
        if any(value < 0 for value in counts):
            raise ValueError("LLM usage counters must be non-negative")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        if self.application_cache_hit != (
            not self.provider_called and self.outcome == "cache_hit"
        ):
            raise ValueError("cache-hit and provider-call flags are inconsistent")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_mtok_usd: Decimal
    output_per_mtok_usd: Decimal


class ModelPricingCatalog:
    def __init__(
        self,
        *,
        version: str | None,
        prices: dict[str, ModelPrice],
    ) -> None:
        self.version = version
        self._prices = prices

    @classmethod
    def empty(cls) -> ModelPricingCatalog:
        return cls(version=None, prices={})

    @classmethod
    def from_path(cls, path: Path = DEFAULT_PRICING_PATH) -> ModelPricingCatalog:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        except (OSError, json.JSONDecodeError):
            logger.warning("llm_pricing_catalog_unavailable path=%s", path)
            return cls.empty()
        if not isinstance(payload, dict):
            logger.warning("llm_pricing_catalog_invalid path=%s", path)
            return cls.empty()

        raw_version = payload.get("_verified_at")
        version = str(raw_version) if raw_version else None
        prices: dict[str, ModelPrice] = {}
        for key, raw in payload.items():
            if key.startswith("_") or not isinstance(raw, dict):
                continue
            try:
                input_rate = Decimal(str(raw["input_per_mtok_usd"]))
                output_rate = Decimal(str(raw["output_per_mtok_usd"]))
            except (InvalidOperation, KeyError, ValueError, TypeError):
                continue
            if input_rate < 0 or output_rate < 0:
                continue
            prices[key.strip().lower()] = ModelPrice(
                input_per_mtok_usd=input_rate,
                output_per_mtok_usd=output_rate,
            )
        return cls(version=version, prices=prices)

    def get(self, *, provider: str, model_name: str) -> ModelPrice | None:
        return self._prices.get(f"{provider}:{model_name}".lower())


@dataclass(frozen=True, slots=True)
class PricedLlmUsageEvent:
    observation: LlmUsageObservation
    provider: str
    normalized_model_name: str
    estimated_list_cost_usd: Decimal | None
    pricing_version: str | None
    input_price_per_mtok_usd: Decimal | None
    output_price_per_mtok_usd: Decimal | None


def price_observation(
    observation: LlmUsageObservation,
    catalog: ModelPricingCatalog,
) -> PricedLlmUsageEvent:
    provider = resolve_vendor(observation.model_name)
    model_name = strip_vendor_prefix(observation.model_name)
    price = catalog.get(provider=provider, model_name=model_name)
    estimated_cost: Decimal | None
    if observation.application_cache_hit:
        estimated_cost = Decimal(0).quantize(_COST_QUANTUM)
    elif observation.usage_available and price is not None:
        estimated_cost = (
            (
                Decimal(observation.input_tokens) * price.input_per_mtok_usd
                + Decimal(observation.output_tokens) * price.output_per_mtok_usd
            )
            / _TOKENS_PER_MILLION
        ).quantize(_COST_QUANTUM)
    else:
        estimated_cost = None
    return PricedLlmUsageEvent(
        observation=observation,
        provider=provider,
        normalized_model_name=model_name,
        estimated_list_cost_usd=estimated_cost,
        pricing_version=catalog.version,
        input_price_per_mtok_usd=(
            price.input_per_mtok_usd if price is not None else None
        ),
        output_price_per_mtok_usd=(
            price.output_per_mtok_usd if price is not None else None
        ),
    )


class LlmUsageBatchRepository(Protocol):
    def write_batch(self, events: Sequence[PricedLlmUsageEvent]) -> None: ...


class PostgresLlmUsageRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def write_batch(self, events: Sequence[PricedLlmUsageEvent]) -> None:
        if not events:
            return
        rows = []
        for event in events:
            observation = event.observation
            rows.append(
                (
                    observation.occurred_at,
                    observation.call_kind.value,
                    observation.intent,
                    event.provider,
                    event.normalized_model_name,
                    observation.outcome,
                    observation.outcome_detail,
                    observation.provider_called,
                    observation.application_cache_hit,
                    observation.usage_available,
                    observation.request_count,
                    observation.input_tokens,
                    observation.output_tokens,
                    observation.cache_read_tokens,
                    observation.cache_write_tokens,
                    observation.latency_ms,
                    event.estimated_list_cost_usd,
                    event.pricing_version,
                    event.input_price_per_mtok_usd,
                    event.output_price_per_mtok_usd,
                )
            )
        with (
            self._pool.connection(timeout=1.0) as connection,
            connection.cursor() as cursor,
        ):
            cursor.executemany(
                """
                    insert into public.llm_usage_events (
                        occurred_at,
                        call_kind,
                        intent,
                        provider,
                        model_name,
                        outcome,
                        outcome_detail,
                        provider_called,
                        application_cache_hit,
                        usage_available,
                        request_count,
                        input_tokens,
                        output_tokens,
                        cache_read_tokens,
                        cache_write_tokens,
                        latency_ms,
                        estimated_list_cost_usd,
                        pricing_version,
                        input_price_per_mtok_usd,
                        output_price_per_mtok_usd
                    )
                    values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                rows,
            )


class LlmUsageRecorder(Protocol):
    def record(self, observation: LlmUsageObservation) -> bool: ...


class BufferedLlmUsageRecorder:
    """Bounded, non-blocking producer with one background batch writer."""

    def __init__(
        self,
        repository: LlmUsageBatchRepository,
        pricing_catalog: ModelPricingCatalog,
        *,
        queue_maxsize: int = 2_048,
        batch_size: int = 50,
        flush_interval_seconds: float = 1.0,
    ) -> None:
        if queue_maxsize < 1 or batch_size < 1 or flush_interval_seconds <= 0:
            raise ValueError("recorder limits must be positive")
        self._repository = repository
        self._pricing_catalog = pricing_catalog
        self._queue: Queue[LlmUsageObservation | object] = Queue(
            maxsize=queue_maxsize
        )
        self._batch_size = batch_size
        self._flush_interval_seconds = flush_interval_seconds
        self._stop = threading.Event()
        self._dropped_count = 0
        self._thread = threading.Thread(
            target=self._run,
            name="llm-usage-writer",
            daemon=True,
        )
        self._thread.start()

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def record(self, observation: LlmUsageObservation) -> bool:
        if self._stop.is_set():
            return False
        try:
            self._queue.put_nowait(observation)
            return True
        except Full:
            self._dropped_count += 1
            if self._dropped_count == 1 or self._dropped_count % 100 == 0:
                logger.warning(
                    "llm_usage_queue_full dropped_count=%s",
                    self._dropped_count,
                )
            return False

    def _write(self, observations: list[LlmUsageObservation]) -> None:
        if not observations:
            return
        try:
            events = [
                price_observation(observation, self._pricing_catalog)
                for observation in observations
            ]
            self._repository.write_batch(events)
        except Exception:  # noqa: BLE001 - telemetry must never affect chat
            logger.warning(
                "llm_usage_batch_write_failed event_count=%s",
                len(observations),
                exc_info=True,
            )

    def _run(self) -> None:
        batch: list[LlmUsageObservation] = []
        deadline: float | None = None
        while True:
            if batch:
                assert deadline is not None
                timeout = max(0.0, deadline - monotonic())
            else:
                timeout = min(self._flush_interval_seconds, 0.1)
            try:
                item = self._queue.get(timeout=timeout)
            except Empty:
                item = None
            if item is _STOP_ITEM:
                break
            if isinstance(item, LlmUsageObservation):
                if not batch:
                    deadline = monotonic() + self._flush_interval_seconds
                batch.append(item)
            if batch and (
                len(batch) >= self._batch_size
                or (deadline is not None and monotonic() >= deadline)
            ):
                self._write(batch)
                batch = []
                deadline = None
        self._write(batch)

    def close(self, *, timeout_seconds: float = 5.0) -> None:
        first_close = not self._stop.is_set()
        self._stop.set()
        if first_close:
            try:
                self._queue.put(_STOP_ITEM, timeout=min(1.0, timeout_seconds))
            except Full:
                logger.warning("llm_usage_writer_stop_signal_dropped")
        self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            logger.warning("llm_usage_writer_shutdown_timed_out")


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def record_llm_usage(
    recorder: LlmUsageRecorder | None,
    *,
    call_kind: LlmCallKind,
    model_name: str,
    outcome: LlmOutcome,
    outcome_detail: str | None,
    result: object | None = None,
    started_at: float | None = None,
    intent: str | None = None,
    provider_called: bool = True,
    application_cache_hit: bool = False,
) -> bool:
    """Extract provider counters and enqueue them without exposing content."""

    if recorder is None:
        return False
    usage = None
    if result is not None:
        usage_method = getattr(result, "usage", None)
        if callable(usage_method):
            try:
                usage = usage_method()
            except Exception:  # noqa: BLE001 - malformed telemetry is non-fatal
                logger.warning("llm_usage_extraction_failed")
    latency_ms = (
        None
        if started_at is None
        else max(0, round((monotonic() - started_at) * 1_000))
    )
    observation = LlmUsageObservation(
        call_kind=call_kind,
        model_name=model_name,
        outcome=outcome,
        outcome_detail=outcome_detail,
        provider_called=provider_called,
        application_cache_hit=application_cache_hit,
        usage_available=usage is not None,
        request_count=_nonnegative_int(getattr(usage, "requests", 0)),
        input_tokens=_nonnegative_int(getattr(usage, "input_tokens", 0)),
        output_tokens=_nonnegative_int(getattr(usage, "output_tokens", 0)),
        cache_read_tokens=_nonnegative_int(getattr(usage, "cache_read_tokens", 0)),
        cache_write_tokens=_nonnegative_int(getattr(usage, "cache_write_tokens", 0)),
        latency_ms=latency_ms,
        intent=intent,
    )
    try:
        return bool(recorder.record(observation))
    except Exception:  # noqa: BLE001 - telemetry must never affect chat
        logger.warning("llm_usage_enqueue_failed", exc_info=True)
        return False


_RECORDER_LOCK = threading.Lock()
_RECORDERS: dict[tuple[str, int], BufferedLlmUsageRecorder] = {}


def get_llm_usage_recorder(
    database_url: str,
    *,
    database_pool_max_size: int = 5,
) -> BufferedLlmUsageRecorder | None:
    database_url = database_url.strip()
    if not database_url:
        return None
    key = (database_url, database_pool_max_size)
    with _RECORDER_LOCK:
        recorder = _RECORDERS.get(key)
        if recorder is None:
            pool = get_database_pool(
                database_url,
                max_size=database_pool_max_size,
            )
            recorder = BufferedLlmUsageRecorder(
                PostgresLlmUsageRepository(pool),
                ModelPricingCatalog.from_path(),
            )
            _RECORDERS[key] = recorder
        return recorder


def close_llm_usage_recorders() -> None:
    with _RECORDER_LOCK:
        recorders = list(_RECORDERS.values())
        _RECORDERS.clear()
    for recorder in recorders:
        recorder.close()
