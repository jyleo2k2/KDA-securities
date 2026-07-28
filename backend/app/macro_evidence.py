"""Sanitized read model for the latest official macro evidence report."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .engine.macro_regime import (
    MacroAnalogRegimeEvaluation,
    MonthlyMacroRegimeObservation,
    calculate_macro_analog_regimes,
)
from .engine.macro_regime_outcomes import (
    MacroRegimeEtfOutcomeEvaluation,
    calculate_post_regime_etf_outcomes,
)
from .engine.models import SourceChip


class MacroEvidenceUnavailable(RuntimeError):
    """Raised when the local evidence report cannot be safely served."""


class MacroMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str
    label: str
    value: Decimal
    unit: str
    observed_at: date
    source: str
    publisher: str
    source_label: str
    source_url: str
    basis: str


class MacroAlgorithmUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    annual_assumption_review_evidence: bool
    retirement_longevity_context: bool
    planning_return_input: bool
    allocation_weight_input: bool
    rebalancing_trigger_input: bool
    real_value_calculation_input: bool
    is_forecast: bool
    reason: str


class MacroEvidenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str
    as_of: date
    outcome: Literal["ready", "incomplete"]
    metrics: list[MacroMetric]
    missing_metrics: list[str] = Field(default_factory=list)
    stale_metrics: list[str] = Field(default_factory=list)
    algorithm_usage: MacroAlgorithmUsage


class MacroRegimeMetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str
    label: str
    unit: str
    aggregation: str
    source: str
    publisher: str
    source_label: str
    source_url: str
    source_as_of: date


class MacroAnalogRegimeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: date
    dataset_policy_version: str
    period_start: date
    period_end: date
    complete_month_count: int
    metrics: list[MacroRegimeMetricDefinition]
    analysis: MacroAnalogRegimeEvaluation
    etf_outcomes: MacroRegimeEtfOutcomeEvaluation | None = None


_PUBLIC_METRICS = (
    "kr_base_rate",
    "kr_cpi_yoy",
    "kr_life_expectancy_65_a1",
    "kr_life_expectancy_65_a2",
    "us_federal_funds_rate",
    "us_cpi_yoy",
    "us_treasury_10y",
    "us_breakeven_inflation_10y",
)
_PUBLISHERS = {
    "BOK_ECOS": "한국은행 ECOS",
    "KOSIS": "국가데이터처 KOSIS",
    "FRED": "Federal Reserve Bank of St. Louis",
}
_KIS_MARKET_DATA_REFERENCE = "https://openapi.koreainvestment.com/"
DEFAULT_ANALOG_REGIME_SNAPSHOT_PATH = Path(
    "data/reference/macro_analog_regime_snapshot_2026-07-20.json"
)


def attach_etf_outcomes(
    snapshot: MacroAnalogRegimeSnapshot,
    *,
    repository: Any,
    isu_codes: list[str],
) -> MacroAnalogRegimeSnapshot:
    """Attach realized ETF outcomes from an injected market-data repository."""

    codes = list(dict.fromkeys(isu_codes))
    if not codes:
        return snapshot
    loader = getattr(repository, "load_total_return_histories", None)
    if callable(loader):
        histories, history_sources = loader(set(codes))
    else:
        histories = {
            code: repository.histories[code]
            for code in codes
            if code in repository.histories
        }
        history_sources = {
            code: repository.history_sources[code]
            for code in codes
            if code in repository.history_sources
        }
    names_by_code = {
        str(product["isu_code"]): str(product.get("isu_name") or product["isu_code"])
        for product in repository.products
        if isinstance(product, dict) and product.get("isu_code") in codes
    }
    source_chips = {
        code: SourceChip(
            label=(
                "한투 수정주가·KIND 현금분배 반영 원화 총수익지수"
                if source == "kis_adjusted_close_plus_kind_cash_distribution"
                else "ETF 과거 가격 이력"
            ),
            reference=_KIS_MARKET_DATA_REFERENCE,
            as_of=max(histories[code]),
        )
        for code, source in history_sources.items()
        if code in histories and histories[code]
    }
    evaluation = calculate_post_regime_etf_outcomes(
        matches=snapshot.analysis.matches,
        isu_codes=codes,
        names_by_code=names_by_code,
        histories=histories,
        history_sources=history_sources,
        source_chips=source_chips,
    )
    return snapshot.model_copy(update={"etf_outcomes": evaluation})


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MacroEvidenceUnavailable(f"macro evidence field is invalid: {field}")
    return value


class MacroEvidenceRepository:
    """Read only the public subset of a collector-produced JSON report."""

    def __init__(
        self,
        report_path: Path,
        *,
        analog_snapshot_path: Path = DEFAULT_ANALOG_REGIME_SNAPSHOT_PATH,
    ) -> None:
        self._report_path = report_path
        self._analog_snapshot_path = analog_snapshot_path

    def _root(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._report_path.read_text(encoding="utf-8"))
            return _mapping(payload, field="root")
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise MacroEvidenceUnavailable(
                "current macro evidence report is unavailable"
            ) from exc

    def latest(self) -> MacroEvidenceSnapshot:
        try:
            root = self._root()
            latest = _mapping(
                root.get("latest_observations"), field="latest_observations"
            )
            derived = _mapping(
                root.get("derived_observations"), field="derived_observations"
            )
            quality = _mapping(root.get("quality"), field="quality")
            usage = _mapping(root.get("algorithm_usage"), field="algorithm_usage")
            metrics = [
                self._metric(
                    metric_id,
                    _mapping(
                        (derived if metric_id == "kr_cpi_yoy" else latest).get(
                            metric_id
                        ),
                        field=metric_id,
                    ),
                )
                for metric_id in _PUBLIC_METRICS
                if metric_id in (derived if metric_id == "kr_cpi_yoy" else latest)
            ]
            return MacroEvidenceSnapshot(
                policy_version=root["policy_version"],
                as_of=root["as_of"],
                outcome=root["outcome"],
                metrics=metrics,
                missing_metrics=quality.get("missing_metrics", []),
                stale_metrics=quality.get("stale_metrics", []),
                algorithm_usage=MacroAlgorithmUsage.model_validate(usage),
            )
        except (
            KeyError,
            TypeError,
            ValidationError,
        ) as exc:
            raise MacroEvidenceUnavailable(
                "current macro evidence report is unavailable"
            ) from exc

    def analog_regimes(self) -> MacroAnalogRegimeSnapshot:
        if not self._report_path.is_file():
            try:
                payload = json.loads(
                    self._analog_snapshot_path.read_text(encoding="utf-8")
                )
                return MacroAnalogRegimeSnapshot.model_validate(payload)
            except (
                OSError,
                json.JSONDecodeError,
                TypeError,
                ValidationError,
            ) as exc:
                raise MacroEvidenceUnavailable(
                    "historical macro regime evidence is unavailable"
                ) from exc
        try:
            root = self._root()
            dataset = _mapping(
                root.get("historical_regime_dataset"),
                field="historical_regime_dataset",
            )
            if dataset.get("outcome") != "ready":
                raise MacroEvidenceUnavailable(
                    "historical macro regime evidence is incomplete"
                )
            rows_payload = dataset.get("rows")
            definitions_payload = dataset.get("metric_definitions")
            if not isinstance(rows_payload, list) or not isinstance(
                definitions_payload, list
            ):
                raise TypeError("historical regime rows are invalid")
            rows = [
                MonthlyMacroRegimeObservation.model_validate(row)
                for row in rows_payload
            ]
            definitions = [
                self._regime_definition(item) for item in definitions_payload
            ]
            analysis = calculate_macro_analog_regimes(rows)
            quality = _mapping(dataset.get("quality"), field="regime_quality")
            return MacroAnalogRegimeSnapshot(
                as_of=root["as_of"],
                dataset_policy_version=dataset["policy_version"],
                period_start=dataset["period_start"],
                period_end=dataset["period_end"],
                complete_month_count=quality["complete_month_count"],
                metrics=definitions,
                analysis=analysis,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            raise MacroEvidenceUnavailable(
                "historical macro regime evidence is unavailable"
            ) from exc

    @staticmethod
    def _metric(metric_id: str, payload: dict[str, Any]) -> MacroMetric:
        source_chip = _mapping(payload.get("source_chip"), field="source_chip")
        source = str(payload["source"])
        return MacroMetric(
            metric_id=metric_id,
            label=payload["label"],
            value=payload["value"],
            unit=payload["unit"],
            observed_at=payload["period"],
            source=source,
            publisher=_PUBLISHERS.get(source, source),
            source_label=source_chip["label"],
            source_url=source_chip["reference"],
            basis=payload.get("formula", "공식 API 최신 관측값"),
        )

    @staticmethod
    def _regime_definition(payload: object) -> MacroRegimeMetricDefinition:
        item = _mapping(payload, field="regime_metric_definition")
        source_chip = _mapping(item.get("source_chip"), field="source_chip")
        source = str(item["source"])
        return MacroRegimeMetricDefinition(
            metric_id=item["metric_id"],
            label=item["label"],
            unit=item["unit"],
            aggregation=item["aggregation"],
            source=source,
            publisher=_PUBLISHERS.get(source, source),
            source_label=source_chip["label"],
            source_url=source_chip["reference"],
            source_as_of=source_chip["as_of"],
        )
