"""Collect official macro observations without changing planning assumptions."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import Settings

from ._files import atomic_write_bytes, atomic_write_json
from ._secrets import require_secret
from .macro_clients import (
    MacroApiError,
    MacroObservation,
    RawMacroResponse,
    fetch_bok_series,
    fetch_fred_series,
    fetch_kosis_series,
)

POLICY_VERSION = "macro-evidence-2026-07-20.1"

_FRESHNESS_RULES = {
    "kr_base_rate": ("daily", 7),
    "kr_cpi_index": ("monthly", 2),
    "kr_life_expectancy_65_a1": ("annual", 3),
    "kr_life_expectancy_65_a2": ("annual", 3),
    "us_federal_funds_rate": ("monthly", 2),
    "us_cpi_yoy": ("monthly", 2),
    "us_treasury_10y": ("daily", 7),
    "us_breakeven_inflation_10y": ("daily", 7),
}


def _month_offset(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _latest(observations: Iterable[MacroObservation]) -> MacroObservation:
    rows = list(observations)
    if not rows:
        raise MacroApiError(
            "macro series has no usable observations", code="empty_series"
        )
    return max(rows, key=lambda observation: observation.period)


def _observation_payload(observation: MacroObservation) -> dict[str, Any]:
    return {
        "metric_id": observation.metric_id,
        "source": observation.source,
        "label": observation.label,
        "period": observation.period,
        "value": _decimal_text(observation.value),
        "unit": observation.unit,
        "source_chip": {
            "label": observation.label,
            "reference": observation.source_reference,
            "as_of": observation.period,
        },
        "dimensions": observation.dimensions,
    }


def _freshness(metric_id: str, period: str, as_of: date) -> dict[str, Any]:
    frequency, maximum_lag = _FRESHNESS_RULES[metric_id]
    observed = date.fromisoformat(period)
    if frequency == "daily":
        lag = (as_of - observed).days
        lag_unit = "days"
    elif frequency == "monthly":
        lag = (as_of.year - observed.year) * 12 + as_of.month - observed.month
        lag_unit = "months"
    else:
        lag = as_of.year - observed.year
        lag_unit = "years"
    return {
        "frequency": frequency,
        "observed_period": period,
        "lag": lag,
        "lag_unit": lag_unit,
        "maximum_lag": maximum_lag,
        "status": "fresh" if 0 <= lag <= maximum_lag else "stale",
    }


def build_macro_evidence_report(
    *, observations: list[MacroObservation], as_of: date
) -> dict[str, Any]:
    grouped: dict[str, list[MacroObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.metric_id, []).append(observation)

    latest = {
        metric_id: _observation_payload(_latest(rows))
        for metric_id, rows in sorted(grouped.items())
    }
    korean_cpi = sorted(grouped.get("kr_cpi_index", []), key=lambda row: row.period)
    derived: dict[str, Any] = {}
    if korean_cpi:
        current = korean_cpi[-1]
        prior_period = _month_offset(
            date.fromisoformat(current.period), -12
        ).isoformat()
        prior = next((row for row in korean_cpi if row.period == prior_period), None)
        if prior is not None and prior.value != 0:
            yoy = (current.value / prior.value - Decimal("1")) * Decimal("100")
            derived["kr_cpi_yoy"] = {
                "metric_id": "kr_cpi_yoy",
                "source": "BOK_ECOS",
                "label": "소비자물가지수 전년동월비",
                "period": current.period,
                "value": _decimal_text(yoy.quantize(Decimal("0.0001"))),
                "unit": "%",
                "formula": "(current_index / index_12_months_ago - 1) * 100",
                "source_chip": {
                    "label": "한국은행 ECOS 소비자물가지수 총지수",
                    "reference": current.source_reference,
                    "as_of": current.period,
                },
            }

    required = {
        "kr_base_rate",
        "kr_cpi_index",
        "kr_life_expectancy_65_a1",
        "kr_life_expectancy_65_a2",
        "us_federal_funds_rate",
        "us_cpi_yoy",
        "us_treasury_10y",
        "us_breakeven_inflation_10y",
    }
    missing = sorted(required - latest.keys())
    freshness = {
        metric_id: _freshness(metric_id, latest[metric_id]["period"], as_of)
        for metric_id in sorted(required & latest.keys())
    }
    stale = sorted(
        metric_id
        for metric_id, result in freshness.items()
        if result["status"] == "stale"
    )
    return {
        "policy_version": POLICY_VERSION,
        "as_of": as_of.isoformat(),
        "outcome": (
            "ready"
            if not missing and not stale and "kr_cpi_yoy" in derived
            else "incomplete"
        ),
        "latest_observations": latest,
        "derived_observations": derived,
        "quality": {
            "required_metric_count": len(required),
            "available_metric_count": len(required & latest.keys()),
            "missing_metrics": missing,
            "stale_metrics": stale,
            "freshness": freshness,
        },
        "algorithm_usage": {
            "annual_assumption_review_evidence": True,
            "retirement_longevity_context": True,
            "planning_return_input": False,
            "allocation_weight_input": False,
            "rebalancing_trigger_input": False,
            "real_value_calculation_input": False,
            "is_forecast": False,
            "reason": (
                "최근 거시 관측치는 승인된 장기 계획가정의 검토 근거일 뿐, "
                "ETF 미래수익률·목표비중·리밸런싱 신호로 직접 사용하지 않는다."
            ),
        },
    }


def _save_raw(
    root: Path, response: RawMacroResponse, name: str, as_of: date
) -> dict[str, Any]:
    path = root / as_of.isoformat() / response.source.lower() / f"{name}.json"
    atomic_write_bytes(path, response.raw_content)
    return {
        "source": response.source,
        "path": path.as_posix(),
        "request_params": response.request_params,
        "sha256": response.sha256,
    }


def run_live_collection(
    *,
    bok_api_key: str,
    kosis_api_key: str,
    fred_api_key: str,
    as_of: date,
    raw_root: Path,
    report_path: Path,
) -> dict[str, Any]:
    observations: list[MacroObservation] = []
    manifests: list[dict[str, Any]] = []
    start_daily = (as_of - timedelta(days=90)).strftime("%Y%m%d")
    start_monthly = _month_offset(as_of, -24)
    fred_start = _month_offset(as_of, -24).isoformat()

    with httpx.Client(
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "pension-copilot-macro-evidence/0.1"},
    ) as client:
        response, rows = fetch_bok_series(
            client,
            api_key=bok_api_key,
            metric_id="kr_base_rate",
            stat_code="722Y001",
            cycle="D",
            start_period=start_daily,
            end_period=as_of.strftime("%Y%m%d"),
            item_code="0101000",
        )
        manifests.append(_save_raw(raw_root, response, "kr_base_rate", as_of))
        observations.extend(rows)

        response, rows = fetch_bok_series(
            client,
            api_key=bok_api_key,
            metric_id="kr_cpi_index",
            stat_code="901Y009",
            cycle="M",
            start_period=start_monthly.strftime("%Y%m"),
            end_period=as_of.strftime("%Y%m"),
            item_code="0",
        )
        manifests.append(_save_raw(raw_root, response, "kr_cpi_index", as_of))
        observations.extend(rows)

        response, rows = fetch_kosis_series(
            client,
            api_key=kosis_api_key,
            metric_id="kr_life_expectancy_65",
            org_id="101",
            table_id="DT_2OEHG072",
            item_id="T001",
            object_l1="1005",
            object_l2="A1+A2",
            latest_period_count=5,
        )
        manifests.append(_save_raw(raw_root, response, "kr_life_expectancy_65", as_of))
        observations.extend(rows)

        fred_specs = (
            ("us_federal_funds_rate", "FEDFUNDS", "미국 연방기금 실효금리", "%", "lin"),
            ("us_cpi_yoy", "CPIAUCSL", "미국 소비자물가지수 전년동월비", "%", "pc1"),
            ("us_treasury_10y", "DGS10", "미국 10년 국채금리", "%", "lin"),
            (
                "us_breakeven_inflation_10y",
                "T10YIE",
                "미국 10년 기대인플레이션",
                "%",
                "lin",
            ),
        )
        for metric_id, series_id, label, unit, units in fred_specs:
            response, rows = fetch_fred_series(
                client,
                api_key=fred_api_key,
                metric_id=metric_id,
                series_id=series_id,
                label=label,
                unit=unit,
                observation_start=fred_start,
                observation_end=as_of.isoformat(),
                units=units,
            )
            manifests.append(_save_raw(raw_root, response, metric_id, as_of))
            observations.extend(rows)

    report = build_macro_evidence_report(observations=observations, as_of=as_of)
    report["source_manifests"] = manifests
    atomic_write_json(report_path, report)
    return {
        "outcome": report["outcome"],
        "as_of": as_of.isoformat(),
        "observation_count": len(observations),
        "source_response_count": len(manifests),
        "report_path": report_path.as_posix(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect BOK, KOSIS and FRED observations for assumption review."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/macro"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("data/cache/macro/macro_evidence_latest.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings(_env_file=args.env_file)
    result = run_live_collection(
        bok_api_key=require_secret(settings.bok_ecos_api_key, "BOK_ECOS_API_KEY"),
        kosis_api_key=require_secret(settings.kosis_api_key, "KOSIS_API_KEY"),
        fred_api_key=require_secret(settings.fred_api_key, "FRED_API_KEY"),
        as_of=args.as_of,
        raw_root=args.raw_root,
        report_path=args.report_path,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
