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


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MacroEvidenceUnavailable(f"macro evidence field is invalid: {field}")
    return value


class MacroEvidenceRepository:
    """Read only the public subset of a collector-produced JSON report."""

    def __init__(self, report_path: Path) -> None:
        self._report_path = report_path

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
